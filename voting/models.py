import math
from datetime import timedelta
from operator import attrgetter

from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey, GenericRelation
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.db import models, transaction
from django.db.models import Count, Q, Sum
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from comments.models import Comment, Commentable
from config.errors import RuleError
from moderation.models import Hideable
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
        # Kural 6: kim ne oy verdi hiçbir yerde görünmesin (Django'nun silme onay sayfası da bunu yazar).
        return f'oy #{self.pk}'

    @classmethod
    def cast(cls, *, proposal, voter, choice):
        """Oy ver/değiştir (upsert). Kural 1 ve 6'daki oy hakkı ve süre denetimini burada yapar."""
        if choice not in cls.Choice.values:
            raise RuleError('Geçersiz oy.')
        if not proposal.accepts_votes():
            raise RuleError('Bu öneri şu anda oylanamıyor.')
        if not voter.can_vote:
            raise RuleError('Bu kullanıcının oy hakkı yok.')
        weight = voter.vote_weight if proposal.WEIGHTED else 1
        vote, _ = cls.objects.update_or_create(
            content_type=ContentType.objects.get_for_model(proposal), object_id=proposal.pk, voter=voter,
            defaults={'choice': choice, 'weight': weight},
        )
        return vote


PROPOSALS = {}  # Registry: URL'deki tip adı (SLUG) → öneri modeli. Tipler tanımlanırken kendini kaydeder.


class ProposalQuerySet(models.QuerySet):
    """Önerilerin ortak sorguları (Repository): "süren" ve "vadesi gelen" tanımı tek yerde."""

    def running(self):
        """Oylaması (istekte tartışması) süren öneriler: kural 8'deki açık öneri, panel, rozetler."""
        return self.filter(status=BaseProposal.Status.VOTING, voting_ends_at__gt=timezone.now())

    def due(self):
        """Sonuçlanacaklar: süresi dolmuş ama sonuçlanmamış, ya da kabul edilip uygulanması yarıda kalmış."""
        return self.filter(Q(status=BaseProposal.Status.VOTING, voting_ends_at__lte=timezone.now())
                           | Q(status=BaseProposal.Status.ACCEPTED))


