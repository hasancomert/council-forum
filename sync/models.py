"""Eşitlemenin kendi tabloları: değişiklik günlüğü (tetikleyiciler yazar), tek satırlık durum, pk sayacı, gelen kaydı.
Tablo adları sabit: tetikleyici SQL'i ve ham sorgular bu adları kullanır. Admin'e kaydedilmez, eşitlenmez.
"""
import secrets

from django.db import models
from django.utils import timezone


def new_db_id():
    """Veritabanı kimliği: durum satırı ilk oluşunca (sync_init --reset de) üretilir, dosya kopyası taşır."""
    return secrets.randbits(31)


class Change(models.Model):
    """Yerel bir satır değişikliği; id giden akışın sıra numarası. data: satırın o anki hali (columns() sırasıyla
    JSON dizi), silmede boş. seen: kayıt anında karşıdan uygulanmış son sıra no (çakışma kuralı buna bakar).
    """
    tbl = models.CharField(max_length=64)
    rid = models.BigIntegerField()
    data = models.TextField(null=True)
    seen = models.BigIntegerField(default=0)
    at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'sync_change'
        ordering = ['id']


class State(models.Model):
    """Tek satır (pk=1): bağlantı ve akışın durumu."""
    applying = models.BooleanField(default=False)  # karşıdan gelen uygulanıyor: tetikleyiciler susar (yankı yok)
    applied = models.BigIntegerField(default=0)  # karşıdan uygulanan son sıra no
    peer_applied = models.BigIntegerField(default=0)  # karşının uyguladığı son yerel sıra no
    synced_until = models.DateTimeField(null=True)  # karşının kendi saatiyle "bu ana kadarki her şeyim sende"
    heard_at = models.DateTimeField(null=True)  # karşıdan son duyulan paket
    clock_offset = models.IntegerField(default=0)  # karşı saat − yerel saat (sn)
    rssi = models.SmallIntegerField(null=True)
    snr = models.SmallIntegerField(null=True)
    schema_ok = models.BooleanField(default=True)  # şema özetleri tutuyor mu
    airtime_ms = models.IntegerField(default=0)  # son bir saatte yayın süresi
    db_id = models.IntegerField(default=new_db_id)  # şema özetine katılır: kopyalanmadan ayrı kurulan yakalansın

    class Meta:
        db_table = 'sync_state'

    @classmethod
    def load(cls):
        return cls.objects.get_or_create(pk=1)[0]


class Counter(models.Model):
    """Düğüm başına pk sayacı; key = "<düğüm>:<tablo>"."""
    key = models.CharField(max_length=80, primary_key=True)
    next = models.BigIntegerField()

    class Meta:
        db_table = 'sync_counter'


class Received(models.Model):
    """Karşıdan gelen mesajların kaydı (durum sayfası). note: boş, çakışma, ad çakışması ya da uygulanamadı."""
    seq = models.BigIntegerField()
    tbl = models.CharField(max_length=64)
    rid = models.BigIntegerField()
    note = models.CharField(max_length=20, blank=True)
    at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'sync_received'
        ordering = ['-id']
