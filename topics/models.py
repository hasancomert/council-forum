from django.conf import settings
from django.db import models
from django.urls import reverse


class TopicQuerySet(models.QuerySet):
    def visible(self):
        # Görünürlüğün tek yeri: silinenleri ve üst konusu silinenleri eler.
        # 8. adımdaki moderasyon gizlemesi de buraya eklenecek.
        return self.filter(is_deleted=False).exclude(parent__is_deleted=True)


class Topic(models.Model):
    # Alt konu = parent'ı dolu konu. limit_choices_to hem admin listesini süzer hem de
    # full_clean()'de denetler: üst konu yalnızca ana konu olabilir (iki seviye).
    parent = models.ForeignKey(
        'self', models.PROTECT, null=True, blank=True, related_name='children',
        limit_choices_to={'parent': None}, verbose_name='üst konu',
    )
    title = models.CharField('başlık', max_length=200)
    description = models.TextField('açıklama', blank=True)
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, models.SET_NULL, null=True, blank=True, editable=False, verbose_name='açan',
    )
    created_at = models.DateTimeField('açılış tarihi', auto_now_add=True)
    is_closed = models.BooleanField('kapalı', default=False)
    is_deleted = models.BooleanField('silinmiş', default=False)

    objects = TopicQuerySet.as_manager()

    class Meta:
        verbose_name = 'konu'
        verbose_name_plural = 'konular'
        ordering = ['-created_at']

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse('topic', args=[self.pk])

    @property
    def is_locked(self):
        """Kendisi ya da üst konusu kapalı mı (alanlara yazılmaz, hesaplanır)."""
        return self.is_closed or (self.parent is not None and self.parent.is_closed)

    @property
    def is_visible(self):
        """visible() sorgusunun tek nesnelik karşılığı; ikisi birlikte güncellenir (8. adım)."""
        return not (self.is_deleted or (self.parent_id and self.parent.is_deleted))

    @property
    def is_open(self):
        """Kural 7: yeni yorum ve öneri kabul ediyor mu."""
        return self.is_visible and not self.is_locked