class BaseProposal(Commentable, Hideable):
    """Ortak öneri iskeleti. Tip başına ayrı model kullanılıyor (Vote hariç), böylece her
    önerinin kendi hedef/payload alanları olur; oy/ağırlık/süre mantığı burada tekrar etmez.
    Template Method: finalize() ve clean() akışı sabit; tipe göre değişen adımlar alt sınıfın kancaları
    (check_target, prefill, _accepted, apply). Yeni tip yalnızca bir alt sınıftır (+ göç): kayıt, URL, form,
    admin, panel, öneri sayfası, API ve konu sayfasındaki bağlantı kendiliğinden gelir.
    """
    class Status(models.TextChoices):
        VOTING = 'voting', 'Oylanıyor'
        ACCEPTED = 'accepted', 'Kabul edildi'
        REJECTED = 'rejected', 'Reddedildi'
        APPLIED = 'applied', 'Uygulandı'
        # Kabul edildi ama hedef artık uygun değildi (ör. üst konu kapandı): beklemez, sonuç budur.
        FAILED = 'failed', 'Uygulanamadı'
        # Moderasyon: gizlenen ya da önereni kapatılan süren öneri. finalize() atlar. İptal ve uygulanamadı
        # açık öneri sayısına ve 30 günlük ret yasağına girmez (ikisi yalnızca VOTING/REJECTED'e bakar).
        CANCELLED = 'cancelled', 'İptal edildi'

    OWNER = 'proposer'
    in_discussion = False  # yalnızca istekte tartışma evresi var (RequestProposal property ile ezer)
    SLUG = ''  # URL'deki tip adı; tanımlayan sınıf PROPOSALS'a kaydolur
    TARGET = None  # formda URL'den gelen konunun yazılacağı alan (TopicProposal: 'topic', konu açma: 'parent')
    LINK = ''  # konu sayfasındaki öneri bağlantısı (boşsa yok); MORE: "Diğer öneriler"in içinde
    MORE = False
    FORM_FIELDS = ()  # öneri formunda kullanıcının doldurduğu alanlar
    WEIGHTED = True  # kural 2: yalnızca B statüsü oylamasında (ExpertProposal) False
    DUPLICATE_FIELDS = ()  # kural 8: "aynı öneri" bu alanların eşleşmesiyle belirlenir

    proposer = models.ForeignKey(
        settings.AUTH_USER_MODEL, models.SET_NULL, null=True, editable=False, verbose_name='öneren',
    )
    created_at = models.DateTimeField('açılış tarihi', auto_now_add=True)
    voting_ends_at = models.DateTimeField('oylama bitişi')
    status = models.CharField('durum', max_length=10, choices=Status, default=Status.VOTING)
    quorum = models.PositiveIntegerField('yeter sayı', null=True, editable=False)  # sonuçlanma anındaki değer
    applied_at = models.DateTimeField('uygulanma tarihi', null=True, blank=True)

    votes = GenericRelation(Vote, content_type_field='content_type', object_id_field='object_id')

    objects = ProposalQuerySet.as_manager()

    class Meta:
        abstract = True

    def __init_subclass__(cls, **kwargs):
        # Kendini kaydeden Registry: SLUG'ı olan her somut tip PROPOSALS'a girer (soyut ara sınıfların SLUG'ı yok).
        super().__init_subclass__(**kwargs)
        if 'SLUG' in cls.__dict__:
            if cls.SLUG in PROPOSALS:
                raise ImproperlyConfigured(f'{cls.SLUG!r} öneri tipi zaten kayıtlı: {PROPOSALS[cls.SLUG].__name__}')
            PROPOSALS[cls.SLUG] = cls

    def save(self, *args, **kwargs):
        if self._state.adding and not self.voting_ends_at:
            self.voting_ends_at = timezone.now() + timedelta(days=settings.FORUM['PROPOSAL_VOTING_DAYS'])
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse('proposal', args=[self.SLUG, self.pk])

    @property
    def kind(self):
        return self._meta.verbose_name  # şablonlar _meta'ya erişemez

    @property
    def deadline(self):
        """İçinde bulunulan evrenin bitişi (istekte tartışma sürerken oylamanın başlangıcı: RequestProposal ezer)."""
        return self.voting_ends_at

    @property
    def target(self):
        """URL'den gelen hedef konu (TARGET alanı); yoksa None."""
        return getattr(self, self.TARGET) if self.TARGET else None

    @property
    def target_label(self):
        return self._meta.get_field(self.TARGET).verbose_name if self.TARGET else ''

    def details(self):
        """Önerinin kendi alanları [(etiket, değer)]: başlık, açıklama, işlem, üye, gerekçe… Öneri sayfası ve API
        aynı listeyi gösterir, yeni tipin alanları kendiliğinden görünür. Ortak alanlar, hedef, tarihler ve boşlar hariç.
        """
        common = {f.name for f in BaseProposal._meta.fields} | {'id', self.TARGET}
        out = []
        for f in self._meta.concrete_fields:
            if f.name not in common and not isinstance(f, models.DateTimeField):
                value = getattr(self, f'get_{f.name}_display')() if f.choices else getattr(self, f.name)
                if value:
                    out.append((f.verbose_name, str(value)))
        return out

    @classmethod
    def targets(cls):
        """URL'deki konunun arandığı küme: öneri yalnızca görünür konuya açılır (gizli içerik forma dolmasın)."""
        return Topic.objects.visible()

    @classmethod
    def offered_for(cls, topic):
        """Konu sayfasında bu tipin bağlantısı çıksın mı: tipin kendi hedef denetimi (check_target) boş bir öneriyle
        denenir; kural ikinci kez yazılmaz.
        """
        if not (cls.LINK and cls.TARGET):
            return False
        proposal = cls(**{cls.TARGET: topic})
        proposal.prefill()
        try:
            proposal.check_target()
        except ValidationError:
            return False
        return True

    @property
    def is_open(self):
        """Oylama bitene kadar açık (istekte tartışma + oylama): yorum ve yorum oyu buna bakar."""
        return self.status == self.Status.VOTING and timezone.now() < self.voting_ends_at

    def accepts_votes(self):
        return self.is_open

    @property
    def results_visible(self):
        # Kural 6: sonuç bitene kadar gizli; iptal edilen oylama hiç bitmediği için ara sonucu da açıklanmaz.
        return self.status not in (self.Status.VOTING, self.Status.CANCELLED)

    def set_hidden(self, hidden):
        """Süren öneri gizlenince iptal olur; gizleme kaldırılınca iptal kalır (oylama süresi geri gelmez)."""
        if hidden:
            self.finalize()  # süresi dolmuşsa önce sonuçlansın: bitmiş oylama iptal edilmez
            type(self).objects.filter(pk=self.pk, status=self.Status.VOTING).update(status=self.Status.CANCELLED)
            self.refresh_from_db(fields=['status'])
        super().set_hidden(hidden)

    @property
    def participant_count(self):
        return self.votes.count()

    def tally(self):
        """Ağırlıklı evet/hayır toplamı ve katılımcı sayısı, tek sorguda."""
        return self.votes.aggregate(
            yes=Sum('weight', filter=Q(choice=Vote.Choice.YES), default=0),
            no=Sum('weight', filter=Q(choice=Vote.Choice.NO), default=0),
            count=Count('pk'),
        )

    def _accepted(self, t):
        return t['yes'] > t['no']  # kural 4: ağırlıklı oyların yarısından fazlası evet, eşitlikte ret

    def apply(self):
        """Kabul edilen öneriyi hedefe uygular. Hedefin durumu artık uygun değilse hiçbir şeyi
        değiştirmeden False döner; öneri 'uygulanamadı' diye sonuçlanır.
        """
        raise NotImplementedError

    def finalize(self):
        """Kural 3 ve 4'ü uygular; lazy kontrol (sayfa ziyareti) ve finalize_proposals
        komutu tarafından çağrılır. Süresi gelmemiş öneriye dokunmaz.
        """
        now = timezone.now()
        if self.status == self.Status.VOTING:
            if now < self.voting_ends_at:
                return
            t, quorum = self.tally(), required_quorum()
            status = self.Status.ACCEPTED if t['count'] >= quorum and self._accepted(t) else self.Status.REJECTED
            # Koşullu UPDATE: iki finalize() aynı anda çalışırsa (sayfa ziyareti + komut) yalnızca biri yazar.
            type(self).objects.filter(pk=self.pk, status=self.Status.VOTING).update(status=status, quorum=quorum)
            self.refresh_from_db(fields=['status', 'quorum'])
        if self.status == self.Status.ACCEPTED:
            with transaction.atomic():
                # Önce 'uygulandı' diye işaretle ki öneri iki kez uygulanmasın (ör. aynı konu iki kez açılmasın).
                claimed = type(self).objects.filter(pk=self.pk, status=self.Status.ACCEPTED).update(
                    status=self.Status.APPLIED, applied_at=now)
                if claimed and not self.apply():  # hedef uygun değil: bekletmeden sonuçlanır
                    type(self).objects.filter(pk=self.pk).update(status=self.Status.FAILED, applied_at=None)
            self.refresh_from_db(fields=['status', 'applied_at'])

    def clean(self):
        """ModelForm ve admin bunu kendiliğinden çağırır: yeni öneri denetimlerinin tek yeri."""
        if not self._state.adding:
            return
        forum = settings.FORUM
        if not self.proposer.can_vote:  # öneren formdan önce yazılır (voting.views.new_form)
            age = f"Öneri açmak için hesabın en az {forum['MIN_ACCOUNT_AGE_DAYS']} günlük olmalı."
            raise ValidationError('Engelin sürerken öneri açamazsın.' if self.proposer.is_banned else age)
        if open_proposal_count(self.proposer) >= forum['MAX_OPEN_PROPOSALS']:
            raise ValidationError(f"Aynı anda en fazla {forum['MAX_OPEN_PROPOSALS']} açık önerin olabilir.")
        self.check_target()
        if self.is_duplicate():
            raise ValidationError(
                f"Bu önerinin aynısı oylamada ya da son {forum['REJECTED_COOLDOWN_DAYS']} gün içinde reddedildi.")

    def prefill(self):
        """Öneri formunun başlangıç değerleri; hedef atandıktan sonra çağrılır."""

    def check_target(self):
        """Tipe göre hedef denetimi: hedef bu öneriyi alamıyorsa ValidationError (konu sayfasındaki bağlantılar da
        buna bakar: offered_for)."""

    def is_duplicate(self):
        """Kural 8: aynısı oylamada mı, ya da reddedilmesinin üzerinden bekleme süresi geçmedi mi.
        Bekleme süresi reddedilme anından (voting_ends_at) sayılır.
        """
        cutoff = timezone.now() - timedelta(days=settings.FORUM['REJECTED_COOLDOWN_DAYS'])
        same = type(self).objects.filter(**{f: getattr(self, f) for f in self.DUPLICATE_FIELDS})
        return same.filter(
            Q(status=self.Status.VOTING) | Q(status=self.Status.REJECTED, voting_ends_at__gte=cutoff),
        ).exists()


