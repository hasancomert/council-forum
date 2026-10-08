import json
import logging
import re
from urllib.parse import urlencode
from urllib.request import urlopen

from django import forms
from django.conf import settings
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.password_validation import get_default_password_validators

from .models import User

logger = logging.getLogger(__name__)
TURNSTILE_URL = 'https://challenges.cloudflare.com/turnstile/v0/siteverify'


def turnstile_ok(token):
    """Cloudflare'e sorar: CAPTCHA çözüldü mü? Jeton yoksa sormaz. Ağ/yanıt hatasında kayıt reddedilir (fail-closed)
    ve neden kayda düşer (yanlış anahtar, CSP, ağ: hepsi kullanıcıya aynı mesajı verir, işletmeci kayıttan görür).
    """
    if not token:
        return False
    data = urlencode({'secret': settings.TURNSTILE_SECRET_KEY, 'response': token}).encode()
    try:
        with urlopen(TURNSTILE_URL, data, timeout=10) as r:
            return json.load(r).get('success') is True
    except (OSError, ValueError) as e:
        logger.warning('Turnstile doğrulanamadı: %r', e)
        return False


class SignupForm(UserCreationForm):
    # Yalnızca şartların kabulü: KVKK aydınlatması onay değil bilgilendirmedir, şarta bağlanmaz (şablonda bağlantı).
    terms = forms.BooleanField(label='Kullanım şartlarını okudum, kabul ediyorum.')

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ('username', 'email', 'first_name', 'last_name')  # geniş ekranda ikişer ikişer yan yana

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Açıklamalar tek satır: yan yana iki alanın satırları hizalı kalsın, sayfa bir ekrana sığsın. Django'nun
        # dört maddelik parola listesi yerine kısa hâli; en kısa uzunluk AUTH_PASSWORD_VALIDATORS'tan okunur.
        # Öbür kurallar (yaygın şifre, bilgilere benzerlik) yine denetlenir, ihlalde hata mesajı çıkar.
        n = next(v.min_length for v in get_default_password_validators() if hasattr(v, 'min_length'))
        f = self.fields
        f['password1'].label, f['password2'].label = 'Şifre', 'Şifre (tekrar)'  # arayüz "parola" değil "şifre" der
        f['username'].help_text = 'Herkese görünür: harf, rakam, _ ve -'
        f['first_name'].help_text = f['last_name'].help_text = 'Kimseye gösterilmez.'
        f['email'].help_text = 'Doğrulama için; kimseye gösterilmez.'
        f['password1'].help_text = f'En az {n} karakter, yalnızca rakam olamaz.'
        f['password2'].help_text = 'Aynı şifreyi yeniden yaz.'

    def clean_username(self):
        """Taklit olmasın: harf büyüklüğü ve i/ı/I/İ farkı yok sayılır ("Veli"/"veli", "İlker"/"ilker" aynı ad).
        Tek sorgu: her i türevi [iıIİ] olur, gerisi büyük/küçük harf duyarsız düzenli ifadeyle aranır (iregex;
        SQLite'ta Python'un re'si, PostgreSQL'de ~*; ikisi de Ş/ş'yi tanır, SQL'in iexact'i SQLite'ta tanımaz).
        """
        name = self.cleaned_data['username']
        pattern = ''.join('[iıIİ]' if c in 'iıIİ' else re.escape(c) for c in name)
        if User.objects.filter(username__iregex=f'^{pattern}$').exists():
            raise forms.ValidationError('Bu takma ad ya da çok benzeri alınmış.')
        return name

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
