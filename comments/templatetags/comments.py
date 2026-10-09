from django import template
from django.contrib.contenttypes.models import ContentType

from ..forms import CommentForm
from ..views import section

register = template.Library()


@register.inclusion_tag('comments/section.html', takes_context=True)
def comment_section(context, target):
    """Hedefin yorum bölümü; veri comments.views.section()'dan (API de onu kullanır)."""
    request = context['request']
    user = request.user
    return section(target, user, request.GET.get('sort'), request.GET.get('page')) | {
        'target': target, 'ct': ContentType.objects.get_for_model(target).pk,
        'form': CommentForm(auto_id=False),  # sayfada çok form var: tekrarlanan id olmasın
        'can_post': user.is_authenticated and user.can_post,  # engelli yazamaz
        'request': request, 'user': user, 'csrf_token': context.get('csrf_token'),
    }
