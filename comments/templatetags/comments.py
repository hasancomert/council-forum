from collections import defaultdict

from django import template
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.core.paginator import Paginator
from django.db.models import Count, Q

from ..forms import CommentForm
from ..models import CommentVote

register = template.Library()


@register.inclusion_tag('comments/section.html', takes_context=True)
def comment_section(context, target):
    """Hedefin yorum bölümü. Ana yorumlar veritabanında sıralanıp sayfalanır (COMMENTS_PER_PAGE), yanıtlar
    yalnızca sayfadaki ana yorumlar için gelir. Yorum sayısından bağımsız 4 sorgu: sayımlar, sayfa, yanıtlar
    ve kullanıcının oyları. Tek seviye yanıt olduğundan özyineleme yok, gruplama Python'da.
    """
    request = context['request']
    user = request.user
    sort = request.GET.get('sort')
    top = target.comments.filter(parent=None).select_related('author')
    top = top.order_by('-created_at') if sort == 'new' else top.order_by('-score', 'created_at')  # eşit puanda eski önde
    n = target.comments.aggregate(top=Count('pk', filter=Q(parent=None)),
                                  shown=Count('pk', filter=Q(is_deleted=False, is_hidden=False)))
    paginator = Paginator(top, settings.FORUM['COMMENTS_PER_PAGE'])
    paginator.count = n['top']  # count bir cached_property: kendi sayım sorgusu yerine yukarıdaki kullanılır
    page = paginator.get_page(request.GET.get('page'))  # geçersiz sayfa → ilk/son
    top = list(page)
    replies = list(target.comments.filter(parent__in=top).select_related('author').order_by('created_at'))
    mine = {}
    if top and user.is_authenticated:
        mine = dict(CommentVote.objects.filter(voter=user, comment__in=top + replies).values_list('comment_id', 'value'))
    groups = defaultdict(list)
    is_open = target.is_open
    for c in top + replies:
        c.my_vote = mine.get(c.pk, 0)
        c.masked = c.hidden_from(user)  # gizli metni yalnızca yazarı ve yöneticiler görür
        c.frozen = c.is_hidden or not is_open  # yanıt, oy ve düzenleme yok; yazar yine silebilir
    for r in replies:
        groups[r.parent_id].append(r)  # yanıtlar hep kronolojik
    for c in top:
        c.children = groups[c.pk]
    return {
        'target': target, 'open': is_open, 'comments': top, 'page': page, 'sort': sort, 'count': n['shown'],
        'ct': ContentType.objects.get_for_model(target).pk,
        'form': CommentForm(auto_id=False),  # sayfada çok form var: tekrarlanan id olmasın
        'can_vote': user.is_authenticated and user.can_vote,  # kural 1: hesap yaşı
        'can_post': user.is_authenticated and user.can_post,  # engelli yazamaz
        'request': request, 'user': user, 'csrf_token': context.get('csrf_token'),
    }