class TopicProposal(BaseProposal):
    """Var olan bir konuya yönelik öneriler: düzenleme, kapatma, silme, geri alma, istek. Konu alanı ve denetimi
    yalnızca bunlarda (ISP): konu açma önerisinin üst konusu isteğe bağlı, bilirkişilik önerisinin konusu yok.
    """
    TARGET = 'topic'

    topic = models.ForeignKey(Topic, models.PROTECT, verbose_name='konu')

    class Meta:
        abstract = True

    def check_target(self):
        if not self.topic.is_open:  # kural 7
            raise ValidationError('Kapalı, silinmiş ya da gizlenmiş konu yeni öneri almaz.')


class TopicOpenProposal(BaseProposal):
    # parent boşsa yeni ana konu önerisi (kural 9: kuruluştan sonra bu da oylamayla).
    SLUG = 'open'
    TARGET = 'parent'  # isteğe bağlı: boşsa ana konu önerisi
    LINK = 'Alt konu öner'
    FORM_FIELDS = ('title', 'description')

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

    def check_target(self):
        if self.parent_id and (self.parent.parent_id or not self.parent.is_open):
            raise ValidationError('Alt konu yalnızca açık bir ana konunun altına önerilebilir.')

    def apply(self):
        if self.parent_id and not self.parent.is_open:
            return False  # üst konu artık kapalı/silinmiş, yeni alt konu açılamaz
        Topic.objects.create(
            parent=self.parent, title=self.title, description=self.description, author=self.proposer,
        )
        return True


