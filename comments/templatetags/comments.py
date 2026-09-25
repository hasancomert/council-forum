from collections import defaultdict

from django import template
from django.contrib.contenttypes.models import ContentType

from ..forms import CommentForm

register = template.Library()


@register.inclusion_tag('comments/section.html', takes_context=True)
def comment_section(context, target):
    """Hedefin yorum bölümü. Tek seviye yanıt olduğundan özyineleme yok: yorumlar tek sorguda
    gelir, Python'da ana yorum → yanıtlar diye gruplanır.
    """
    request = context['request']
    comments = list(target.comments.select_related('author').order_by('created_at'))
    groups = defaultdict(list)
    for c in comments:
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
        'request': request, 'user': request.user, 'csrf_token': context.get('csrf_token'),
    }
