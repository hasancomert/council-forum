from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey, GenericRelation
from django.contrib.contenttypes.models import ContentType
from django.db import models, transaction
from django.db.models import F


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


class CommentVote(models.Model):
    # Karar oyu (voting.Vote) değil: ağırlık yok (kural 2), puan herkese açık ve anında güncellenir,
    # aktif üye sayımına girmez. Gerçek ForeignKey olduğu için model de sorgu da daha basit.
    comment = models.ForeignKey(Comment, models.CASCADE, related_name='votes')
    voter = models.ForeignKey(settings.AUTH_USER_MODEL, models.CASCADE)
    value = models.SmallIntegerField(choices=[(1, '▲'), (-1, '▼')])

    class Meta:
        constraints = [models.UniqueConstraint(fields=['comment', 'voter'], name='yorum_tek_oy')]

    @classmethod
    @transaction.atomic
    def cast(cls, comment, voter, value):
        """▲ (1) ya da ▼ (−1); aynı tuşa ikinci basış oyu geri alır. Yeni oyu (1, −1, 0) döndürür."""
        if value not in (1, -1):
            raise ValueError('Geçersiz oy.')
        # Yorum satırını kilitle: aynı yoruma eşzamanlı oylar (ör. çift tık) sırayla işlensin, puan kaymasın.
        comment = Comment.objects.select_for_update().get(pk=comment.pk)
        if not voter.can_vote or comment.author_id == voter.pk or comment.is_deleted or not comment.target.is_open:
            raise ValueError('Bu yoruma oy verilemez.')
        old = cls.objects.filter(comment=comment, voter=voter).first()
        old_value = old.value if old else 0
        new = 0 if value == old_value else value
        if new:
            cls.objects.update_or_create(comment=comment, voter=voter, defaults={'value': new})
        elif old:
            old.delete()
        Comment.objects.filter(pk=comment.pk).update(score=F('score') + new - old_value)  # atomik, sayım gerekmez
        return new
