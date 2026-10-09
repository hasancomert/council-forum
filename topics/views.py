from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, OuterRef, Q, Subquery
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_POST

from comments.models import vote_block
from comments.views import updown
from config.utils import as_pk, back
from voting.models import PROPOSAL_MODELS, TopicCloseProposal, TopicDeleteProposal

from .models import SORTS, Topic, TopicVote, count_of

# sekme: (başlık, süzgeç, varsayılan sıralama). Süzgeçler Topic.is_locked'ın sorgu karşılığı:
# üst konusu kapalı alt konu da kapalıdır (yorum, oy ve öneri almaz), "Kapalı" sekmesinde görünür.
TABS = {
    'main': ('Ana konular', Q(parent=None, is_closed=False), 'popular'),
    'sub': ('Alt konular', Q(parent__isnull=False, is_closed=False, parent__is_closed=False), 'popular'),
    'closed': ('Kapalı', Q(is_closed=True) | Q(parent__is_closed=True), 'new'),
}


def with_pending(qs, parent=True):
    """'Kapatma/Silme oylamasında' rozetlerinin verisi (Topic.pending() okur): süren önerinin pk'si, yoksa None.
    Satır başına alt sorgu, sorgu sayısı artmaz. Görünüm yapar: topics.models voting'i import edemez.
    parent: alt konuda üst konunun süren kapatma/silme oylaması da (alt konu onunla birlikte kapanır).
    """
    def running(model, ref='pk'):
        return Subquery(model.objects.running().filter(topic=OuterRef(ref)).values('pk')[:1])
    qs = qs.annotate(closing=running(TopicCloseProposal), deleting=running(TopicDeleteProposal))
    if parent:
        qs = qs.annotate(parent_closing=running(TopicCloseProposal, 'parent'),
                         parent_deleting=running(TopicDeleteProposal, 'parent'))
    return qs


def listing(g):
    """Ana sayfanın konu listesi (site ve API): g = request.GET (tab, sort, page, parent)."""
    qs, parent = Topic.objects.visible(), None
    if (pk := as_pk(g.get('parent'))) is not None:  # ?parent=<pk>: yalnızca o konunun alt konuları
        parent = get_object_or_404(Topic.objects.visible(), pk=pk)
        qs = qs.filter(parent=parent)
    tabs = {k: v[0] for k, v in TABS.items() if not (parent and k == 'main')}  # alt konunun alt konusu olmaz
    tab = g.get('tab') if g.get('tab') in tabs else next(iter(tabs))  # adresteki değer yalnızca sözlükte aranır
    _, where, sort = TABS[tab]
    # kapalı konu yorum ve oy almaz, "en popüler" orada anlamsız (adreste verilse de)
    sorts = {k: label for k, (label, _) in SORTS.items() if not (tab == 'closed' and k == 'popular')}
    sort = g.get('sort') if g.get('sort') in sorts else sort
    qs = with_pending(qs.filter(where).select_related('parent').ranked(sort))
    if tab == 'main':
        qs = qs.annotate(n_sub=count_of(Topic, parent=OuterRef('pk'), is_deleted=False, is_hidden=False))
    return {
        'page': Paginator(qs, settings.FORUM['TOPICS_PER_PAGE']).get_page(g.get('page')),  # geçersiz sayfa → ilk/son
        'tab': tab, 'sort': sort, 'parent': parent, 'tabs': tabs, 'sorts': sorts,
    }


def home(request):
    return render(request, 'topics/home.html', listing(request.GET))


def archive(request):
    # Kural 7: silinen konunun yalnızca başlığı ve tarihi görünür (şablonda); içerik gizli kalır.
    # Kapalılar ana sayfanın "Kapalı" sekmesinde; üst konusu silinen alt konu, üst konu geri gelince döner.
    # Gizliler burada da listelenmez.
    topics = Topic.objects.unhidden().filter(is_deleted=True).select_related('parent').order_by('-created_at', '-pk')
    page = Paginator(topics, settings.FORUM['TOPICS_PER_PAGE']).get_page(request.GET.get('page'))
    return render(request, 'topics/archive.html', {'page': page, 'title': 'Silinen konular'})


def proposal_links(topic, user):
    """Konu sayfasındaki öneri bağlantıları [(tip, etiket)]: (öndekiler, "Diğer öneriler"dekiler). Site, API ve
    uygulama aynı listeyi çizer. Hangi tipin önerilebileceğine tipin kendi hedef denetimi karar verir
    (BaseProposal.offered_for); öneri açmak oy hakkı ister (kural 1). Sorgu yok.
    """
    main, more = [], []
    if user.is_authenticated and user.can_vote:
        for model in PROPOSAL_MODELS:
            if model.offered_for(topic):
                (more if model.MORE else main).append((model.SLUG, model.LINK))
    return main, more


def page_data(pk, user):
    """Konu sayfasının verisi (site ve API). Silinmiş konu 404; gizli konunun sayfası açılır, metni maskelenir."""
    topic = get_object_or_404(with_pending(Topic.objects.existing().select_related('parent', 'author')), pk=pk)
    masked = topic.hidden_from(user)  # metni yalnızca sahibi ve yöneticiler görür
    data = {
        'topic': topic, 'masked': masked, 'title': 'Moderasyonla gizlendi' if masked else topic.title,
        # ▲/▼ hep görünür; verilemiyorsa düğmeler soluk ve nedeni yazar
        'vote_why': vote_block(user) or ('Kendi konuna oy verilmez' if topic.author_id == user.pk
                                         else '' if topic.is_open else 'Oylama kapalı'),
        # a and b or 0: giriş yoksa ya da oy yoksa 0
        'my_vote': user.is_authenticated and TopicVote.objects.filter(
            topic=topic, voter=user).values_list('value', flat=True).first() or 0,
    }
    data['links'], data['more_links'] = proposal_links(topic, user)
    if not topic.parent_id:  # ana konu: ilk TOPICS_PER_PAGE açık alt konu; gerisi ana sayfada ?parent= ile
        subs, open_q, closed_q = topic.children.visible(), TABS['sub'][1], TABS['closed'][1]
        data['n_subs'] = subs.aggregate(open=Count('pk', filter=open_q), closed=Count('pk', filter=closed_q))
        subs = with_pending(subs.filter(open_q).ranked('popular'), parent=False)  # üst konunun rozeti başlıkta
        data['subs'] = subs[:settings.FORUM['TOPICS_PER_PAGE']]
    return data


def detail(request, pk):
    return render(request, 'topics/detail.html', page_data(pk, request.user))


@login_required
@require_POST
def vote(request, pk):
    topic = get_object_or_404(Topic, pk=pk)
    return updown(request, TopicVote, topic, back(request, topic.get_absolute_url()))  # yorumların hangi sayfasındaysa oraya
