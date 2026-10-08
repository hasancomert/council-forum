from django import template
from django.conf import settings

from ..models import active_proposals, mark_voted, required_quorum

register = template.Library()


@register.inclusion_tag('voting/panel.html', takes_context=True)
def active_panel(context):
    """Aktif oylamalar paneli: evresinin bitişi en yakın olan önce; yeter sayı (kural 3) katılım çubuğu için.
    Önbellek yok: tip başına 1 sorgu, ölçülen kazanç birkaç ms'ydi (KISS; TASARIM.md).
    """
    props = active_proposals()
    voting = [p for p in props if not p.in_discussion][:settings.FORUM['PANEL_VOTING']]
    talk = [p for p in props if p.in_discussion][:settings.FORUM['PANEL_DISCUSSION']]
    mark_voted(voting, context['request'].user)
    return {'voting': voting, 'talk': talk, 'total': len(props), 'quorum': required_quorum(),
            'more': len(props) > len(voting) + len(talk)}
