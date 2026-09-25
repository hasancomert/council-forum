from datetime import timedelta
from unittest.mock import patch

from django.conf import settings
from django.core import mail
from django.test import TestCase
from django.utils import timezone

from comments.models import Comment
from topics.models import Topic
from voting.models import TopicCloseProposal, TopicEditProposal, Vote
from voting.tests import make_user

from .models import User

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

    def test_expired_unverified_account_is_freed(self, _):
        self.signup()
        User.objects.update(date_joined=User.objects.get().date_joined
                            - timedelta(seconds=settings.PASSWORD_RESET_TIMEOUT + 1))
        self.signup()
        self.assertEqual(User.objects.count(), 1)
        self.assertEqual(len(mail.outbox), 2)


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
        self.assertContains(self.delete(password='yanlis'), 'Şifre yanlış.')
        self.user.refresh_from_db()
        self.assertIsNone(self.user.deleted_at)

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
