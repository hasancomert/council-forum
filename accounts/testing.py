"""Testlerin ortak yardımcısı (bütün uygulamaların testleri kullanır; bir test modülü ötekinden import etmesin)."""
from datetime import timedelta

from django.utils import timezone

from .models import User


def make_user(name, role='A', days=10):
    # Şifresiz (None): hash'leme testleri yavaşlatır; giriş force_login ile yapılır. days: hesap yaşı (kural 1).
    user = User.objects.create_user(name, f'{name}@example.com', None, first_name='Ad', last_name='Soyad', role=role)
    User.objects.filter(pk=user.pk).update(date_joined=timezone.now() - timedelta(days=days))
    user.refresh_from_db()
    return user
