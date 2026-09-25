from django import template
from django.contrib.contenttypes.models import ContentType

register = template.Library()


@register.inclusion_tag('moderation/_links.html', takes_context=True)
def mod_links(context, obj):
    """Gizlenebilir içeriğin yanındaki moderasyon bağlantısı (yalnızca yöneticiye). Sorgu atmaz."""
    return {'obj': obj, 'ct': ContentType.objects.get_for_model(obj).pk, 'user': context['request'].user}
