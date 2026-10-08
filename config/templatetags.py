from django import template
from django.template.defaultfilters import stringfilter
from django.utils import timezone
from django.utils.formats import date_format

register = template.Library()


@register.filter(is_safe=True)
@stringfilter
def capfirst(value):
    """Django'nun capfirst'ünün Türkçe hâli: 'istek' -> 'İstek' (Python'un upper()'ı 'i'yi 'I' yapar).
    settings.TEMPLATES'te builtins olarak yüklenir ve yerleşik süzgeci bütün şablonlarda ezer.
    """
    return value[:1].replace('i', 'İ').upper() + value[1:]


def span(seconds):
    """Kısa süre: '14 dk', 3 saate kadar '1 sa 14 dk', sonra '5 sa'; 48 saate kadar '1 gün 6 sa', sonra '3 gün';
    30 günden sonra '10 ay', bir yıldan sonra yalnızca '3 yıl'.
    """
    m = int(seconds // 60)
    h, d = m // 60, m // 1440
    if d >= 365:
        return f'{d // 365} yıl'
    if d >= 30:
        return f'{d // 30} ay'
    if d >= 2:
        return f'{d} gün'
    if d:
        return f'1 gün {h - 24} sa' if h > 24 else '1 gün'
    if h >= 3 or (h and not m % 60):
        return f'{h} sa'
    return f'{h} sa {m % 60} dk' if h else f'{m} dk'


@register.filter
def ago(value):
    """Geçen süre: '1 sa 14 dk önce'; bir dakikadan yeniyse 'az önce' (timesince'in kısası)."""
    if not value:
        return ''
    seconds = (timezone.now() - value).total_seconds()
    return 'az önce' if seconds < 60 else f'{span(seconds)} önce'


@register.filter
def when(value, fmt='j F Y H:i'):
    """Sitenin tarih biçimi ('8 Ekim 2026 14:05'), yerel saatle; şablonlar ve API aynı biçimi kullanır."""
    return date_format(timezone.localtime(value), fmt) if value else ''


@register.filter
def left(value):
    """Bitişe kalan süre: '1 gün 22 sa' (timeuntil'in kısası); şablon arkasına 'kaldı' yazar."""
    if not value:
        return ''
    seconds = (value - timezone.now()).total_seconds()
    return span(seconds) if seconds >= 60 else "1 dk'dan az"
