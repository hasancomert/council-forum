from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey, GenericRelation
from django.contrib.contenttypes.models import ContentType
from django.db import models


class Commentable(models.Model):
    """Yorum alabilen modellerin ortak atası (Java'daki interface gibi): Topic ve BaseProposal.
    Bu uygulama topics ve voting'i import etmez; döngüsel import olmaz.
    """
    comments = GenericRelation('comments.Comment')  # tabloya sütun eklemez, migration gerekmez

    class Meta:
        abstract = True

    @property
    def is_open(self):
        """Yeni yorum, yanıt, düzenleme ve yorum oyu kabul ediyor mu; alt sınıf tanımlar."""
        raise NotImplementedError


class Comment(models.Model):
    content_type = models.ForeignKey(ContentType, models.CASCADE)
    object_id = models.PositiveIntegerField()
    target = GenericForeignKey()
    # Tek seviye: yanıta verilen yanıt da ana yoruma bağlanır (görünümde).
    parent = models.ForeignKey(
        'self', models.PROTECT, null=True, blank=True, related_name='replies', verbose_name='yanıtlanan',
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, models.SET_NULL, null=True, editable=False, verbose_name='yazar',
    )
    body = models.TextField('yorum', max_length=settings.FORUM['COMMENT_MAX_LENGTH'])  # sınırı form denetler
    created_at = models.DateTimeField('tarih', auto_now_add=True)
    edited_at = models.DateTimeField('düzenlenme', null=True, editable=False)
    is_deleted = models.BooleanField('silinmiş', default=False)  # yumuşak silme, metin kalır (kural 7)
    score = models.IntegerField('puan', default=0, editable=False)  # ▲ − ▼, yalnızca CommentVote.cast() değiştirir

    class Meta:
        verbose_name = 'yorum'
        verbose_name_plural = 'yorumlar'
        indexes = [models.Index(fields=['content_type', 'object_id'])]

    def __str__(self):
        return self.body[:50]

    def get_absolute_url(self):
        return f'{self.target.get_absolute_url()}#c{self.pk}'
