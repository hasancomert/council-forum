from datetime import timedelta

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.db.models import Func, IntegerField, OuterRef, Subquery
from django.urls import reverse
from django.utils import timezone

from comments.models import Comment, Commentable, CommentVote, UpDownVote


def count_of(model, **filters):
    """Satır başına COUNT alt sorgusu: JOIN çoğaltması ve konu başına ayrı sorgu yok. Count değil
    düz Func: GROUP BY eklenmez, eşleşme yoksa da tek satır döner (NULL değil 0)."""
    return Subquery(model.objects.filter(**filters).order_by().values(n=Func('pk', function='COUNT')),
                    output_field=IntegerField())


SORTS = {'popular': ('-heat', '-created_at'), 'votes': ('-score', '-created_at'), 'new': ('-created_at',)}


class TopicQuerySet(models.QuerySet):
    def visible(self):
        # Görünürlüğün tek yeri: silinenleri ve üst konusu silinenleri eler, kapalıları elemez.
        # 8. adımdaki moderasyon gizlemesi de buraya eklenecek.
        return self.filter(is_deleted=False).exclude(parent__is_deleted=True)

    def ranked(self, sort):
        """Yorum sayısını (n_comments) ekler ve SORTS'a göre sıralar. heat ("en popüler") yalnızca
        o sıralamada hesaplanır: son POPULAR_DAYS günün yorumları ve oyları (yönüne bakılmaz)."""
        ct = ContentType.objects.get_for_model(self.model)
        on_topic = {'content_type': ct, 'object_id': OuterRef('pk'), 'is_deleted': False}
        qs = self.annotate(n_comments=count_of(Comment, **on_topic))
        if sort == 'popular':
            since = timezone.now() - timedelta(days=settings.FORUM['POPULAR_DAYS'])
            w = settings.FORUM['POPULAR_WEIGHTS']
            qs = qs.annotate(heat=w['comment'] * count_of(Comment, created_at__gte=since, **on_topic)
                             + w['vote'] * (count_of(CommentVote, voted_at__gte=since, comment__content_type=ct,
                                                     comment__object_id=OuterRef('pk'))
                                            + count_of(TopicVote, voted_at__gte=since, topic=OuterRef('pk'))))
        return qs.order_by(*SORTS[sort])


class Topic(Commentable):
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
    score = models.IntegerField('puan', default=0, editable=False)  # ▲ − ▼, yalnızca UpDownVote.cast() değiştirir

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

    def can_be_voted_by(self, user):
        return user.can_vote and self.author_id != user.pk and self.is_open


class TopicVote(UpDownVote):
    # "En çok oy" sıralamasının verisi; yorum oyuyla aynı kurallar. Kimin ne verdiği gizli: admin'de yok.
    TARGET = 'topic'
    topic = models.ForeignKey(Topic, models.CASCADE, related_name='votes')

    class Meta:
        constraints = [models.UniqueConstraint(fields=['topic', 'voter'], name='konu_tek_oy')]
