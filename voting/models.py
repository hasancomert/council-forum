import math
from datetime import timedelta

from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey, GenericRelation
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.utils import timezone

from accounts.models import User
from topics.models import Topic


class Vote(models.Model):
    # GenericForeignKey: Java'daki tek bir yabancı anahtarla değil, content_type+object_id
    # çiftiyle herhangi bir modele işaret eden "polimorfik" ilişki. Böylece tüm öneri
    # tiplerinin oyu tek tabloda tutulur, oy/ağırlık mantığı tekrar etmez.
    class Choice(models.TextChoices):
        YES = 'yes', 'Evet'
        NO = 'no', 'Hayır'

    content_type = models.ForeignKey(ContentType, models.CASCADE)
    object_id = models.PositiveIntegerField()
    proposal = GenericForeignKey('content_type', 'object_id')

    voter = models.ForeignKey(settings.AUTH_USER_MODEL, models.CASCADE, verbose_name='oy veren')
    choice = models.CharField('oy', max_length=3, choices=Choice)
    weight = models.PositiveSmallIntegerField('ağırlık')  # oy anındaki ağırlık, rol sonradan değişse de sabit kalır
    voted_at = models.DateTimeField('oy tarihi', auto_now=True)  # kural 6: oy değiştirilebilir, her değişiklikte güncellenir

    class Meta:
        verbose_name = 'oy'
        verbose_name_plural = 'oylar'
        constraints = [
            models.UniqueConstraint(fields=['content_type', 'object_id', 'voter'], name='tek_kullanici_tek_oy'),
        ]

    def __str__(self):
        return f'{self.voter} -> {self.proposal}: {self.choice}'

    @classmethod
    def cast(cls, *, proposal, voter, choice):
        """Oy ver/değiştir (upsert). Kural 1 ve 6'daki oy hakkı ve süre denetimini burada yapar."""
        if not proposal.accepts_votes():
            raise ValueError('Bu öneri şu anda oylanamıyor.')
        if not voter.can_vote:
            raise ValueError('Bu kullanıcının oy hakkı yok.')
        weight = voter.vote_weight if proposal.WEIGHTED else 1
        vote, _ = cls.objects.update_or_create(
            content_type=ContentType.objects.get_for_model(proposal), object_id=proposal.pk, voter=voter,
            defaults={'choice': choice, 'weight': weight},
        )
        return vote


class BaseProposal(models.Model):
    """Ortak öneri iskeleti. Tip başına ayrı model kullanılıyor (Vote hariç), böylece her
    önerinin kendi hedef/payload alanları olur; oy/ağırlık/süre mantığı burada tekrar etmez.
    """
    class Status(models.TextChoices):
        VOTING = 'voting', 'Oylanıyor'
        ACCEPTED = 'accepted', 'Kabul edildi'
        REJECTED = 'rejected', 'Reddedildi'
        APPLIED = 'applied', 'Uygulandı'

    WEIGHTED = True  # kural 2: yalnızca B statüsü oylamasında (ExpertProposal) False
    VOTING_DAYS_SETTING = 'PROPOSAL_VOTING_DAYS'  # kural 5: RequestProposal kendi süresini hesaplar
    DUPLICATE_FIELDS = ()  # kural 8: "aynı öneri" bu alanların eşleşmesiyle belirlenir

    proposer = models.ForeignKey(
        settings.AUTH_USER_MODEL, models.SET_NULL, null=True, editable=False, verbose_name='öneren',
    )
    created_at = models.DateTimeField('açılış tarihi', auto_now_add=True)
    voting_ends_at = models.DateTimeField('oylama bitişi')
    status = models.CharField('durum', max_length=10, choices=Status, default=Status.VOTING)
    applied_at = models.DateTimeField('uygulanma tarihi', null=True, blank=True)

    votes = GenericRelation(Vote, content_type_field='content_type', object_id_field='object_id')

    class Meta:
        abstract = True
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        if self._state.adding and not self.voting_ends_at:
            self.voting_ends_at = timezone.now() + timedelta(days=settings.FORUM[self.VOTING_DAYS_SETTING])
        super().save(*args, **kwargs)

    def accepts_votes(self):
        return self.status == self.Status.VOTING and timezone.now() < self.voting_ends_at

    @property
    def results_visible(self):
        return self.status != self.Status.VOTING  # kural 6: sonuç bitene kadar gizli

    @property
    def participant_count(self):
        return self.votes.count()

    def _accepted(self, votes):
        # kural 4: ağırlıklı oyların yarısından fazlası evet, eşitlikte ret.
        yes = sum(v.weight for v in votes if v.choice == Vote.Choice.YES)
        no = sum(v.weight for v in votes if v.choice == Vote.Choice.NO)
        return yes > no

    def apply(self):
        """Kabul edilen öneriyi hedefe uygular. Uygulanamazsa (hedefin durumu artık uygun
        değilse) False döner; öneri 'kabul' durumunda kalır, bir sonraki finalize() yeniden dener.
        """
        raise NotImplementedError

    def finalize(self):
        """Kural 3 ve 4'ü uygular; lazy kontrol (sayfa ziyareti) ve finalize_proposals
        komutu tarafından çağrılır. Süresi gelmemiş öneriye dokunmaz.
        """
        if self.status == self.Status.VOTING:
            if timezone.now() < self.voting_ends_at:
                return
            votes = list(self.votes.all())
            if len(votes) < required_quorum() or not self._accepted(votes):
                self.status = self.Status.REJECTED
                self.save(update_fields=['status'])
                return
            self.status = self.Status.ACCEPTED
            self.save(update_fields=['status'])
        if self.status == self.Status.ACCEPTED:
            # kabul edilen öneri uygulanmadan önce hedefin güncel durumu burada denetlenir (apply()).
            if self.apply():
                self.status = self.Status.APPLIED
                self.applied_at = timezone.now()
                self.save(update_fields=['status', 'applied_at'])

    @classmethod
    def has_recent_rejection(cls, **field_values):
        """Kural 8: aynı tip+hedef+içerikli öneri reddedildiyse REJECTED_COOLDOWN_DAYS gün
        yeniden açılamaz. field_values, DUPLICATE_FIELDS ile aynı adları taşımalı.
        """
        if not cls.DUPLICATE_FIELDS:
            return False
        cutoff = timezone.now() - timedelta(days=settings.FORUM['REJECTED_COOLDOWN_DAYS'])
        filters = {field: field_values[field] for field in cls.DUPLICATE_FIELDS}
        return cls.objects.filter(status=cls.Status.REJECTED, created_at__gte=cutoff, **filters).exists()


