from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models


class Hideable(models.Model):
    """Moderasyonla gizlenebilen içeriğin ortak atası: Comment, Topic, BaseProposal. Silmeden ayrı alan;
    veritabanından bir şey silinmez. Gizli içerik donar ve listelerden çıkar, metnini yalnızca sahibi ve
    yöneticiler görür. Bu uygulama comments, topics ve voting'i modellerde import etmez; döngü olmaz.
    """
    OWNER = 'author'  # içeriğin sahibi olan alan (öneride 'proposer')
    is_hidden = models.BooleanField('moderasyonla gizli', default=False)

    class Meta:
        abstract = True

    @property
    def owner_id(self):
        return getattr(self, f'{self.OWNER}_id')

    @property
    def owner(self):
        return getattr(self, self.OWNER)

    def hidden_from(self, user):
        """Gizli ve kullanıcı ne sahibi ne yönetici: metin yerine "moderasyonla gizlendi" yazılır."""
        return self.is_hidden and not (user.is_authenticated and (user.is_moderator or user.pk == self.owner_id))

    def set_hidden(self, hidden):
        """Gizler ya da gizlemeyi kaldırır; kaydı moderasyon görünümü yazar."""
        self.is_hidden = hidden
        self.save(update_fields=['is_hidden'])

    def can_be_reported_by(self, user):
        """Şikayet: oy hakkı gerekir (kural 1); kendi, gizli ya da silinmiş içerik şikayet edilmez."""
        return (user.is_authenticated and user.can_vote and self.owner_id != user.pk and not self.is_hidden
                and not getattr(self, 'is_deleted', False))


class ModAction(models.Model):
    """Herkese açık moderasyon kaydı. Yalnızca eklenir: değiştirilemez, silinemez; kayıttaki üyeler de
    silinemez (PROTECT). İçeriğin metni tutulmaz, yalnızca türü ve bağlantısı: gizli metin kayıtta görünmez.
    """
    class Kind(models.TextChoices):
        HIDE = 'hide', 'gizleme'
        UNHIDE = 'unhide', 'gizlemeyi kaldırma'
        BAN = 'ban', 'engelleme'
        UNBAN = 'unban', 'engeli kaldırma'
        CLOSE = 'close', 'hesap kapatma'
        REOPEN = 'reopen', 'hesabı yeniden açma'

    class Reason(models.TextChoices):  # "diğer" yok
        TROLL = 'troll', 'trollük'
        ABUSE = 'abuse', 'aşırı içerik'
        FAKE = 'fake', 'sahte hesap'

    moderator = models.ForeignKey(settings.AUTH_USER_MODEL, models.PROTECT, related_name='+', verbose_name='yönetici')
    user = models.ForeignKey(  # içerik işleminde sahibi; sahibi silinmiş içerikte boş
        settings.AUTH_USER_MODEL, models.PROTECT, null=True, related_name='mod_actions', verbose_name='etkilenen üye',
    )
    kind = models.CharField('işlem', max_length=10, choices=Kind)
    reason = models.CharField('gerekçe', max_length=10, choices=Reason)
    note = models.CharField('not', max_length=settings.FORUM['MOD_NOTE_MAX_LENGTH'])  # herkese açık, zorunlu
    content_type = models.ForeignKey(ContentType, models.PROTECT, null=True)  # yalnızca içerik işlemlerinde
    object_id = models.PositiveIntegerField(null=True)
    target = GenericForeignKey()
    until = models.DateTimeField('engel bitişi', null=True)
    created_at = models.DateTimeField('tarih', auto_now_add=True)

    class Meta:
        verbose_name = 'moderasyon kaydı'
        verbose_name_plural = 'moderasyon kayıtları'
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValueError('Moderasyon kaydı değiştirilemez.')
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError('Moderasyon kaydı silinemez.')


class Report(models.Model):
    """Şikayet: içerik kendiliğinden gizlenmez, yöneticinin kuyruğuna düşer. Şikayet edenin kimliği gizli:
    yalnızca "içerik başına tek şikayet" ve hız sınırı için tutulur; hiçbir sayfada ve admin'de görünmez.
    """
    content_type = models.ForeignKey(ContentType, models.CASCADE)
    object_id = models.PositiveIntegerField()
    target = GenericForeignKey()
    reporter = models.ForeignKey(settings.AUTH_USER_MODEL, models.CASCADE, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)
    is_open = models.BooleanField(default=True)  # gizleme ya da "şikayetleri kapat" kapatır

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['content_type', 'object_id', 'reporter'], name='icerik_basina_tek_sikayet'),
        ]
