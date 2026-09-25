import json
from urllib.parse import urlencode
from urllib.request import urlopen

from django import forms
from django.conf import settings
from django.contrib.auth.forms import UserCreationForm

from .models import User


def turnstile_ok(token):
    """Cloudflare'e sorar: CAPTCHA çözüldü mü? Ağ/yanıt hatasında kayıt reddedilir."""
    data = urlencode({'secret': settings.TURNSTILE_SECRET_KEY, 'response': token}).encode()
    try:
        with urlopen('https://challenges.cloudflare.com/turnstile/v0/siteverify', data, timeout=10) as r:
            return json.load(r).get('success') is True
    except (OSError, ValueError):
        return False


class SignupForm(UserCreationForm):
    # Yalnızca şartların kabulü: KVKK aydınlatması onay değil bilgilendirmedir, şarta bağlanmaz (şablonda bağlantı).
    terms = forms.BooleanField(label='Kullanım şartlarını okudum, kabul ediyorum.')

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ('username', 'first_name', 'last_name', 'email')

    def clean_email(self):
        return self.cleaned_data['email'].lower()  # Ali@x.com ile ali@x.com aynı hesap sayılsın

    def clean(self):
        # Turnstile, çözülen CAPTCHA'nın jetonunu forma bu adla ekler
        if not turnstile_ok(self.data.get('cf-turnstile-response', '')):
            raise forms.ValidationError('Robot olmadığın doğrulanamadı, tekrar dene.')
        return super().clean()


class DeleteAccountForm(forms.Form):
    password = forms.CharField(label='Şifren', widget=forms.PasswordInput(attrs={'autocomplete': 'current-password'}))
    delete_comments = forms.BooleanField(label='Yorumlarımın metnini de sil', required=False, label_suffix='')

    def __init__(self, user, *args, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean_password(self):
        if not self.user.check_password(self.cleaned_data['password']):
            raise forms.ValidationError('Şifre yanlış.')
