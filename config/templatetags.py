from django import template
from django.template.defaultfilters import stringfilter

register = template.Library()


@register.filter(is_safe=True)
@stringfilter
def capfirst(value):
    """Django'nun capfirst'ünün Türkçe hâli: 'istek' -> 'İstek' (Python'un upper()'ı 'i'yi 'I' yapar).
    settings.TEMPLATES'te builtins olarak yüklenir ve yerleşik süzgeci bütün şablonlarda ezer.
    """
    return value[:1].replace('i', 'İ').upper() + value[1:]