class TopicEditProposal(TopicProposal):
    SLUG = 'edit'
    LINK, MORE = 'Düzenleme öner', True
    FORM_FIELDS = ('new_title', 'new_description')

    new_title = models.CharField('yeni başlık', max_length=200)
    new_description = models.TextField('yeni açıklama', blank=True)

    DUPLICATE_FIELDS = ('topic_id', 'new_title', 'new_description')

    class Meta:
        verbose_name = 'konu düzenleme önerisi'
        verbose_name_plural = 'konu düzenleme önerileri'

    def __str__(self):
        return f'Düzenle: {self.topic}'

    def prefill(self):
        self.new_title, self.new_description = self.topic.title, self.topic.description

    def apply(self):
        if not self.topic.is_open:
            return False  # oylama sürerken konu kapandı ya da silindi
        self.topic.change(title=self.new_title, description=self.new_description)
        return True


class TopicCloseProposal(TopicProposal):
    SLUG = 'close'
    LINK, MORE = 'Kapatma öner', True

    DUPLICATE_FIELDS = ('topic_id',)

    class Meta:
        verbose_name = 'konu kapatma önerisi'
        verbose_name_plural = 'konu kapatma önerileri'

    def __str__(self):
        return f'Kapat: {self.topic}'

    def apply(self):
        if self.topic.is_deleted:
            return False  # silinmiş konu kapatılamaz
        self.topic.change(is_closed=True)
        return True


class TopicDeleteProposal(TopicProposal):
    SLUG = 'delete'
    LINK, MORE = 'Silme öner', True

    DUPLICATE_FIELDS = ('topic_id',)

    class Meta:
        verbose_name = 'konu silme önerisi'
        verbose_name_plural = 'konu silme önerileri'

    def __str__(self):
        return f'Sil: {self.topic}'

    def apply(self):
        self.topic.change(is_deleted=True)
        return True


