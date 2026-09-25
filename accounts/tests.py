from datetime import timedelta
from unittest.mock import patch

from django.conf import settings
from django.core import mail
from django.test import TestCase

from .models import User

FORM = {'username': 'ali', 'first_name': 'Ali', 'last_name': 'Veli', 'email': 'Ali@Example.com',
        'password1': 'uzun-bir-sifre-42', 'password2': 'uzun-bir-sifre-42'}


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
