from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from django.views.decorators.debug import sensitive_post_parameters

from comments.models import Comment
from voting.models import withdraw_running

from .forms import DeleteAccountForm, SignupForm
from .models import User


@sensitive_post_parameters('password1', 'password2')  # 500 hata e-postasında şifre görünmesin
def signup(request):
    form = SignupForm(request.POST or None)
    if form.is_bound:
        User.purge_unverified()
    # is_valid() CAPTCHA'yı Cloudflare'e sorar (en çok 10 sn): ağ isteği veritabanı işleminin dışında kalır,
    # SQLite'ın yazma kilidi bu sürede tutulmaz.
    if form.is_valid():
        with transaction.atomic():  # e-posta gönderilemezse hesap da oluşmasın
            user = form.save(commit=False)
            user.is_active = False  # e-posta doğrulanana kadar giriş yapamaz
            user.terms_accepted_at = timezone.now()  # zorunlu kutu: kabul anı saklanır
            user.save()
            uid = urlsafe_base64_encode(str(user.pk).encode())
            token = default_token_generator.make_token(user)
            link = request.build_absolute_uri(reverse('activate', args=[uid, token]))
            user.email_user('Forum hesabını doğrula', f'Hesabını açmak için bağlantıya tıkla:\n{link}')
        return render(request, 'message.html', {
            'title': 'E-postanı kontrol et',
            'message': f'{user.email} adresine bir doğrulama bağlantısı gönderdik.',
        })
    return render(request, 'registration/signup.html', {'form': form, 'site_key': settings.TURNSTILE_SITE_KEY})


def activate(request, uidb64, token):
    try:
        user = User.objects.get(pk=urlsafe_base64_decode(uidb64).decode())
    except (ValueError, OverflowError, User.DoesNotExist):
        user = None
    if user is None or not default_token_generator.check_token(user, token):
        return render(request, 'message.html', {
            'title': 'Geçersiz bağlantı',
            'message': 'Bağlantı kullanılmış ya da süresi dolmuş. Süresi dolduysa yeniden kayıt olabilirsin.',
        }, status=400)
    user.is_active = True
    user.save(update_fields=['is_active'])
    login(request, user)  # last_login değişir, token geçersizleşir: bağlantı tek kullanımlık
    return redirect('home')


@sensitive_post_parameters('password')
@login_required
def delete_account(request):
    """Hesabı sil: kişisel bilgiler anonimleşir (User.anonymize). Süren oylamalardaki oylar ve açık öneriler geri
    çekilir; bitmiş oylamalar ve ▲/▼ puanları değişmez. Yorum metinleri yalnızca üye isterse silinir.
    """
    user = request.user
    if user.is_staff:
        raise PermissionDenied  # kurucu/admin hesabı buradan silinmez: son süper kullanıcı kaybolmasın
    form = DeleteAccountForm(user, request.POST or None)
    if form.is_valid():
        with transaction.atomic():
            withdraw_running(user)
            if form.cleaned_data['delete_comments']:
                Comment.objects.filter(author=user).update(is_deleted=True, body='')  # yerinde "Bu yorum silindi"
            user.anonymize()
        logout(request)
        messages.success(request, 'Hesabın silindi.')
        return redirect('home')
    return render(request, 'accounts/delete.html', {'form': form, 'title': 'Hesabı sil'})
