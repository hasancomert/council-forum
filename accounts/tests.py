import io
from datetime import timedelta
from unittest.mock import MagicMock, patch
from urllib.error import URLError

from django.conf import settings
from django.core import mail
from django.db import connection
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from comments.models import Comment
from moderation.models import ModAction
from topics.models import Topic
from voting.models import TopicCloseProposal, TopicEditProposal, Vote

from .forms import TURNSTILE_URL, turnstile_ok
from .models import User
from .testing import make_user

FORM = {'username': 'ali', 'first_name': 'Ali', 'last_name': 'Veli', 'email': 'Ali@Example.com',
        'password1': 'uzun-bir-sifre-42', 'password2': 'uzun-bir-sifre-42', 'terms': 'on'}


@patch('accounts.forms.turnstile_ok', return_value=True)  # testte Cloudflare'e gidilmez
class SignupTests(TestCase):
    def signup(self, **changes):
        return self.client.post('/accounts/signup/', FORM | changes)

    def test_signup_then_activate(self, _):
        self.signup()
        user = User.objects.get()
        self.assertFalse(user.is_active)
        self.assertEqual(user.email, 'ali@example.com')
        link = mail.outbox[0].body.split()[-1]
        self.assertRedirects(self.client.get(link), '/')
        user.refresh_from_db()
        self.assertTrue(user.is_active)
        self.assertEqual(self.client.get(link).status_code, 400)  # bağlantı tek kullanımlık

    def test_broken_activation_link_is_400(self, _):
        self.assertEqual(self.client.get('/accounts/activate/!!!/x/').status_code, 400)  # 500 değil

    def test_terms_required_and_acceptance_time_saved(self, _):
        self.assertContains(self.signup(terms=''), 'Bu alan zorunludur')
        self.assertFalse(User.objects.exists())
        self.signup()
        accepted = User.objects.get().terms_accepted_at
        self.assertGreater(accepted, timezone.now() - timedelta(minutes=1))

    def test_captcha_required(self, captcha):
        captcha.return_value = False
        self.assertContains(self.signup(), 'Robot olmadığın')
        self.assertFalse(User.objects.exists())

    def test_duplicates_ignore_case(self, _):
        self.signup()
        self.signup(username='ALI', email='x@example.com')
        self.signup(username='ali2', email='ALI@example.com')
        self.assertEqual(User.objects.count(), 1)

    def test_username_letters_and_lookalikes(self, _):
        self.signup()  # ali
        for name in ('İlker', 'şule'):
            User.objects.create_user(name, f'{len(name)}{name[-1]}@example.com', None, first_name='A', last_name='B')
        # benzer ad (harf büyüklüğü, i/ı/I/İ), e-posta ve noktalı ad, Kiril 'е' ile taklit
        for i, bad in enumerate(('ALİ', 'Alı', 'ilker', 'ILKER', 'Şule', 'ali@x.com', 'a.b', 'vеli')):
            with self.subTest(bad):
                self.assertContains(self.signup(username=bad, email=f'k{i}@example.com'), 'errorlist')
        self.assertEqual(User.objects.count(), 3)
        self.signup(username='Çağrı_Öz-42', email='c@example.com')
        self.assertTrue(User.objects.filter(username='Çağrı_Öz-42').exists())

    def test_expired_unverified_account_is_freed(self, _):
        self.signup()
        User.objects.update(date_joined=User.objects.get().date_joined
                            - timedelta(seconds=settings.PASSWORD_RESET_TIMEOUT + 1))
        self.signup()
        self.assertEqual(User.objects.count(), 1)
        self.assertEqual(len(mail.outbox), 2)

    def test_cleanup_skips_account_closed_by_moderation(self, _):
        # hiç giriş yapmadan kapatılan hesabın kaydı (PROTECT) silinemez: her kayıt denemesi 500 veriyordu
        closed = make_user('kapatilan')
        ModAction.objects.create(moderator=make_user('yonetici'), user=closed, kind='close', reason='fake', note='.')
        User.objects.filter(pk=closed.pk).update(is_active=False, date_joined=timezone.now() - timedelta(days=30))
        self.assertEqual(self.signup().status_code, 200)
        self.assertTrue(User.objects.filter(pk=closed.pk).exists())

    def test_captcha_checked_outside_transaction(self, captcha):
        # Cloudflare'e soru (en çok 10 sn) bir veritabanı işleminin içinde olsaydı SQLite yazma kilidini tutardı
        depth = []
        captcha.side_effect = lambda token: depth.append(len(connection.savepoint_ids)) or True
        baseline = len(connection.savepoint_ids)  # testin kendi işlemi
        self.signup()
        self.assertEqual(depth, [baseline])
        self.assertTrue(User.objects.filter(username='ali').exists())

    def test_passwords_hidden_from_error_reports(self, _):
        r = self.signup()
        self.assertEqual(r.wsgi_request.sensitive_post_parameters, ('password1', 'password2'))


