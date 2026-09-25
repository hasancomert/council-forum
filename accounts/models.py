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
    is_moderator = models.BooleanField('yönetici', default=False)  # moderasyon sitede yapılır, admin'e girmez
    banned_until = models.DateTimeField('engel bitişi', null=True, blank=True)  # yalnızca moderasyonla değişir
    terms_accepted_at = models.DateTimeField('şartları kabul', null=True, editable=False)  # kayıtta; kurucuda boş
    deleted_at = models.DateTimeField('silinme', null=True, editable=False)  # hesap silindi: anonim

    REQUIRED_FIELDS = ['email', 'first_name', 'last_name']  # createsuperuser da sorsun

    def __str__(self):
        # Silinen hesabın takma adı hiçbir yerde görünmez: yorum, öneri ve moderasyon kaydı bunu yazar.
        return 'silinmiş üye' if self.deleted_at else self.username

    def anonymize(self):
        """Hesap silme (KVKK): kişisel bilgiler silinir, satır kalır. Gerçek silme karar oylarını CASCADE'le
        silip bitmiş oylamaların sonucunu değiştirir, moderasyon kaydı (PROTECT) da buna izin vermez.
        Takma ad ve e-posta benzersiz olmalı: kişiye ait olmayan, pk'den türeyen değerler yazılır.
        """
        self.username, self.email = f'silinmis-{self.pk}', f'{self.pk}@silinmis.invalid'
        self.first_name = self.last_name = ''
        self.set_unusable_password()  # öbür cihazlardaki oturumlar da düşer (oturum şifre özetine bağlı)
        self.is_active = self.is_moderator = False
        self.role, self.banned_until, self.terms_accepted_at = self.Role.MEMBER, None, None
        self.deleted_at = timezone.now()
        self.save()

    @property
    def vote_weight(self):
        return settings.FORUM['VOTE_WEIGHT'][self.role]

    @property
    def is_banned(self):
        # Süre dolunca engel kendiliğinden kalkar: alan temizlenmez, yalnızca tarihe bakılır.
        return self.banned_until is not None and self.banned_until > timezone.now()

    @property
    def can_post(self):
        """Yorum yazabilir mi: aktif ve engelsiz (hesap yaşı gerekmez)."""
        return self.is_active and not self.is_banned

    @property
    def can_vote(self):
        """Her türlü oy, öneri ve şikayet: ayrıca kural 1'deki hesap yaşı."""
        min_age = timedelta(days=settings.FORUM['MIN_ACCOUNT_AGE_DAYS'])
        return self.can_post and timezone.now() - self.date_joined >= min_age
