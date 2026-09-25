from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, OuterRef, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .models import SORTS, Topic, TopicVote, count_of

# sekme: (başlık, süzgeç, varsayılan sıralama). Süzgeçler Topic.is_locked'ın sorgu karşılığı:
# üst konusu kapalı alt konu da kapalıdır (yorum, oy ve öneri almaz), "Kapalı" sekmesinde görünür.
TABS = {
    'main': ('Ana konular', Q(parent=None, is_closed=False), 'popular'),
    'sub': ('Alt konular', Q(parent__isnull=False, is_closed=False, parent__is_closed=False), 'popular'),
    'closed': ('Kapalı', Q(is_closed=True) | Q(parent__is_closed=True), 'new'),
}
SORT_LABELS = {'popular': 'en popüler', 'votes': 'en çok oy', 'new': 'en yeni'}


def home(request):
    g = request.GET
    qs, parent = Topic.objects.visible(), None
    if g.get('parent', '').isdigit():  # ?parent=<pk>: yalnızca o konunun alt konuları (konu sayfasındaki bağlantılar)
        parent = get_object_or_404(Topic.objects.visible(), pk=g['parent'])
        qs = qs.filter(parent=parent)
    tabs = {k: v[0] for k, v in TABS.items() if not (parent and k == 'main')}  # alt konunun alt konusu olmaz
    tab = g.get('tab') if g.get('tab') in tabs else next(iter(tabs))  # adresteki değer yalnızca sözlükte aranır
    _, where, sort = TABS[tab]
    sort = g.get('sort') if g.get('sort') in SORTS else sort
    qs = qs.filter(where).select_related('parent').ranked(sort)
    if tab == 'main':
        qs = qs.annotate(n_sub=count_of(Topic, parent=OuterRef('pk'), is_deleted=False))
    return render(request, 'topics/home.html', {
        'page': Paginator(qs, settings.FORUM['TOPICS_PER_PAGE']).get_page(g.get('page')),  # geçersiz sayfa → ilk/son
        'tab': tab, 'sort': sort, 'parent': parent, 'tabs': tabs,
        # kapalı konu yorum ve oy almaz, "en popüler" orada anlamsız
        'sorts': {k: v for k, v in SORT_LABELS.items() if not (tab == 'closed' and k == 'popular')},
    })


def archive(request):
    # Kural 7: silinen konunun yalnızca başlığı ve tarihi görünür (şablonda); içerik gizli kalır.
    # Kapalılar ana sayfanın "Kapalı" sekmesinde; üst konusu silinen alt konu, üst konu geri gelince döner.
    topics = Topic.objects.filter(is_deleted=True).select_related('parent')
    page = Paginator(topics, settings.FORUM['TOPICS_PER_PAGE']).get_page(request.GET.get('page'))
    return render(request, 'topics/archive.html', {'page': page, 'title': 'Silinen konular'})


def detail(request, pk):
    topic = get_object_or_404(Topic.objects.visible().select_related('parent'), pk=pk)  # gizli konu 404
    user = request.user
    context = {
        'topic': topic, 'title': topic.title,
        'votable': user.is_authenticated and topic.can_be_voted_by(user),
        # a and b or 0: giriş yoksa ya da oy yoksa 0
        'my_vote': user.is_authenticated and TopicVote.objects.filter(
            topic=topic, voter=user).values_list('value', flat=True).first() or 0,
    }
    if not topic.parent_id:  # ana konu: ilk TOPICS_PER_PAGE açık alt konu; gerisi ana sayfada ?parent= ile
        subs, open_q, closed_q = topic.children.visible(), TABS['sub'][1], TABS['closed'][1]
        context['n_subs'] = subs.aggregate(open=Count('pk', filter=open_q), closed=Count('pk', filter=closed_q))
        context['subs'] = subs.filter(open_q).ranked('popular')[:settings.FORUM['TOPICS_PER_PAGE']]
    return render(request, 'topics/detail.html', context)


@login_required
@require_POST
def vote(request, pk):
    topic = get_object_or_404(Topic, pk=pk)
    try:
        TopicVote.cast(topic, request.user, {'1': 1, '-1': -1}.get(request.POST.get('value'), 0))
    except ValueError as e:
        messages.error(request, str(e))
    return redirect(topic)
