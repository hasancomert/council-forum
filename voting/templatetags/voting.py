from operator import attrgetter

from django import template
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.core.cache import cache

from ..models import PANEL_CACHE_KEY, Vote, active_proposals, required_quorum

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
    user = context['request'].user
    if voting and user.is_authenticated and user.can_vote:
        # "Oy ver": oy verilmemiş öneri, 1 sorgu. Açık öneriye verilen oy, önerinin açılışından sonradır; kullanıcının
        # en eski açık öneriden sonraki oyları yeter. Tipler ayrı tablolarda: eşleşme (content_type, object_id).
        mine = set(Vote.objects.filter(voter=user, voted_at__gte=min(p.created_at for p in voting))
                   .values_list('content_type_id', 'object_id'))
        for p in voting:
            p.voted = (ContentType.objects.get_for_model(p).pk, p.pk) in mine
    return {'voting': voting, 'talk': talk, 'total': total, 'quorum': quorum, 'more': total > len(voting) + len(talk)}
