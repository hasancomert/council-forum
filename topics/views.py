from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import OuterRef, Q
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
    tab = g.get('tab') if g.get('tab') in TABS else 'main'  # adresteki değer yalnızca sözlükte aranır
    _, where, sort = TABS[tab]
    sort = g.get('sort') if g.get('sort') in SORTS else sort
    qs = Topic.objects.visible().filter(where).select_related('parent').ranked(sort)
    if tab == 'main':
        qs = qs.annotate(n_sub=count_of(Topic, parent=OuterRef('pk'), is_deleted=False))
    return render(request, 'topics/home.html', {
        'page': Paginator(qs, settings.FORUM['TOPICS_PER_PAGE']).get_page(g.get('page')),  # geçersiz sayfa → ilk/son
        'tab': tab, 'sort': sort,
        'tabs': {k: v[0] for k, v in TABS.items()},
        # kapalı konu yorum ve oy almaz, "en popüler" orada anlamsız
        'sorts': {k: v for k, v in SORT_LABELS.items() if not (tab == 'closed' and k == 'popular')},
    })


def archive(request):
    # Kural 7: silinmiş konunun yalnızca başlığı ve tarihi görünür (şablonda); içerik gizli kalır.
    topics = Topic.objects.filter(Q(is_closed=True) | Q(is_deleted=True)).select_related('parent')
    return render(request, 'topics/archive.html', {'topics': topics, 'title': 'Arşiv'})


def detail(request, pk):
    topic = get_object_or_404(Topic.objects.visible(), pk=pk)  # gizli konu 404
    user = request.user
    return render(request, 'topics/detail.html', {
        'topic': topic, 'title': topic.title, 'children': topic.children.visible(),
        'votable': user.is_authenticated and topic.can_be_voted_by(user),
        # a and b or 0: giriş yoksa ya da oy yoksa 0
        'my_vote': user.is_authenticated and TopicVote.objects.filter(
            topic=topic, voter=user).values_list('value', flat=True).first() or 0,
    })


@login_required
@require_POST
def vote(request, pk):
    topic = get_object_or_404(Topic, pk=pk)
    try:
        TopicVote.cast(topic, request.user, {'1': 1, '-1': -1}.get(request.POST.get('value'), 0))
    except ValueError as e:
        messages.error(request, str(e))
    return redirect(topic)