class TopicUndoProposal(TopicProposal):
    class Action(models.TextChoices):
        REOPEN = 'reopen', 'Kapatmayı geri al'
        RESTORE = 'restore', 'Silmeyi geri al'

    SLUG = 'undo'
    LINK = 'Yeniden açmayı öner'  # konu sayfası yalnızca kapalı konuda; silineni arşiv sayfası geri getirir
    FORM_FIELDS = ('action',)

    action = models.CharField('işlem', max_length=10, choices=Action)

    DUPLICATE_FIELDS = ('topic_id', 'action')

    class Meta:
        verbose_name = 'geri alma önerisi'
        verbose_name_plural = 'geri alma önerileri'

    def __str__(self):
        return f'{self.get_action_display()}: {self.topic}'

    @classmethod
    def targets(cls):
        return Topic.objects.unhidden()  # kapalı ve silinmiş konu da; gizlenmiş olanı yalnızca yönetici açar

    def prefill(self):
        self.action = self.Action.RESTORE if self.topic.is_deleted else self.Action.REOPEN

    def check_target(self):
        if not self.topic.is_unhidden:  # üst konusu gizli olan da (gizli ana konunun alt konuları donar)
            raise ValidationError('Gizlenmiş konu öneri almaz.')  # moderasyon yalnızca yöneticiyle geri alınır
        if not (self.topic.is_closed if self.action == self.Action.REOPEN else self.topic.is_deleted):
            raise ValidationError('Bu konuda geri alınacak bir kapatma ya da silme yok.')

    def apply(self):
        self.topic.change(**{'is_closed' if self.action == self.Action.REOPEN else 'is_deleted': False})
        return True


class ExpertProposal(BaseProposal):
    class Action(models.TextChoices):
        GRANT = 'grant', 'B statüsü ver'
        REVOKE = 'revoke', 'B statüsünü geri al'

    SLUG = 'expert'
    TARGET = None  # hedef üye formda seçilir (voting/forms.py)
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

    def check_target(self):
        if not self.target_user_id:
            return
        if self.action == self.Action.GRANT:
            if self.target_user_id != self.proposer_id:
                raise ValidationError('B statüsü başvurusu yalnızca kendi adına yapılır.')  # kural 2: "başvuru"
            if self.target_user.role != User.Role.MEMBER:
                raise ValidationError('Bu üye zaten bilirkişi.')
        elif self.target_user.role != User.Role.EXPERT:
            raise ValidationError('Bu üye bilirkişi değil.')

    def _accepted(self, t):
        # kural 2: 2/3 evet. Ağırlık hep 1, yani count oy sayısıdır; ondalık hatası olmasın diye çapraz çarpım.
        # Oy yoksa ret (0 >= 0 kabul sayılmasın; yeter sayı en az 1 olsa da).
        num, den = settings.FORUM['EXPERT_APPROVAL_NUM'], settings.FORUM['EXPERT_APPROVAL_DEN']
        return t['count'] > 0 and t['yes'] * den >= t['count'] * num

    def apply(self):
        new_role = User.Role.EXPERT if self.action == self.Action.GRANT else User.Role.MEMBER
        if self.target_user.role != new_role:
            self.target_user.role = new_role
            self.target_user.save(update_fields=['role'])
        return True


class RequestProposal(TopicProposal):
    """Kural 5: konudan doğan istek, 3 gün tartışma + 3 gün oylama. Uygulanacak bir sistem
    işlemi yok; kabul edilmesi başlı başına sonuçtur (apply() hemen True döner).
    """
    SLUG = 'request'
    LINK = 'İstek aç'
    FORM_FIELDS = ('title', 'content')

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
        if self._state.adding:  # verilen tarihler korunur (taban sınıftaki gibi)
            forum = settings.FORUM
            if not self.discussion_ends_at:
                self.discussion_ends_at = timezone.now() + timedelta(days=forum['REQUEST_DISCUSSION_DAYS'])
            if not self.voting_ends_at:
                self.voting_ends_at = self.discussion_ends_at + timedelta(days=forum['REQUEST_VOTING_DAYS'])
        super().save(*args, **kwargs)

    @property
    def in_discussion(self):
        return timezone.now() < self.discussion_ends_at

    @property
    def deadline(self):
        return self.discussion_ends_at if self.in_discussion else self.voting_ends_at

    def accepts_votes(self):
        return self.is_open and not self.in_discussion

    def apply(self):
        return True