class VoteTests(TestCase):
    def test_weight_and_min_age(self):
        user = User.objects.create_user('b', email='b@example.com', role=User.Role.EXPERT)
        self.assertEqual(user.vote_weight, settings.FORUM['VOTE_WEIGHT']['B'])
        self.assertFalse(user.can_vote)
        user.date_joined -= timedelta(days=settings.FORUM['MIN_ACCOUNT_AGE_DAYS'])
        self.assertTrue(user.can_vote)
        user.is_active = False
        self.assertFalse(user.can_vote)

    def test_ban_lifts_by_itself(self):
        user = User.objects.create_user('c', email='c@example.com')
        user.date_joined -= timedelta(days=settings.FORUM['MIN_ACCOUNT_AGE_DAYS'])
        user.banned_until = timezone.now() + timedelta(days=1)
        self.assertFalse(user.can_post or user.can_vote)
        user.banned_until = timezone.now() - timedelta(seconds=1)  # süre doldu, alan temizlenmeden kalkar
        self.assertTrue(user.can_post and user.can_vote)


class LegalPageTests(TestCase):
    def test_pages_linked_from_footer_and_use_settings(self):
        home = self.client.get('/')
        for url in ('/kullanim-sartlari/', '/kvkk/', '/cerezler/', '/iletisim/'):
            self.assertContains(home, f'href="{url}"')
            self.assertContains(self.client.get(url), 'hukuk uzmanı kontrolü gerekir')
        self.assertContains(self.client.get('/iletisim/'), settings.SITE['email'])  # 5651 tanıtıcı bilgi
        terms = self.client.get('/kullanim-sartlari/')  # kural sayıları metne ayardan gelir
        self.assertContains(terms, f"oy ağırlığı {settings.FORUM['VOTE_WEIGHT']['B']}")
        self.assertContains(terms, f"%{settings.FORUM['QUORUM_PERCENT']}")


