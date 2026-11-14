from django.conf import settings

from .gate import enabled


def sync_status(request):
    """Menüdeki LoRa rozeti; eşitleme kapalıyken sorgu yok."""
    if not enabled():
        return {}
    from .views import summary  # views voting'i import eder: ayarlar yüklenirken değil, istekte
    return {'sync': summary(), 'sync_poll': settings.SYNC['POLL_SECONDS']}
