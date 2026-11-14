"""Eşitleyici: Link ile veritabanı arasındaki yapıştırıcı. Giden mesajlar sync_change'ten, gelenler apply() ile."""
import logging
import time
from datetime import UTC, datetime, timedelta

from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from .link import Link
from .models import Change, Received, State
from .replay import apply, pack
from .tables import fingerprint, label

log = logging.getLogger(__name__)


class Runner:
    def __init__(self, port, now=time.monotonic):
        self.now, self.saved_at = now, None
        self.link = Link(port, self, node=settings.SYNC['NODE'], key=settings.SYNC['KEY'].encode(), now=now)
        self.schema_known = False  # bu süreçte karşıdan şeması tutan bir durum paketi geldi mi
        self.waiting = None  # (karşı saat, karşının son sıra no): hepsi uygulanınca synced_until olur

    # Link'in beklediği host sözleşmesi
    def applied(self):
        return State.load().applied

    def next_message(self):
        change = Change.objects.filter(id__gt=State.load().peer_applied).first()
        return (change.id, pack(change)) if change else None

    def delivered(self, seq):
        State.objects.filter(pk=1).update(peer_applied=seq)
        change = Change.objects.get(id=seq)
        log.info('giden  #%s %s %s', seq, label(change.tbl), change.rid)

    def deliver(self, seq, body):
        # Şema bilinmeden ya da tutmazken uygulanmaz (veritabanı kopyalanmamış olabilir): onay yok, karşı yeniden dener.
        if not (self.schema_known and State.load().schema_ok):
            return False
        apply(seq, body)
        got = Received.objects.first()
        log.info('gelen  #%s %s %s%s', seq, label(got.tbl), got.rid, f' ({got.note})' if got.note else '')
        self.check_synced()
        return True

    def status(self):
        last = Change.objects.order_by('-id').values_list('id', flat=True).first() or 0
        return int(time.time()), last, fingerprint()

    def on_status(self, clock, last, applied, schema):
        self.schema_known = schema == fingerprint()
        if not self.schema_known:
            State.objects.filter(pk=1).update(schema_ok=False)
            return
        peer_applied = max(State.load().peer_applied, applied)  # toplu onay; geri gitmez
        State.objects.filter(pk=1).update(schema_ok=True, peer_applied=peer_applied,
                                          clock_offset=clock - int(time.time()))
        self.waiting = (clock, last)
        self.check_synced()

    def check_synced(self):
        """Karşı kendi saatiyle clock anına kadarki her değişikliğini bildirdi; hepsi uygulandıysa synced_until ilerler
        (hakem kuralı karşının saatine bakar: iki bilgisayarın saat farkı sonucu bozmaz).
        """
        if self.waiting and State.load().applied >= self.waiting[1]:
            until = datetime.fromtimestamp(self.waiting[0], UTC)
            State.objects.filter(Q(synced_until=None) | Q(synced_until__lt=until), pk=1).update(synced_until=until)
            self.waiting = None

    def tick(self):
        """Bir adım; hiçbir hata döngüyü durdurmaz (günlüğe yazılır). Durum saniyede en çok bir kez kaydedilir."""
        try:
            self.link.step()
            if self.saved_at is None or self.now() >= self.saved_at + 1:
                self.saved_at, link = self.now(), self.link
                fields = {'airtime_ms': int(link.airtime_used() * 1000)}
                if link.heard is not None:
                    fields.update(heard_at=timezone.now() - timedelta(seconds=self.now() - link.heard),
                                  rssi=link.rssi, snr=link.snr)
                State.objects.filter(pk=1).update(**fields)
        except Exception:
            log.exception('Eşitleme adımı başarısız')