class DeleteAccountTests(TestCase):
    def setUp(self):
        self.user = make_user('silinecek')
        self.user.set_password('dogru-sifre-42')
        self.user.save()
        self.other = make_user('diger')
        self.topic = Topic.objects.create(title='Konu', author=self.user)
        self.comment = Comment.objects.create(target=self.topic, author=self.user, body='Benim yorumum')
        self.running = TopicCloseProposal.objects.create(proposer=self.user, topic=self.topic)
        self.finished = TopicEditProposal.objects.create(proposer=self.other, topic=self.topic, new_title='Yeni')
        for p in (self.running, self.finished):
            Vote.cast(proposal=p, voter=self.user, choice='yes')
        TopicEditProposal.objects.filter(pk=self.finished.pk).update(voting_ends_at=timezone.now())  # bitti
        self.client.force_login(self.user)

    def delete(self, **data):
        return self.client.post('/accounts/delete/', {'password': 'dogru-sifre-42'} | data)

    def test_wrong_password_changes_nothing(self):
        r = self.delete(password='yanlis')
        self.assertContains(r, 'Şifre yanlış.')
        self.assertEqual(r.wsgi_request.sensitive_post_parameters, ('password',))  # 500 e-postasında görünmez
        self.user.refresh_from_db()
        self.assertIsNone(self.user.deleted_at)

    def test_lookalike_name_cannot_block_deletion(self):
        # anonimleştirme pk'den türeyen ad yazsaydı biri o adla önceden kayıt olup silmeyi (KVKK) engelleyebilirdi
        make_user(f'silinmis-{self.user.pk}')
        User.objects.create_user('x', f'{self.user.pk}@silinmis.invalid', None, first_name='A', last_name='B')
        self.assertRedirects(self.delete(), '/')
        self.user.refresh_from_db()
        self.assertIsNotNone(self.user.deleted_at)

    def test_anonymizes_and_keeps_finished_votes(self):
        self.assertRedirects(self.delete(), '/')
        u = User.objects.get(pk=self.user.pk)
        self.assertEqual((str(u), u.first_name, u.last_name, u.is_active), ('silinmiş üye', '', '', False))
        self.assertNotIn('silinecek', u.username + u.email)
        self.assertFalse(u.has_usable_password())
        self.assertEqual(self.client.get('/accounts/').status_code, 302)  # oturum kapandı
        self.assertEqual(list(Vote.objects.filter(voter=u).values_list('object_id', flat=True)), [self.finished.pk])
        self.running.refresh_from_db()
        self.assertEqual(self.running.status, 'cancelled')  # açık öneri geri çekildi
        self.comment.refresh_from_db()
        self.assertEqual((self.comment.body, self.comment.is_deleted), ('Benim yorumum', False))  # kutu işaretsiz
        self.assertContains(self.client.get(self.topic.get_absolute_url()), 'silinmiş üye')

    def test_optionally_deletes_comment_texts(self):
        self.delete(delete_comments='on')
        self.comment.refresh_from_db()
        self.assertEqual((self.comment.body, self.comment.is_deleted), ('', True))

    def test_staff_cannot_delete_and_anonymized_is_not_purged(self):
        User.objects.filter(pk=self.other.pk).update(is_staff=True)
        self.client.force_login(self.other)
        self.assertEqual(self.delete().status_code, 403)
        self.user.anonymize()
        User.objects.filter(pk=self.user.pk).update(last_login=None, date_joined=timezone.now() - timedelta(days=30))
        with patch('accounts.forms.turnstile_ok', return_value=True):
            self.client.post('/accounts/signup/', FORM)  # doğrulanmamış hesap temizliği anonim hesaba dokunmaz
        self.assertTrue(User.objects.filter(pk=self.user.pk).exists())


class TurnstileTests(SimpleTestCase):
    """CAPTCHA doğrulayıcısı (accounts.forms.turnstile_ok): Cloudflare yerine sahte urlopen."""

    def reply(self, body):
        response = MagicMock()
        response.__enter__.return_value = io.BytesIO(body)
        return response

    @patch('accounts.forms.urlopen')
    def test_success_and_request(self, urlopen):
        urlopen.return_value = self.reply(b'{"success": true}')
        self.assertTrue(turnstile_ok('jeton'))
        url, data = urlopen.call_args.args[:2]
        self.assertEqual(url, TURNSTILE_URL)
        self.assertIn(b'response=jeton', data)
        self.assertIn(b'secret=', data)

    @patch('accounts.forms.urlopen')
    def test_rejects_without_token_on_failure_and_on_errors(self, urlopen):
        self.assertFalse(turnstile_ok(''))
        urlopen.assert_not_called()  # jetonsuz istek Cloudflare'e gitmez
        urlopen.return_value = self.reply(b'{"success": false}')
        self.assertFalse(turnstile_ok('jeton'))
        urlopen.return_value = self.reply(b'bozuk')  # JSON değil: fail-closed ve kayda düşer
        with self.assertLogs('accounts.forms', 'WARNING'):
            self.assertFalse(turnstile_ok('jeton'))
        urlopen.side_effect = URLError('ağ yok')
        with self.assertLogs('accounts.forms', 'WARNING'):
            self.assertFalse(turnstile_ok('jeton'))