class TopicOpenProposal(BaseProposal):
    # parent boşsa yeni ana konu önerisi (kural 9: kuruluştan sonra bu da oylamayla).
    parent = models.ForeignKey(
        Topic, models.PROTECT, null=True, blank=True,
        limit_choices_to={'parent': None}, verbose_name='üst konu',
    )
    title = models.CharField('başlık', max_length=200)
    description = models.TextField('açıklama', blank=True)

    DUPLICATE_FIELDS = ('parent_id', 'title')

    class Meta:
        verbose_name = 'konu açma önerisi'
        verbose_name_plural = 'konu açma önerileri'

    def __str__(self):
        return f'Aç: {self.title}'

    def apply(self):
        if self.parent_id and (self.parent.is_deleted or self.parent.is_closed):
            return False  # üst konu artık kapalı/silinmiş, yeni alt konu açılamaz
        Topic.objects.create(
            parent=self.parent, title=self.title, description=self.description, author=self.proposer,
        )
        return True


class TopicEditProposal(BaseProposal):
    topic = models.ForeignKey(Topic, models.PROTECT, verbose_name='konu')
    new_title = models.CharField('yeni başlık', max_length=200)
    new_description = models.TextField('yeni açıklama', blank=True)

    DUPLICATE_FIELDS = ('topic_id', 'new_title', 'new_description')

    class Meta:
        verbose_name = 'konu düzenleme önerisi'
        verbose_name_plural = 'konu düzenleme önerileri'

    def __str__(self):
        return f'Düzenle: {self.topic}'

    def apply(self):
        self.topic.title = self.new_title
        self.topic.description = self.new_description
        self.topic.save(update_fields=['title', 'description'])
        return True


class TopicCloseProposal(BaseProposal):
    topic = models.ForeignKey(Topic, models.PROTECT, verbose_name='konu')

    DUPLICATE_FIELDS = ('topic_id',)

    class Meta:
        verbose_name = 'konu kapatma önerisi'
        verbose_name_plural = 'konu kapatma önerileri'

    def __str__(self):
        return f'Kapat: {self.topic}'

    def apply(self):
        if self.topic.is_deleted:
            return False  # silinmiş konu kapatılamaz
        if not self.topic.is_closed:
            self.topic.is_closed = True
            self.topic.save(update_fields=['is_closed'])
        return True


class TopicDeleteProposal(BaseProposal):
    topic = models.ForeignKey(Topic, models.PROTECT, verbose_name='konu')

    DUPLICATE_FIELDS = ('topic_id',)

    class Meta:
        verbose_name = 'konu silme önerisi'
        verbose_name_plural = 'konu silme önerileri'

    def __str__(self):
        return f'Sil: {self.topic}'

    def apply(self):
        if not self.topic.is_deleted:
            self.topic.is_deleted = True
            self.topic.save(update_fields=['is_deleted'])
        return True


