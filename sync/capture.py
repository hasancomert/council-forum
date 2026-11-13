"""Değişikliği yakalama: SQLite tetikleyicileri eşitlenen her satır değişikliğinin o anki halini sync_change'e yazar.
Satır hangi yoldan değişirse değişsin (save, .update(), ham SQL) yakalanır; mevcut uygulamalara dokunulmaz.
"""
from django.core import checks
from django.core.exceptions import ImproperlyConfigured
from django.db import connection, transaction

from .gate import enabled
from .models import Change, Counter, Received, State
from .tables import columns, tables

# applying: eşitleyici karşıdan geleni uygularken tetikleyici susar (yankı olmasın).
# seen: kayıt anında karşıdan uygulanmış son sıra no; strftime: UTC, milisaniyeli (Django'nun biçimi).
TRIGGER = """CREATE TRIGGER "sync_{t}_{op}" AFTER {event} ON "{t}"
WHEN NOT COALESCE((SELECT applying FROM sync_state), 0){changed}
BEGIN
  INSERT INTO sync_change (tbl, rid, data, seen, at)
  VALUES ('{t}', {row}.id, {data}, COALESCE((SELECT applied FROM sync_state), 0),
          strftime('%Y-%m-%d %H:%M:%f', 'now'));
END"""


def names():
    return {f'sync_{t}_{op}' for t in tables() for op in 'iud'}


def install():
    """Tetikleyicileri (yeniden) kurar; yeniden çalıştırılabilir, günlüğe dokunmaz."""
    if connection.vendor != 'sqlite':
        raise ImproperlyConfigured('Eşitleme yalnızca SQLite ile çalışır.')
    with transaction.atomic(), connection.cursor() as cursor:
        for t in tables():
            cols = columns(t)
            new = 'json_array(' + ', '.join(f'NEW."{c}"' for c in cols) + ')'
            # güncelleme yalnızca telsizden giden bir sütun değiştiyse kayıt üretir (puan, last_login üretmez)
            changed = ' AND (' + ' OR '.join(f'OLD."{c}" IS NOT NEW."{c}"' for c in cols) + ')'
            for op, event, row, data, cond in (('i', 'INSERT', 'NEW', new, ''), ('u', 'UPDATE', 'NEW', new, changed),
                                               ('d', 'DELETE', 'OLD', 'NULL', '')):
                cursor.execute(f'DROP TRIGGER IF EXISTS "sync_{t}_{op}"')
                cursor.execute(TRIGGER.format(t=t, op=op, event=event, row=row, data=data, changed=cond))
    State.load()


def installed():
    if connection.vendor != 'sqlite':
        return False
    with connection.cursor() as cursor:
        cursor.execute("SELECT name FROM sqlite_master WHERE type = 'trigger'")
        return names() <= {name for name, in cursor.fetchall()}


def reset():
    """Günlüğü, gelen kaydını, sayaçları ve durumu sıfırlar (yalnızca ilk kurulumda: sync_init --reset)."""
    with transaction.atomic():
        for model in (Change, Received, Counter, State):
            model.objects.all().delete()
        State.load()


def reinstall(**kwargs):
    """post_migrate: Django SQLite'ta tabloyu değiştiren migration'da tabloyu yeniden kurar, tetikleyicileri düşer."""
    if enabled() and connection.vendor == 'sqlite':
        install()


def check_triggers(**kwargs):
    """Sistem denetimi (check, runserver açılışı). Tablolar henüz yoksa (migrate'ten önce) sessiz."""
    if enabled() and 'sync_state' in connection.introspection.table_names() and not installed():
        return [checks.Warning('Eşitleme tetikleyicileri kurulu değil: python manage.py sync_init', id='sync.W001')]
    return []
