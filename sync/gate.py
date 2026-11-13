"""Eşitleme kapısı. Modül düzeyinde hiçbir model import etmez: voting/models.py bunu import eder."""
from django.conf import settings


def enabled():
    return bool(settings.SYNC['NODE'])


def is_arbiter():
    """Hakem (1. düğüm): oylamaları yalnızca o sonuçlandırır, çakışmada onun sürümü geçerli."""
    return settings.SYNC['NODE'] == 1