class TopicUndoProposal(BaseProposal):
    class Action(models.TextChoices):
        REOPEN = 'reopen', 'Kapatmayı geri al'
        RESTORE = 'restore', 'Silmeyi geri al'

    topic = models.ForeignKey(Topic, models.PROTECT, verbose_name='konu')
    action = models.CharField('işlem', max_length=10, choices=Action)

    DUPLICATE_FIELDS = ('topic_id', 'action')

    class Meta:
        verbose_name = 'geri alma önerisi'
        verbose_name_plural = 'geri alma önerileri'

    def __str__(self):
        return f'{self.get_action_display()}: {self.topic}'

    def apply(self):
        if self.action == self.Action.REOPEN:
            if self.topic.is_closed:
                self.topic.is_closed = False
                self.topic.save(update_fields=['is_closed'])
        elif self.topic.is_deleted:
            self.topic.is_deleted = False
            self.topic.save(update_fields=['is_deleted'])
        return True


class ExpertProposal(BaseProposal):
    class Action(models.TextChoices):
        GRANT = 'grant', 'B statüsü ver'
        REVOKE = 'revoke', 'B statüsünü geri al'

    WEIGHTED = False  # kural 2: bu oylamada herkesin oyu 1

    target_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, models.PROTECT, related_name='expert_proposals', verbose_name='üye',
    )
    action = models.CharField('işlem', max_length=10, choices=Action)
    reason = models.TextField('gerekçe')

    DUPLICATE_FIELDS = ('target_user_id', 'action')

    class Meta:
        verbose_name = 'bilirkişilik önerisi'
        verbose_name_plural = 'bilirkişilik önerileri'

    def __str__(self):
        return f'{self.get_action_display()}: {self.target_user}'

    def _accepted(self, votes):
        # kural 2: 2/3 evet gerekir (ondalık hatasından kaçınmak için çapraz çarpım).
        yes = sum(1 for v in votes if v.choice == Vote.Choice.YES)
        num, den = settings.FORUM['EXPERT_APPROVAL_NUM'], settings.FORUM['EXPERT_APPROVAL_DEN']
        return yes * den >= len(votes) * num

    def apply(self):
        new_role = User.Role.EXPERT if self.action == self.Action.GRANT else User.Role.MEMBER
        if self.target_user.role != new_role:
            self.target_user.role = new_role
            self.target_user.save(update_fields=['role'])
        return True


class RequestProposal(BaseProposal):
    """Kural 5: konudan doğan istek, 3 gün tartışma + 3 gün oylama. Uygulanacak bir sistem
    işlemi yok; kabul edilmesi başlı başına sonuçtur (apply() hemen True döner).
    """
    topic = models.ForeignKey(Topic, models.PROTECT, related_name='requests', verbose_name='ilgili konu')
    title = models.CharField('başlık', max_length=200)
    content = models.TextField('içerik')
    discussion_ends_at = models.DateTimeField('tartışma bitişi')

    DUPLICATE_FIELDS = ('topic_id', 'title', 'content')

    class Meta:
        verbose_name = 'istek'
        verbose_name_plural = 'istekler'

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if self._state.adding and not self.discussion_ends_at:
            self.discussion_ends_at = timezone.now() + timedelta(days=settings.FORUM['REQUEST_DISCUSSION_DAYS'])
            self.voting_ends_at = self.discussion_ends_at + timedelta(days=settings.FORUM['REQUEST_VOTING_DAYS'])
        super().save(*args, **kwargs)

    def accepts_votes(self):
        return super().accepts_votes() and timezone.now() >= self.discussion_ends_at

    def apply(self):
        return True


PROPOSAL_MODELS = (
    TopicOpenProposal, TopicEditProposal, TopicCloseProposal, TopicDeleteProposal,
    TopicUndoProposal, ExpertProposal, RequestProposal,
)


def open_proposal_count(user):
    """Kural 8: kişi başı en fazla 3 açık öneri, tüm tipler toplanarak sayılır."""
    return sum(model.objects.filter(proposer=user, status=BaseProposal.Status.VOTING).count() for model in PROPOSAL_MODELS)


def active_member_count():
    """Kural 3: son 30 günde oy kullanmış veya konu paylaşmış üye sayısı."""
    since = timezone.now() - timedelta(days=30)
    voter_ids = Vote.objects.filter(voted_at__gte=since).values('voter_id')
    author_ids = Topic.objects.filter(created_at__gte=since).values('author_id')
    return User.objects.filter(models.Q(pk__in=voter_ids) | models.Q(pk__in=author_ids)).distinct().count()


def required_quorum():
    """Kural 3: yeter sayı, aktif üyelerin %QUORUM_PERCENT'i, en az QUORUM_MIN."""
    total = active_member_count()
    return max(settings.FORUM['QUORUM_MIN'], math.ceil(total * settings.FORUM['QUORUM_PERCENT'] / 100))
