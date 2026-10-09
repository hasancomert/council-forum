from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey, GenericRelation
from django.contrib.contenttypes.models import ContentType
from django.db import models, transaction
from django.db.models import F, OuterRef, Subquery

from config.errors import RuleError
from moderation.models import Hideable


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


class Comment(Hideable):
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
    score = models.IntegerField('puan', default=0, editable=False)  # ▲ − ▼, yalnızca UpDownVote.cast() değiştirir

    class Meta:
        verbose_name = 'yorum'
        verbose_name_plural = 'yorumlar'
        indexes = [models.Index(fields=['content_type', 'object_id'])]

    def __str__(self):
        return self.body[:50]

    def get_absolute_url(self):
        return f'{self.target.get_absolute_url()}#c{self.pk}'

    def can_be_voted_by(self, user):
        return (user.can_vote and self.author_id != user.pk and not self.is_deleted and not self.is_hidden
                and self.target.is_open)

    def soft_delete(self):
        """Yazarın silmesi (site ve API): yerinde "Bu yorum silindi" yazar, yanıtlar kalır, geri alınmaz. Hedef
        kapalı ya da yorum gizli olsa da serbest. Metin kalır (kural 7); hesap silmede üye isterse boşaltılır.
        """
        self.is_deleted = True
        self.save(update_fields=['is_deleted'])


def vote_block(user):
    """▲/▼ verilemiyorsa kullanıcıya bağlı nedeni (düğme soluk, üzerine gelince yazar), verebiliyorsa ''.
    Hedefe bağlı nedenleri (kendi içeriği, kapalı hedef) çağıran ekler.
    """
    if not user.is_authenticated:
        return 'Oy vermek için giriş yap'
    if user.is_banned:
        return 'Engelin sürerken oy veremezsin'
    if not user.can_vote:
        return f"Oy vermek için hesabın en az {settings.FORUM['MIN_ACCOUNT_AGE_DAYS']} günlük olmalı"
    return ''


class UpDownVote(models.Model):
    """▲/▼ oyunun ortak atası (CommentVote, topics.TopicVote). Karar oyu (voting.Vote) değil: ağırlık
    yok (kural 2), puan herkese açık ve anında güncellenir, aktif üye sayımına girmez.
    Alt sınıf hedef FK'yi tanımlar, adını TARGET'a yazar; hedefte `score` ve `can_be_voted_by(user)` olmalı.
    """
    TARGET = None
    voter = models.ForeignKey(settings.AUTH_USER_MODEL, models.CASCADE)
    value = models.SmallIntegerField(choices=[(1, '▲'), (-1, '▼')])
    voted_at = models.DateTimeField(auto_now=True)  # "en popüler" penceresi; yön değişince de güncellenir

    class Meta:
        abstract = True

    @classmethod
    @transaction.atomic
    def cast(cls, target, voter, value):
        """▲ (1) ya da ▼ (−1); aynı tuşa ikinci basış oyu geri alır. Yeni oyu (1, −1, 0) döndürür."""
        if isinstance(value, bool) or value not in (1, -1):  # JSON'daki true da 1 sayılırdı (True == 1)
            raise RuleError('Geçersiz oy.')
        # Hedef satırı kilitle: aynı hedefe eşzamanlı oylar (ör. çift tık) sırayla işlensin, puan kaymasın.
        target = type(target).objects.select_for_update().get(pk=target.pk)
        if not target.can_be_voted_by(voter):
            raise RuleError('Buna oy verilemez.')
        key = {cls.TARGET: target, 'voter': voter}
        old = cls.objects.filter(**key).first()
        old_value = old.value if old else 0
        new = 0 if value == old_value else value
        if new:
            cls.objects.update_or_create(**key, defaults={'value': new})
        else:  # aynı tuşa ikinci basış: eski oy vardı
            old.delete()
        type(target).objects.filter(pk=target.pk).update(score=F('score') + new - old_value)  # atomik, sayım gerekmez
        return new

    @classmethod
    def withdraw_all(cls, voter):
        """Hesap kapatma: kullanıcının bütün oylarını siler; hedeflerin puanı tek UPDATE ile düzelir
        (hedef başına en fazla bir oy olduğundan alt sorgu tek değer döndürür).
        """
        mine = cls.objects.filter(voter=voter)
        target_model = cls._meta.get_field(cls.TARGET).related_model
        target_model.objects.filter(pk__in=mine.values(cls.TARGET)).update(
            score=F('score') - Subquery(mine.filter(**{cls.TARGET: OuterRef('pk')}).values('value')))
        mine.delete()

    @staticmethod
    def withdraw_everywhere(voter):
        """Hesap kapatma: üyenin her tür ▲/▼ oyu (yorum, konu). Moderasyon oy türlerini tek tek bilmez; yeni bir
        oylanabilir içerik türü (yeni alt sınıf) kendiliğinden girer.
        """
        for model in UpDownVote.__subclasses__():
            model.withdraw_all(voter)


class CommentVote(UpDownVote):
    TARGET = 'comment'
    comment = models.ForeignKey(Comment, models.CASCADE, related_name='votes')

    class Meta:
        constraints = [models.UniqueConstraint(fields=['comment', 'voter'], name='yorum_tek_oy')]