PROPOSAL_MODELS = tuple(PROPOSALS.values())  # tanım sırasıyla: konu sayfasındaki bağlantıların sırası da bu


def withdraw_running(user):
    """Hesap kapatma ve silme: süren oylamalardaki karar oyları silinir, süren önerileri iptal olur.
    Bitmiş oylamalara dokunulmaz; sonuçları kesinleşmiştir. Tip başına 2 sorgu.
    """
    for model in PROPOSAL_MODELS:
        running = model.objects.running()
        Vote.objects.filter(voter=user, content_type=ContentType.objects.get_for_model(model),
                            object_id__in=running.values('pk')).delete()
        running.filter(proposer=user).update(status=BaseProposal.Status.CANCELLED)


def active_proposals():
    """Oylaması (istekte tartışması) süren öneriler, evresinin bitişi yakın önce; participants = katılım sayısı.
    Panel, açık öneriler sayfası ve API kullanır; tip başına 1 sorgu. Süresi dolup sonuçlanmamış öneriyi burada
    sonuçlandırır (lazy kontrol): zamanlayıcının olmadığı yerel sunucuda da kural 5'teki süre işler.
    """
    now, running = timezone.now(), []
    for model in PROPOSAL_MODELS:
        # select_related(): boş bırakınca null olamayan tüm FK'leri (topic, target_user) tek sorguda getirir.
        for p in model.objects.filter(status=BaseProposal.Status.VOTING).select_related().annotate(
                participants=Count('votes')):
            if p.voting_ends_at > now:
                running.append(p)
            else:
                p.finalize()
    return sorted(running, key=attrgetter('deadline'))


def mark_voted(proposals, user):
    """"Oy ver" rozeti: oy hakkı olan kullanıcıda p.voted (True/False), 1 sorgu (panel ve API). Açık öneriye verilen
    oy önerinin açılışından sonradır; en eski öneriden sonraki oylar yeter. Eşleşme (content_type, object_id).
    """
    if proposals and user.is_authenticated and user.can_vote:
        mine = set(Vote.objects.filter(voter=user, voted_at__gte=min(p.created_at for p in proposals))
                   .values_list('content_type_id', 'object_id'))
        for p in proposals:
            p.voted = (ContentType.objects.get_for_model(p).pk, p.pk) in mine


def open_proposal_count(user):
    """Kural 8: kişi başı açık (oylaması süren) öneri sayısı, tüm tipler toplanarak; süresi dolan sayılmaz."""
    return sum(model.objects.running().filter(proposer=user).count() for model in PROPOSAL_MODELS)


def active_member_count():
    """Kural 3: son ACTIVE_DAYS günde karar oyu veren, konu açan ya da yorum yazan üye sayısı.
    Yorum oyu sayılmaz: tek tıkla verilir, yeter sayıyı şişirmemeli. Kapatılan hesaplar sayılmaz.
    """
    since = timezone.now() - timedelta(days=settings.FORUM['ACTIVE_DAYS'])
    voter_ids = Vote.objects.filter(voted_at__gte=since).values('voter_id')
    author_ids = Topic.objects.filter(created_at__gte=since).values('author_id')
    commenter_ids = Comment.objects.filter(created_at__gte=since).values('author_id')
    # pk__in alt sorguları aynı üyeyi iki kez döndürmez, distinct() gerekmez.
    return User.objects.filter(Q(pk__in=voter_ids) | Q(pk__in=author_ids) | Q(pk__in=commenter_ids),
                               is_active=True).count()


def required_quorum():
    """Kural 3: yeter sayı, aktif üyelerin %QUORUM_PERCENT'i, en az QUORUM_MIN."""
    total = active_member_count()
    return max(settings.FORUM['QUORUM_MIN'], math.ceil(total * settings.FORUM['QUORUM_PERCENT'] / 100))
