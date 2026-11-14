"""Eşitleme kapısı. Modül düzeyinde hiçbir model import etmez: voting/models.py bunu import eder."""
from datetime import timedelta

from django.conf import settings


def enabled():
    return bool(settings.SYNC['NODE'])


def is_arbiter():
    """Hakem (1. düğüm): oylamaları yalnızca o sonuçlandırır, çakışmada onun sürümü geçerli."""
    return settings.SYNC['NODE'] == 1


def may_finalize(proposal):
    """Hakem kuralı: iki forumda sonuç hep aynı olsun. Eşitleme kapalıysa bugünkü gibi; 2. düğüm hiç sonuçlandırmaz
    (sonuç hakemden satır olarak gelir); hakem, karşı düğüm kendi saatiyle bitişi FINALIZE_MARGIN geçtiğini ve o ana
    kadarki bütün değişikliklerini (oylarını) bildirdikten sonra. Ara durumdaki öneri beklemeden uygulanır.
    """
    if not enabled():
        return True
    if not is_arbiter():
        return False
    if proposal.status != 'voting':
        return True
    from .models import State
    until = State.load().synced_until
    return until is not None and until >= proposal.voting_ends_at + timedelta(seconds=settings.SYNC['FINALIZE_MARGIN'])
