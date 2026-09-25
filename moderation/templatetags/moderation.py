from django import template
from django.contrib.contenttypes.models import ContentType

register = template.Library()


@register.inclusion_tag('moderation/_links.html', takes_context=True)
def mod_links(context, obj):
    """Gizlenebilir içeriğin yanında: yöneticiye moderasyon bağlantısı, oy hakkı olana şikayet düğmesi. Sorgu atmaz."""
    user = context['request'].user
    return {
        'obj': obj, 'ct': ContentType.objects.get_for_model(obj).pk, 'user': user,
        'can_report': obj.can_be_reported_by(user),  # yönetici şikayet yerine bağlantıyı görür (şablon)
        'request': context['request'], 'csrf_token': context.get('csrf_token'),
    }
