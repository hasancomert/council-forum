"""Değişikliği mesaja çevirme (pack) ve karşıdan geleni uygulama (apply). Ham SQL: Django modelleri araya girmesin
(auto_now alanları, ModAction'ın değişmezlik denetimi, pk ataması).
"""
import json
import zlib

from django.core.cache import cache
from django.db import IntegrityError, connection, transaction

from .gate import is_arbiter
from .models import Change, Received, State
from .tables import LOCAL, columns, quoted, scored, tables

CONFLICT, RENAMED, FAILED = 'çakışma', 'ad çakışması', 'uygulanamadı'


def pack(change):
    """Mesaj gövdesi: [tablo sırası, rid, seen, satır ya da None] JSON'u, zlib ile sıkıştırılmış."""
    row = None if change.data is None else json.loads(change.data)
    return zlib.compress(json.dumps([tables().index(change.tbl), change.rid, change.seen, row],
                                    separators=(',', ':'), ensure_ascii=False).encode())


def apply(seq, body):
    """Karşıdan gelen değişikliği tek işlemde uygular, notu döndürür. Akış hiçbir hatada durmaz: uygulanamayan
    mesajda da applied ilerler ve Received'a yazılır.
    """
    index, rid, seen, row = json.loads(zlib.decompress(body))
    table = tables()[index]
    try:
        with transaction.atomic():
            State.objects.filter(pk=1).update(applying=True)  # yazma kilidi; tetikleyiciler susar (yankı yok)
            # Çakışma (yalnızca hakemde): iki taraf aynı satırı birbirini görmeden değiştirdi, hakemin sürümü geçerli.
            if is_arbiter() and Change.objects.filter(tbl=table, rid=rid, id__gt=seen).exists():
                note = CONFLICT
            else:
                note = write(table, rid, row)
            finish(seq, table, rid, note)
    except IntegrityError:  # yabancı anahtar hatası işlem kapanırken çıkar: atomic()'in dışında yakalanır
        note = FAILED
        with transaction.atomic():
            finish(seq, table, rid, note)
    cache.clear()  # ana sayfa paneli güncellensin
    return note


def finish(seq, table, rid, note):
    State.objects.filter(pk=1).update(applying=False, applied=seq)
    Received.objects.create(seq=seq, tbl=table, rid=rid, note=note)


def write(table, rid, row):
    """Satırı yazar ya da siler. Yerel sütunlar yalnızca eklemede yazılır; ▲/▼ oyunda hedefin puanı oylardan."""
    note, cols, vote = '', columns(table), scored().get(table)
    with connection.cursor() as cursor:
        targets = set()
        if vote:  # eski hedef, satır değişmeden (silmede silinmeden) önce okunur
            cursor.execute(f'SELECT "{vote[0]}" FROM "{table}" WHERE id = %s', [rid])
            targets.update(target for target, in cursor.fetchall())
        if row is None:
            cursor.execute(f'DELETE FROM "{table}" WHERE id = %s', [rid])
        else:
            values = dict(zip(cols, row))
            if table == 'accounts_user':  # takma ad iki tarafta aynı anda alınmış: karşıdaki ekli adla yazılır
                # Ek önce çıkarılır: karşıda ekli adla saklanan üye orada değişince ad geri gelir; evinde asıl adı kalsın.
                values['username'] = name = values['username'].removesuffix(f'-{rid}')
                cursor.execute('SELECT 1 FROM accounts_user WHERE username = %s AND id != %s', [name, rid])
                if cursor.fetchone():
                    values['username'], note = f'{name}-{rid}', RENAMED
            local = {c: v(rid) if callable(v) else v for c, v in LOCAL.get(table, {}).items()}
            names = ['id', *cols, *local]
            update = ', '.join(f'"{c}" = excluded."{c}"' for c in cols)
            cursor.execute(f'INSERT INTO "{table}" ({quoted(names)}) VALUES ({", ".join(["%s"] * len(names))}) '
                           f'ON CONFLICT("id") DO UPDATE SET {update}', [rid, *values.values(), *local.values()])
            if vote:
                targets.add(values[vote[0]])
        for target in targets:
            cursor.execute(f'UPDATE "{vote[1]}" SET score = (SELECT COALESCE(SUM(value), 0) FROM "{table}" '
                           f'WHERE "{vote[0]}" = %s) WHERE id = %s', [target, target])
    return note
