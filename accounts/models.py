from datetime import timedelta

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone


class User(AbstractUser):
    class Role(models.TextChoices):
        MEMBER = 'A', 'Üye'
        EXPERT = 'B', 'Bilirkişi'

    # AbstractUser'daki alanların etiketi Türkçe, ad/soyad/e-posta zorunlu yapıldı.
    username = models.CharField(
        'takma ad',
        max_length=150,
        unique=True,
        validators=[AbstractUser.username_validator],
        help_text='En fazla 150 karakter: harf, rakam ve @ . + - _',
    )
    first_name = models.CharField('ad', max_length=150)
    last_name = models.CharField('soyad', max_length=150)
    email = models.EmailField('e-posta', unique=True)
    role = models.CharField('rol', max_length=1, choices=Role, default=Role.MEMBER)

    REQUIRED_FIELDS = ['email', 'first_name', 'last_name']  # createsuperuser da sorsun

    @property
    def vote_weight(self):
        return settings.FORUM['VOTE_WEIGHT'][self.role]

    @property
    def can_vote(self):
        min_age = timedelta(days=settings.FORUM['MIN_ACCOUNT_AGE_DAYS'])
        return self.is_active and timezone.now() - self.date_joined >= min_age
