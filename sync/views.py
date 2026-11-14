"""Rozet, durum sayfası ve rozetin JSON'u: yalnızca eşitleme açıkken, kapalıyken 404."""
from datetime import timedelta

from django.conf import settings
from django.http import Http404, JsonResponse
from django.shortcuts import render
from django.utils import timezone

from voting.models import PROPOSAL_MODELS, BaseProposal

from .gate import enabled, is_arbiter
from .models import Change, Received, State
from .tables import digest, label


def summary():
    """Rozet ve JSON: düğüm, bağlantı (son ONLINE_SECONDS'ta karşıdan paket duyuldu mu), bekleyen giden mesaj."""
    state = State.load()
    online = state.heard_at is not None and timezone.now() - state.heard_at < timedelta(
        seconds=settings.SYNC['ONLINE_SECONDS'])
    return {'node': settings.SYNC['NODE'], 'arbiter': is_arbiter(), 'online': online,
            'pending': Change.objects.filter(id__gt=state.peer_applied).count(), 'applied': state.applied,
            'schema_ok': state.schema_ok}


def status(request):
    """Hocanın göreceği sayfa: bağlantı, uyarılar, trafik ve içerik özeti. İçerik metni, üye adı ve oy yönü yok."""
    if not enabled():
        raise Http404
    state, rows, now = State.load(), settings.SYNC['LOG_ROWS'], timezone.now()
    sent = list(Change.objects.only('id', 'tbl', 'rid', 'at').order_by('-id')[:rows])
    received = list(Received.objects.all()[:rows])
    for row in sent + received:
        row.label = label(row.tbl)
    return render(request, 'sync/status.html', {
        'title': 'LoRa eşitleme', 'state': state, 'sent': sent, 'received': received, 'digest': digest(),
        'clock_warn': abs(state.clock_offset) > settings.SYNC['CLOCK_WARN'],
        'airtime': state.airtime_ms / 36000, 'airtime_limit': settings.SYNC['AIRTIME_PERCENT'],  # yüzde
        'waiting': [p for model in PROPOSAL_MODELS  # süresi dolmuş, sonucu hakemden bekleniyor
                    for p in model.objects.filter(status=BaseProposal.Status.VOTING, voting_ends_at__lte=now)],
    })


def status_json(request):
    """site.js rozeti POLL_SECONDS'ta bir yeniler; applied artınca "Yenile" şeridi çıkar."""
    if not enabled():
        raise Http404
    return JsonResponse(summary())
