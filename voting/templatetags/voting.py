from operator import attrgetter

from django import template
from django.conf import settings
from django.core.cache import cache

from ..models import PANEL_CACHE_KEY, active_proposals, mark_voted, required_quorum

register = template.Library()


def _panel():
    """Panelin herkes için aynı kısmı: evresinin bitişi en yakın olan önce; yeter sayı (kural 3) çubuk için."""
    props = sorted(active_proposals(), key=attrgetter('deadline'))
    voting = [p for p in props if not p.in_discussion]
    talk = [p for p in props if p.in_discussion]
    return voting[:settings.FORUM['PANEL_VOTING']], talk[:settings.FORUM['PANEL_DISCUSSION']], len(props), required_quorum()


@register.inclusion_tag('voting/panel.html', takes_context=True)
def active_panel(context):
    """Aktif oylamalar paneli. Ortak kısım PANEL_CACHE_SECONDS saniye önbellekte (tip başına 1 sorgu yerine 0);
    önbellek kopya döndürdüğü için kişiye özel "Oy ver" rozeti ona sızmaz.
    """
    voting, talk, total, quorum = cache.get_or_set(PANEL_CACHE_KEY, _panel, settings.FORUM['PANEL_CACHE_SECONDS'])
    mark_voted(voting, context['request'].user)
    return {'voting': voting, 'talk': talk, 'total': total, 'quorum': quorum, 'more': total > len(voting) + len(talk)}
