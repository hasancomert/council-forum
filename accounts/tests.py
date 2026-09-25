from datetime import timedelta
from unittest.mock import patch

from django.conf import settings
from django.core import mail
from django.test import TestCase
from django.utils import timezone

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
