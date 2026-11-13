"""Hangi tablo ve sütunlar eşitlenir; şema özeti ve içerik özeti. Yalnızca okur, yan etkisi yok."""
import json
import zlib
from functools import cache

from django.apps import apps
from django.contrib.contenttypes.models import ContentType
from django.db import connection

from comments.models import UpDownVote

APPS = ('accounts', 'topics', 'voting', 'comments', 'moderation')
# Telsizden gitmeyen sütunlar: karşıda satır ilk kez oluşurken yazılan değer (ya da pk'den değer üreten fonksiyon).
LOCAL = {
    'accounts_user': {'password': '!', 'last_login': None, 'email': lambda pk: f'{pk}@uzak.invalid',
                      'first_name': '', 'last_name': '', 'is_staff': False, 'is_superuser': False},
    'comments_comment': {'score': 0},  # puan karşıda oylardan yeniden hesaplanır
    'topics_topic': {'score': 0},
}


@cache
def models():
    """db_table -> model; somut modeller (otomatik çoktan-çoğa tablolar get_models()'ta yok)."""
    return {m._meta.db_table: m for app in APPS for m in apps.get_app_config(app).get_models()}


def tables():
    """Eşitlenen tablolar, ada göre sıralı; mesajdaki tablo numarası bu listedeki yer."""
    return sorted(models())


def columns(table):
    """Telsizden giden sütunlar: pk ve LOCAL dışındakiler, modelin alan sırasıyla."""
    local = LOCAL.get(table, {})
    return [f.column for f in models()[table]._meta.concrete_fields if not f.primary_key and f.column not in local]


def label(table):
    return str(models()[table]._meta.verbose_name)


def scored():
    """▲/▼ oy tablosu -> (hedef FK sütunu, hedef tablo)."""
    out = {}
    for table, model in models().items():
        if issubclass(model, UpDownVote):
            target = model._meta.get_field(model.TARGET)
            out[table] = (target.column, target.related_model._meta.db_table)
    return out


def quoted(names):
    return ', '.join(map(connection.ops.quote_name, names))


def fingerprint():
    """Şema özeti: tablolar, bütün sütunları ve ContentType kimlikleri iki tarafta aynı olmalı."""
    schema = [[t, [f.column for f in models()[t]._meta.concrete_fields]] for t in tables()]
    types = list(ContentType.objects.order_by('id').values_list('id', 'app_label', 'model'))
    return zlib.crc32(json.dumps([schema, types]).encode())


def digest():
    """İçerik özeti (8 onaltılık hane): iki tarafta aynıysa forumlar eşit. Yerelde kalan sütunlar dışarıda."""
    crc = 0
    with connection.cursor() as cursor:
        for table in tables():
            cursor.execute(f'SELECT {quoted(["id", *columns(table)])} FROM "{table}" ORDER BY id')
            crc = zlib.crc32(table.encode(), crc)
            for row in cursor:
                crc = zlib.crc32(repr(row).encode(), crc)
    return f'{crc:08x}'
