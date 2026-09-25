from collections import defaultdict

from django import template
from django.contrib.contenttypes.models import ContentType

from ..forms import CommentForm
from ..models import CommentVote

register = template.Library()


@register.inclusion_tag('comments/section.html', takes_context=True)
def comment_section(context, target):
    """Hedefin yorum bölümü, yorum sayısından bağımsız 2 sorgu: yorumlar+yazarlar ve kullanıcının
    oyları. Tek seviye yanıt olduğundan özyineleme yok, ana yorum → yanıtlar Python'da gruplanır.
    """
    request = context['request']
    user = request.user
    comments = list(target.comments.select_related('author').order_by('created_at'))
    mine = {}
    if comments and user.is_authenticated:
        mine = dict(CommentVote.objects.filter(voter=user, comment__in=comments).values_list('comment_id', 'value'))
    groups = defaultdict(list)
    for c in comments:
        c.my_vote = mine.get(c.pk, 0)
        groups[c.parent_id].append(c)
    top = groups.pop(None, [])
    sort = request.GET.get('sort')
    if sort == 'new':
        top.reverse()
    else:
        top.sort(key=lambda c: -c.score)  # sort kararlıdır: eşit puanda eski yorum önde kalır
    for c in top:
        c.children = groups.get(c.pk, [])  # yanıtlar hep kronolojik
    return {
        'target': target, 'open': target.is_open, 'comments': top, 'sort': sort,
        'count': sum(not c.is_deleted for c in comments),
        'ct': ContentType.objects.get_for_model(target).pk,
        'form': CommentForm(auto_id=False),  # sayfada çok form var: tekrarlanan id olmasın
        'can_vote': user.is_authenticated and user.can_vote,  # kural 1: hesap yaşı
        'request': request, 'user': user, 'csrf_token': context.get('csrf_token'),
    }
