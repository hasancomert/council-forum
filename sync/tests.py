import json
import random
import time
import zlib
from collections import deque
from datetime import UTC, datetime, timedelta
from unittest import skipUnless

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.core import checks
from django.core.cache import cache
from django.core.management import call_command
from django.db import connection
from django.test import SimpleTestCase, TestCase, TransactionTestCase, override_settings
from django.utils import timezone

from accounts.models import User
from comments.models import Comment, CommentVote
from moderation.models import ModAction
from topics.models import Topic, TopicVote
from voting.models import TopicCloseProposal, Vote
from voting.tests import make_user

from . import capture
from .context import sync_status
from .link import Link
from .models import Change, Counter, Received, State
from .ports import MemoryPort, SerialPort, SlipDecoder, airtime, slip_encode
from .replay import apply, pack
from .runner import Runner
from .tables import columns, digest, fingerprint, label, scored, tables

SQLITE = skipUnless(connection.vendor == 'sqlite', 'eşitleme yalnızca SQLite')
BASE = settings.SYNC['PK_BASE']
NODE1 = {**settings.SYNC, 'NODE': 1, 'KEY': 'k'}
NODE2 = {**settings.SYNC, 'NODE': 2, 'KEY': 'k'}


def message(change, rid=None, seen=None, data=True, **values):
    """Yakalanmış bir değişiklikten karşıdan gelmiş gibi mesaj: alanlar sütun adıyla değişir; data=None silmedir."""
    index, old_rid, old_seen, row = json.loads(zlib.decompress(pack(change)))
    row = None if data is None else [values.get(c, v) for c, v in zip(columns(change.tbl), row)]
    return zlib.compress(json.dumps([index, rid or old_rid, old_seen if seen is None else seen, row]).encode())


def snapshot():
    out = {}
    with connection.cursor() as cursor:
        for table in tables():
            names = ', '.join(f'"{c}"' for c in ['id', *columns(table)])
            cursor.execute(f'SELECT {names} FROM "{table}" ORDER BY id')
            out[table] = cursor.fetchall()
        for table in ('comments_comment', 'topics_topic'):
            cursor.execute(f'SELECT id, score FROM "{table}" ORDER BY id')
            out[f'{table}.score'] = cursor.fetchall()
    return out


@SQLITE
@override_settings(SYNC=NODE1)
class SyncTestCase(TestCase):
    def setUp(self):
        cache.clear()
        capture.install()


class TablesTests(TestCase):
    def test_synced_tables(self):
        self.assertEqual(tables(), sorted(tables()))
        self.assertEqual(len(tables()), 15)
        self.assertIn('accounts_user', tables())
        self.assertIn('voting_vote', tables())
        self.assertFalse([t for t in tables() if t.startswith(('sync_', 'django_', 'auth_'))])

    def test_columns_exclude_pk_and_local(self):
        cols = columns('accounts_user')
        for name in ('id', 'password', 'last_login', 'email', 'first_name', 'last_name', 'is_staff', 'is_superuser'):
            self.assertNotIn(name, cols)
        for name in ('username', 'role', 'is_moderator', 'banned_until', 'is_active', 'date_joined', 'deleted_at'):
            self.assertIn(name, cols)
        self.assertNotIn('score', columns('comments_comment'))
        self.assertIn('author_id', columns('comments_comment'))

    def test_scored_and_label(self):
        self.assertEqual(scored(), {'comments_commentvote': ('comment_id', 'comments_comment'),
                                    'topics_topicvote': ('topic_id', 'topics_topic')})
        self.assertEqual(label('comments_comment'), 'yorum')

    def test_vote_labels_are_turkish(self):  # modelinde Türkçe ad yok: hedefinden türetilir
        self.assertEqual((label('comments_commentvote'), label('topics_topicvote')), ('yorum oyu', 'konu oyu'))

    def test_fingerprint_follows_content_types(self):
        before = fingerprint()
        ContentType.objects.create(app_label='x', model='y')
        self.assertNotEqual(before, fingerprint())

    def test_fingerprint_changes_with_database_identity(self):  # kopyalanmadan ayrı kurulmuş veritabanı yakalansın
        before = fingerprint()
        capture.reset()  # sync_init --reset yeni kimlik üretir: ayrı kurulmuş öbür bilgisayar gibi
        self.assertNotEqual(before, fingerprint())

    def test_digest_ignores_local_columns(self):
        user = make_user('ali')
        before = digest()
        User.objects.filter(pk=user.pk).update(last_login=timezone.now(), first_name='Yeni')
        self.assertEqual(before, digest())
        User.objects.filter(pk=user.pk).update(role='B')
        self.assertNotEqual(before, digest())

    def test_state_is_single_row(self):
        self.assertEqual(State.load().pk, 1)
        self.assertEqual(State.load().applied, 0)
        self.assertEqual(State.objects.count(), 1)


class CaptureTests(SyncTestCase):
    def snap(self, change):
        return dict(zip(columns(change.tbl), json.loads(change.data)))

    def test_insert_update_delete_are_logged_with_snapshot(self):
        user = make_user('ali')  # INSERT + date_joined UPDATE'i
        rows = list(Change.objects.filter(tbl='accounts_user', rid=user.pk))
        self.assertEqual(len(rows), 2)
        self.assertEqual(self.snap(rows[-1])['username'], 'ali')
        self.assertNotIn('password', self.snap(rows[-1]))
        topic = Topic.objects.create(title='Bir', author=user)
        Topic.objects.filter(pk=topic.pk).update(is_closed=True)  # .update() de yakalanır
        self.assertEqual(self.snap(Change.objects.filter(tbl='topics_topic').last())['is_closed'], 1)
        vote = TopicVote.objects.create(topic=topic, voter=make_user('veli'), value=1)
        pk = vote.pk
        vote.delete()
        self.assertIsNone(Change.objects.filter(tbl='topics_topicvote', rid=pk).last().data)

    def test_local_column_changes_are_not_logged(self):
        user = make_user('ali')
        topic = Topic.objects.create(title='Bir', author=user)
        count = Change.objects.count()
        User.objects.filter(pk=user.pk).update(last_login=timezone.now(), first_name='Yeni')
        Topic.objects.filter(pk=topic.pk).update(score=5)
        self.assertEqual(Change.objects.count(), count)

    def test_applying_flag_silences_triggers_and_seen_is_recorded(self):
        State.objects.filter(pk=1).update(applying=True)
        make_user('ali')
        self.assertFalse(Change.objects.exists())
        State.objects.filter(pk=1).update(applying=False, applied=7)
        make_user('veli')
        self.assertEqual(Change.objects.first().seen, 7)

    def test_install_keeps_log_and_reset_clears_it(self):
        make_user('ali')
        count = Change.objects.count()
        capture.install()
        self.assertEqual(Change.objects.count(), count)
        capture.reset()
        self.assertFalse(Change.objects.exists())
        self.assertTrue(capture.installed())

    def test_missing_trigger_is_reported_and_restored_by_migrate(self):
        with connection.cursor() as cursor:
            cursor.execute('DROP TRIGGER sync_topics_topic_u')
        self.assertFalse(capture.installed())
        self.assertIn('sync.W001', [m.id for m in checks.run_checks()])
        call_command('migrate', verbosity=0)
        self.assertTrue(capture.installed())

    @override_settings(SYNC={**settings.SYNC, 'NODE': 0})
    def test_migrate_does_not_install_when_disabled(self):
        with connection.cursor() as cursor:
            cursor.execute('DROP TRIGGER sync_topics_topic_u')
        call_command('migrate', verbosity=0)
        self.assertFalse(capture.installed())


class PkTests(SyncTestCase):
    def test_node1_counts_up_in_low_range(self):
        ali, veli = make_user('ali'), make_user('veli')
        self.assertEqual(veli.pk, ali.pk + 1)
        self.assertLess(veli.pk, BASE)

    @override_settings(SYNC=NODE2)
    def test_node2_uses_high_range(self):
        ali = make_user('ali')
        topic = Topic.objects.create(title='Bir', author=ali)
        self.assertEqual((ali.pk, topic.pk), (BASE, BASE))
        self.assertEqual(make_user('veli').pk, BASE + 1)

    def test_peer_rows_do_not_move_local_range(self):
        ali = make_user('ali')
        User.objects.create(pk=BASE + 5, username='uzak', email='u@x.invalid', first_name='', last_name='')
        self.assertEqual(make_user('veli').pk, ali.pk + 1)

    def test_peer_first_row_does_not_move_local_range(self):  # karşının ilk satırı (pk = PK_BASE) önce gelirse
        User.objects.create(pk=BASE, username='uzak', email='u@x.invalid', first_name='', last_name='')
        self.assertLess(make_user('ali').pk, BASE)

    def test_counters_are_per_node(self):  # veritabanı 1. düğümden kopyalanınca 2. düğüm kendi aralığını kullanır
        make_user('ali')
        with self.settings(SYNC=NODE2):
            self.assertEqual(make_user('veli').pk, BASE)

    @override_settings(SYNC={**settings.SYNC, 'NODE': 0})
    def test_disabled_leaves_pk_to_database(self):
        make_user('ali')
        self.assertFalse(Counter.objects.exists())

    def test_unsynced_models_are_untouched(self):
        ContentType.objects.create(app_label='x', model='y')
        self.assertFalse(Counter.objects.filter(key__contains='content_type').exists())


class ReplayTests(SyncTestCase):
    def last(self, table):
        return Change.objects.filter(tbl=table).last()

    def build_forum(self):
        ali, veli = make_user('ali'), make_user('veli', 'B')
        main = Topic.objects.create(title='Ana konu', description='Açıklama', author=ali)
        sub = Topic.objects.create(title='Alt konu', parent=main, author=veli)
        long = ('ğüşiöçİ "tırnak" \\ ters\nsatır 🙂 ' * 200)[:5000]
        first = Comment.objects.create(target=main, author=ali, body=long)
        reply = Comment.objects.create(target=main, author=veli, body='yanıt', parent=first)
        CommentVote.cast(first, veli, 1)
        CommentVote.cast(reply, ali, -1)
        TopicVote.cast(main, veli, 1)
        TopicVote.cast(sub, ali, 1)
        TopicVote.cast(sub, ali, 1)  # ikinci basış oyu geri alır: satır silinir
        reply.refresh_from_db()  # düzenleme görünümü gibi güncel satırdan: bellekteki eski puan (0) geri yazılmasın
        reply.body, reply.edited_at = 'düzenlendi', timezone.now()
        reply.save()
        proposal = TopicCloseProposal.objects.create(proposer=ali, topic=sub)
        Vote.cast(proposal=proposal, voter=veli, choice='yes')
        Vote.cast(proposal=proposal, voter=veli, choice='no')
        ModAction.objects.create(moderator=ali, user=veli, kind='hide', reason='troll', note='not',
                                 content_type=ContentType.objects.get_for_model(Comment), object_id=reply.pk)
        reply.set_hidden(True)

    def test_log_replays_into_emptied_tables(self):
        self.build_forum()
        before = snapshot()
        State.objects.filter(pk=1).update(applying=True)
        with connection.cursor() as cursor:
            for table in tables():
                cursor.execute(f'DELETE FROM "{table}"')
        State.objects.filter(pk=1).update(applying=False)
        with self.settings(SYNC=NODE2):  # hakem olmayan düğüm geleni koşulsuz uygular
            for change in Change.objects.all():
                self.assertEqual(apply(change.id, pack(change)), '')
        self.assertEqual(snapshot(), before)
        self.assertEqual(Comment.objects.get(parent=None).body, ('ğüşiöçİ "tırnak" \\ ters\nsatır 🙂 ' * 200)[:5000])

    def test_peer_row_is_created_with_local_defaults_and_no_echo(self):
        make_user('ali')
        note = apply(1, message(self.last('accounts_user'), rid=BASE + 1, username='uzak'))
        peer = User.objects.get(pk=BASE + 1)
        self.assertEqual((note, peer.username, peer.password, peer.email, peer.first_name, peer.is_staff),
                         ('', 'uzak', '!', f'{BASE + 1}@uzak.invalid', '', False))
        self.assertEqual(State.load().applied, 1)
        self.assertEqual(Received.objects.get().note, '')
        self.assertFalse(Change.objects.filter(rid=BASE + 1).exists())

    def test_update_keeps_local_columns(self):
        ali = make_user('ali')
        change = self.last('accounts_user')
        apply(1, message(change, seen=change.id, role='B'))
        ali.refresh_from_db()
        self.assertEqual((ali.role, ali.email, ali.first_name), ('B', 'ali@example.com', 'Ad'))

    def test_arbiter_keeps_its_version_on_conflict(self):
        topic = Topic.objects.create(title='Yerel', author=make_user('ali'))
        incoming = message(self.last('topics_topic'), seen=0, title='Karşı')
        self.assertEqual(apply(1, incoming), 'çakışma')
        topic.refresh_from_db()
        self.assertEqual((topic.title, State.load().applied, Received.objects.get().note), ('Yerel', 1, 'çakışma'))
        with self.settings(SYNC=NODE2):
            self.assertEqual(apply(2, incoming), '')
        topic.refresh_from_db()
        self.assertEqual(topic.title, 'Karşı')

    def test_username_clash_gets_suffix_every_time(self):
        make_user('ali')
        change = self.last('accounts_user')
        self.assertEqual(apply(1, message(change, rid=BASE + 3)), 'ad çakışması')
        self.assertEqual(User.objects.get(pk=BASE + 3).username, f'ali-{BASE + 3}')
        self.assertEqual(apply(2, message(change, rid=BASE + 3, role='B')), 'ad çakışması')
        peer = User.objects.get(pk=BASE + 3)
        self.assertEqual((peer.username, peer.role), (f'ali-{BASE + 3}', 'B'))

    def test_suffixed_name_coming_back_keeps_home_name(self):  # karşıda ekli adla saklanan üye orada değişince
        ali = make_user('ali')
        change = self.last('accounts_user')
        apply(1, message(change, seen=change.id, username=f'ali-{ali.pk}', role='B'))
        ali.refresh_from_db()
        self.assertEqual((ali.username, ali.role), ('ali', 'B'))

    def test_votes_recompute_score(self):
        ali, veli, can = make_user('ali'), make_user('veli'), make_user('can')
        topic = Topic.objects.create(title='Bir', author=ali)
        comment = Comment.objects.create(target=topic, author=ali, body='x')
        CommentVote.cast(comment, veli, 1)
        vote = self.last('comments_commentvote')
        apply(1, message(vote, rid=BASE + 1, seen=vote.id, voter_id=can.pk))
        comment.refresh_from_db()
        self.assertEqual(comment.score, 2)
        apply(2, message(vote, rid=BASE + 1, data=None))
        comment.refresh_from_db()
        self.assertEqual(comment.score, 1)

    def test_unappliable_message_does_not_stop_stream(self):
        ali, veli = make_user('ali'), make_user('veli')
        topic = Topic.objects.create(title='Bir', author=ali)
        comment = Comment.objects.create(target=topic, author=ali, body='x')
        CommentVote.cast(comment, veli, 1)
        vote = self.last('comments_commentvote')
        self.assertEqual(apply(1, message(vote, rid=BASE + 1)), 'uygulanamadı')  # aynı (yorum, üye), başka pk
        self.assertEqual((State.load().applied, Received.objects.first().note), (1, 'uygulanamadı'))
        self.assertEqual(apply(2, message(self.last('accounts_user'), rid=BASE + 9, username='uzak')), '')
        self.assertEqual(State.load().applied, 2)

    def test_cache_is_cleared(self):
        make_user('ali')
        cache.set('x', 1)
        apply(1, message(self.last('accounts_user'), rid=BASE + 1, username='uzak'))
        self.assertIsNone(cache.get('x'))


@SQLITE
class ForeignKeyTests(TransactionTestCase):
    """Yabancı anahtar hatası işlem kapanırken çıkar: TestCase'in sardığı işlemde görünmez, burada gerçek işlem var."""
    def setUp(self):
        capture.install()

    def tearDown(self):  # tetikleyiciler kalsa veritabanını boşaltan flush da günlüğe yazardı
        with connection.cursor() as cursor:
            for name in capture.names():
                cursor.execute(f'DROP TRIGGER "{name}"')

    @override_settings(SYNC=NODE2)
    def test_missing_reference_does_not_stop_stream(self):
        ali = make_user('ali')
        Comment.objects.create(target=Topic.objects.create(title='Bir', author=ali), author=ali, body='x')
        orphan = message(Change.objects.filter(tbl='comments_comment').last(), rid=BASE + 5, author_id=BASE + 99)
        self.assertEqual(apply(1, orphan), 'uygulanamadı')
        self.assertEqual((Comment.objects.filter(pk=BASE + 5).exists(), State.load().applied), (False, 1))


class PortTests(SimpleTestCase):
    def test_slip_round_trip(self):
        data = bytes([0xC0, 0xDB, 1, 0xDC, 0xDD, 0xC0])
        wire = slip_encode(data) + slip_encode(b'ikinci')
        decoder = SlipDecoder()
        self.assertEqual(decoder.feed(wire[:3]) + decoder.feed(wire[3:]), [data, b'ikinci'])
        self.assertNotIn(0xC0, slip_encode(data)[1:-1])

    def test_airtime_sf7(self):
        self.assertAlmostEqual(airtime(210), 0.3331, places=3)
        self.assertAlmostEqual(airtime(11), 0.0412, places=3)

    def test_memory_pair(self):
        a, b = MemoryPort.pair()
        a.write(b'x')
        self.assertEqual(b.read(), (-50, 10, b'x'))
        self.assertIsNone(b.read())
        self.assertIsNone(a.read())
        a.loss = 1.0
        a.write(b'y')
        self.assertIsNone(b.read())

    def test_serial_port_survives_missing_device(self):
        with self.assertLogs('sync', level='WARNING'):  # "Hat açılamadı"
            port = SerialPort('COM_YOK_99')
            port.write(b'x')
            self.assertIsNone(port.read())

    def test_serial_port_reports_open_failure_once(self):  # yanlış port "karşı kapalı"dan ayırt edilsin
        with self.assertLogs('sync', level='WARNING') as logs:
            port = SerialPort('COM_YOK_99')
            port.read()
            port.retry_at = 0  # yeniden deneme zamanı geldi
            port.read()
        self.assertEqual(len(logs.records), 1)
        self.assertIn('COM_YOK_99', logs.records[0].getMessage())


class FakeHost:
    def __init__(self, **messages):
        self.out = {int(k[1:]): v for k, v in messages.items()}  # m1=b'..' -> {1: b'..'}
        self.sent, self.got, self.calls, self.statuses, self.ok = 0, {}, 0, [], True

    def applied(self):
        return max(self.got, default=0)

    def next_message(self):
        pending = sorted(seq for seq in self.out if seq > self.sent)
        return (pending[0], self.out[pending[0]]) if pending else None

    def delivered(self, seq):
        self.sent = seq

    def deliver(self, seq, body):
        self.calls += 1
        if self.ok:
            self.got[seq] = body
        return self.ok

    def status(self):
        return 1000, max(self.out, default=0), 42

    def on_status(self, *args):
        self.statuses.append(args)


class RadioPort:
    """Yarı çift yönlü telsiz: paket airtime() boyunca havada, üst üste binen paketlerin ikisi de kaybolur."""
    def __init__(self, sky, now):
        self.sky, self.now, self.inbox, self.peer = sky, now, deque(), None

    @classmethod
    def pair(cls, now):
        sky = []  # havadakiler: [başlangıç, bitiş, alıcı, paket, bozuldu]
        a, b = cls(sky, now), cls(sky, now)
        a.peer, b.peer = b, a
        return a, b

    def write(self, packet):
        start = self.now()
        item = [start, start + airtime(len(packet)), self.peer, packet, False]
        for other in self.sky:
            if other[0] < item[1] and start < other[1]:
                other[4] = item[4] = True
        self.sky.append(item)

    def read(self):
        for item in [i for i in self.sky if i[1] <= self.now()]:
            self.sky.remove(item)
            if not item[4]:
                item[2].inbox.append((-50, 10, item[3]))
        return self.inbox.popleft() if self.inbox else None


class LinkTests(SimpleTestCase):
    def setUp(self):
        self.t = 0.0
        self.rng = random.Random(1)

    def pair(self, ha, hb, loss=0.0):
        self.pa, self.pb = MemoryPort.pair(loss, self.rng.random)
        make = lambda port, host, node: Link(port, host, node=node, key=b'k', now=lambda: self.t, rng=self.rng.random)
        return make(self.pa, ha, 1), make(self.pb, hb, 2)

    def run_for(self, links, seconds, dt=0.05):
        for _ in range(int(seconds / dt)):
            self.t += dt
            for link in links:
                link.step()

    def test_messages_cross_a_lossy_link_in_order(self):
        big = self.rng.randbytes(20000)
        ha, hb = FakeHost(m1=b'bir', m2=big, m3=b''), FakeHost(m1=b'x', m2=b'y')
        links = self.pair(ha, hb, loss=0.3)
        self.run_for(links, 900)
        self.assertEqual(hb.got, {1: b'bir', 2: big, 3: b''})
        self.assertEqual(ha.got, {1: b'x', 2: b'y'})
        self.assertEqual((ha.sent, hb.sent, hb.calls), (3, 2, 3))

    def test_foreign_own_and_broken_packets_are_ignored(self):
        ha, hb = FakeHost(), FakeHost()
        la, lb = self.pair(ha, hb)
        stranger = Link(self.pa, FakeHost(m1=b'x'), node=1, key=b'baska', now=lambda: self.t, rng=self.rng.random)
        echo = Link(self.pa, FakeHost(m1=b'x'), node=2, key=b'k', now=lambda: self.t, rng=self.rng.random)
        with self.assertLogs('sync', level='WARNING') as logs:  # iki bilgisayarda aynı SYNC_NODE
            self.run_for([stranger, echo, lb], 3)
        self.assertEqual(len(logs.records), 1)
        self.assertIn('SYNC_NODE', logs.records[0].getMessage())
        self.pa.write(b'D\x01')
        self.pa.write(b'')
        self.run_for([lb], 1)
        self.assertEqual((hb.got, hb.statuses, lb.heard), ({}, [], None))

    def test_duplicate_of_applied_message_is_acked_not_redelivered(self):
        ha, hb = FakeHost(m1=b'bir'), FakeHost()
        links = self.pair(ha, hb)
        self.run_for(links, 3)
        ha.sent = 0  # gönderen onayı kaçırmış gibi yeniden yollar
        self.run_for(links, 3)
        self.assertEqual((ha.sent, hb.calls), (1, 1))

    def test_no_ack_when_host_refuses(self):
        ha, hb = FakeHost(m1=b'bir'), FakeHost()
        hb.ok = False
        links = self.pair(ha, hb)
        self.run_for(links, 10)
        self.assertEqual((ha.sent, hb.got), (0, {}))
        hb.ok = True
        self.run_for(links, 30)
        self.assertEqual((ha.sent, hb.got), (1, {1: b'bir'}))

    def test_restarted_receiver_gets_message_from_first_part(self):
        big = self.rng.randbytes(2000)
        ha, hb = FakeHost(m1=big), FakeHost()
        la, lb = self.pair(ha, hb)
        self.run_for([la, lb], 1.5)  # birkaç parça gitti
        self.assertEqual(hb.got, {})
        fresh = Link(self.pb, hb, node=2, key=b'k', now=lambda: self.t, rng=self.rng.random)
        self.run_for([la, fresh], 120)
        self.assertEqual(hb.got, {1: big})

    def test_status_is_exchanged_when_idle(self):
        ha, hb = FakeHost(), FakeHost()
        self.run_for(self.pair(ha, hb), 12)
        self.assertGreaterEqual(len(hb.statuses), 2)
        self.assertEqual(hb.statuses[0], (1000, 0, 0, 42))

    def test_status_continues_during_a_message(self):  # alıcı şemayı mesajın ortasında da öğrenebilsin
        ha, hb = FakeHost(m1=b'bir'), FakeHost()
        hb.ok = False  # mesaj hiç bitmez
        self.run_for(self.pair(ha, hb), 12)
        self.assertGreaterEqual(len(hb.statuses), 2)

    def test_link_goes_down_and_recovers(self):
        ha, hb = FakeHost(m1=b'bir'), FakeHost()
        la, lb = self.pair(ha, hb, loss=1.0)
        self.run_for([la, lb], 30)
        self.assertFalse(la.online)
        self.pa.loss = self.pb.loss = 0.0
        self.run_for([la, lb], 30)
        self.assertTrue(la.online)
        self.assertEqual(hb.got, {1: b'bir'})

    def test_airtime_budget_holds_data(self):
        budget = 3600 * 0.05 / 100  # 1,8 sn
        with self.settings(SYNC={**settings.SYNC, 'AIRTIME_PERCENT': 0.05}):
            ha, hb = FakeHost(m1=self.rng.randbytes(2000)), FakeHost()  # 10 parça, yaklaşık 3,3 sn yayın
            la, lb = self.pair(ha, hb)
            self.run_for([la, lb], 300)
            self.assertEqual(hb.got, {})
            self.assertLessEqual(la.airtime_used(), budget + airtime(255))
            self.run_for([la, lb], 3600 * 4, dt=0.5)  # bütçe saat saat açılır
            self.assertEqual(len(hb.got), 1)

    def radio(self, ha, hb):
        pa, pb = RadioPort.pair(lambda: self.t)
        make = lambda port, host, node: Link(port, host, node=node, key=b'k', now=lambda: self.t, rng=self.rng.random)
        return make(pa, ha, 1), make(pb, hb, 2)

    def test_idle_nodes_started_together_hear_each_other(self):  # durum aralığı rastgele: telsizde kilitlenmesinler
        ha, hb = FakeHost(), FakeHost()
        self.run_for(self.radio(ha, hb), 60)
        self.assertTrue(ha.statuses and hb.statuses)

    def test_two_down_nodes_do_not_retry_in_lockstep(self):  # "bağlantı yok" denemeleri de rastgele aralıklı
        ha, hb = FakeHost(m1=b'bir'), FakeHost(m1=b'iki')
        la, lb = self.radio(ha, hb)
        la.misses = lb.misses = settings.SYNC['DOWN_AFTER']  # ikisi de "bağlantı yok" kipinde başlar
        self.run_for([la, lb], 120)
        self.assertEqual((ha.got, hb.got), ({1: b'iki'}, {1: b'bir'}))

    def test_two_way_transfer_survives_collisions(self):
        ha, hb = FakeHost(m1=self.rng.randbytes(4000)), FakeHost(m1=self.rng.randbytes(4000))
        self.run_for(self.radio(ha, hb), 600)
        self.assertEqual((len(ha.got), len(hb.got)), (1, 1))

    def test_failed_delivered_does_not_wedge_sender(self):  # ör. veritabanı kilitli: onay yeniden gelince yeniden dener
        class Flaky(FakeHost):
            def delivered(self, seq):
                if not getattr(self, 'failed', False):
                    self.failed = True
                    raise OSError('veritabanı kilitli')
                super().delivered(seq)

        ha, hb = Flaky(m1=b'bir', m2=b'iki'), FakeHost()
        links = self.pair(ha, hb)
        for _ in range(400):  # Runner.tick gibi: istisna günlüğe yazılır, döngü sürer
            self.t += 0.05
            for link in links:
                try:
                    link.step()
                except Exception:
                    pass
        self.assertEqual((ha.sent, hb.got), (2, {1: b'bir', 2: b'iki'}))


class RunnerTests(SyncTestCase):
    def setUp(self):
        super().setUp()
        self.runner = Runner(MemoryPort.pair()[0])

    def peer_user(self, rid):
        make_user(f'u{rid}')
        return message(Change.objects.filter(tbl='accounts_user').last(), rid=rid, username=f'uzak{rid}')

    def test_outbox_follows_peer_applied(self):
        self.assertIsNone(self.runner.next_message())
        make_user('ali')
        first = Change.objects.first()
        self.assertEqual(self.runner.next_message(), (first.id, pack(first)))
        self.runner.delivered(first.id)
        self.assertEqual(self.runner.next_message()[0], first.id + 1)
        self.assertEqual(State.load().peer_applied, first.id)

    def test_status_sets_synced_until_only_after_everything_applied(self):
        when = datetime.fromtimestamp(2_000_000_000, UTC)
        self.runner.on_status(2_000_000_000, 2, 0, fingerprint())
        self.assertIsNone(State.load().synced_until)
        self.assertTrue(self.runner.deliver(1, self.peer_user(BASE + 1)))
        self.assertIsNone(State.load().synced_until)
        self.assertTrue(self.runner.deliver(2, self.peer_user(BASE + 2)))
        self.assertEqual(State.load().synced_until, when)
        self.runner.on_status(1_900_000_000, 2, 0, fingerprint())  # karşının saati geri alındı
        self.assertEqual(State.load().synced_until, datetime.fromtimestamp(1_900_000_000, UTC))  # eskisi güvenli değil

    def test_schema_mismatch_blocks_apply(self):
        incoming = self.peer_user(BASE + 1)  # bir kez: her çağrı aynı yerel üyeyi yeniden oluşturmaya çalışır
        with self.assertLogs('sync', level='WARNING'):  # "Veritabanları uyumsuz"
            self.runner.on_status(1, 0, 0, fingerprint() + 1)
        self.assertFalse(State.load().schema_ok)
        self.assertFalse(self.runner.deliver(1, incoming))
        self.assertEqual(State.load().applied, 0)
        self.runner.on_status(1, 0, 0, fingerprint())
        self.assertTrue(State.load().schema_ok)
        self.assertTrue(self.runner.deliver(1, incoming))

    def test_nothing_applied_before_peer_schema_is_known(self):  # ilk durum paketi kaybolsa da
        self.assertFalse(self.runner.deliver(1, self.peer_user(BASE + 1)))
        self.assertEqual(State.load().applied, 0)

    def test_terminal_line_for_incoming_message(self):
        incoming = self.peer_user(BASE + 1)
        self.runner.on_status(1, 0, 0, fingerprint())
        with self.assertLogs('sync', level='INFO') as logs:
            self.runner.deliver(1, incoming)
        self.assertEqual(logs.records[-1].getMessage(), f'gelen  #1 kullanıcı {BASE + 1}')

    def test_peer_clock_set_back_withdraws_synced_until(self):  # karşı o saate kadar yeniden oy kabul eder
        self.runner.on_status(2_000_000_000, 0, 0, fingerprint())
        self.runner.on_status(1_900_000_000, 3, 0, fingerprint())  # saat geri alındı, yeni değişiklikler henüz gelmedi
        self.assertIsNone(State.load().synced_until)

    def test_peer_ack_never_goes_back(self):
        self.runner.on_status(1, 0, 9, fingerprint())
        self.runner.on_status(1, 0, 4, fingerprint())
        self.assertEqual(State.load().peer_applied, 9)

    def test_clock_offset_recorded(self):
        self.runner.on_status(int(time.time()) + 3600, 0, 0, fingerprint())
        self.assertAlmostEqual(State.load().clock_offset, 3600, delta=2)

    def test_port_errors_do_not_kill_the_loop(self):
        class Broken:
            def read(self):
                raise OSError('port yok')

            def write(self, packet):
                raise OSError('port yok')

        runner = Runner(Broken())
        with self.assertLogs('sync', level='ERROR'):
            runner.tick()
            runner.tick()
        self.assertIsNone(State.load().heard_at)

    def test_schema_mismatch_is_reported_once(self):
        with self.assertLogs('sync', level='WARNING') as logs:
            self.runner.on_status(1, 0, 0, fingerprint() + 1)
            self.runner.on_status(1, 0, 0, fingerprint() + 1)
        self.assertEqual(len(logs.records), 1)
        self.assertIn('uyumsuz', logs.records[0].getMessage())


QUORUM2 = {**settings.FORUM, 'QUORUM_MIN': 2}


@override_settings(FORUM=QUORUM2)
class GateTests(SyncTestCase):
    def ended(self, **changes):
        ali, veli = make_user('ali'), make_user('veli')
        self.topic = Topic.objects.create(title='Konu', author=ali)
        proposal = TopicCloseProposal.objects.create(proposer=ali, topic=self.topic)
        for voter in (ali, veli):
            Vote.cast(proposal=proposal, voter=voter, choice='yes')
        changes = {'voting_ends_at': timezone.now() - timedelta(seconds=10)} | changes
        TopicCloseProposal.objects.filter(pk=proposal.pk).update(**changes)
        proposal.refresh_from_db()
        return proposal

    def synced(self, proposal, seconds):
        State.objects.filter(pk=1).update(synced_until=proposal.voting_ends_at + timedelta(seconds=seconds))

    @override_settings(SYNC={**settings.SYNC, 'NODE': 0})
    def test_disabled_sync_finalizes_as_before(self):
        proposal = self.ended()
        proposal.finalize()
        self.assertEqual(proposal.status, 'applied')

    @override_settings(SYNC=NODE2)
    def test_follower_never_finalizes_or_applies(self):
        proposal = self.ended()
        proposal.finalize()
        self.assertEqual(proposal.status, 'voting')
        TopicCloseProposal.objects.filter(pk=proposal.pk).update(status='accepted')  # hakemden ara durum gelmiş gibi
        proposal.refresh_from_db()
        proposal.finalize()
        self.topic.refresh_from_db()
        self.assertEqual((proposal.status, self.topic.is_closed), ('accepted', False))

    def test_arbiter_waits_for_peer(self):
        proposal = self.ended()
        proposal.finalize()
        self.assertEqual(proposal.status, 'voting')  # karşıdan hiç durum gelmedi
        self.synced(proposal, -3600)  # karşının saati bir saat geride: bitişi henüz geçmedi
        proposal.finalize()
        self.assertEqual(proposal.status, 'voting')
        self.synced(proposal, 2)  # pay (3 sn) dolmadı
        proposal.finalize()
        self.assertEqual(proposal.status, 'voting')
        self.synced(proposal, 3)
        proposal.finalize()
        self.topic.refresh_from_db()
        self.assertEqual((proposal.status, self.topic.is_closed), ('applied', True))

    @override_settings(SYNC=NODE2)
    def test_hiding_ended_unfinalized_proposal_does_not_cancel(self):
        proposal = self.ended()
        proposal.set_hidden(True)
        self.assertEqual((proposal.status, proposal.is_hidden), ('voting', True))

    @override_settings(SYNC=NODE2)
    def test_hiding_running_proposal_still_cancels(self):
        proposal = self.ended(voting_ends_at=timezone.now() + timedelta(hours=1))
        proposal.set_hidden(True)
        self.assertEqual(proposal.status, 'cancelled')

    @override_settings(SYNC=NODE2)
    def test_detail_page_says_waiting(self):
        proposal = self.ended()
        self.client.force_login(User.objects.get(username='veli'))
        response = self.client.get(proposal.get_absolute_url())
        self.assertContains(response, 'sonuç iki forum eşitlenince açıklanacak')
        self.assertNotContains(response, 'name="choice"')

    def test_arbiter_runner_finalizes_due_proposals(self):
        proposal = self.ended()
        self.synced(proposal, 60)
        clock = [0.0]
        runner = Runner(MemoryPort.pair()[0], now=lambda: clock[0])
        clock[0] = settings.SYNC['FINALIZE_SECONDS'] + 1
        runner.tick()
        proposal.refresh_from_db()
        self.assertEqual(proposal.status, 'applied')
        self.assertTrue(Change.objects.filter(tbl='voting_topiccloseproposal', rid=proposal.pk,
                                              data__contains='applied').exists())


class UiTests(SyncTestCase):
    @override_settings(SYNC={**settings.SYNC, 'NODE': 0})
    def test_disabled_site_has_no_badge_and_no_pages(self):
        self.assertNotContains(self.client.get('/'), 'LoRa')
        self.assertEqual(self.client.get('/sync/').status_code, 404)
        self.assertEqual(self.client.get('/sync/status.json').status_code, 404)
        with self.assertNumQueries(0):
            self.assertEqual(sync_status(None), {})

    def test_badge_shows_link_state_and_pending(self):
        make_user('ali')  # 2 bekleyen kayıt
        response = self.client.get('/')
        self.assertContains(response, 'LoRa: bağlantı yok')
        self.assertContains(response, 'bekleyen 2')
        State.objects.filter(pk=1).update(heard_at=timezone.now(), peer_applied=Change.objects.last().id)
        response = self.client.get('/')
        self.assertContains(response, 'LoRa: bağlı')
        self.assertNotContains(response, 'bekleyen')

    def test_status_json(self):
        self.assertEqual(self.client.get('/sync/status.json').json(),
                         {'node': 1, 'arbiter': True, 'online': False, 'pending': 0, 'applied': 0, 'schema_ok': True})

    def test_status_page_warnings(self):
        self.assertNotContains(self.client.get('/sync/'), 'Saat farkı')
        State.objects.filter(pk=1).update(clock_offset=3600, schema_ok=False)
        response = self.client.get('/sync/')
        self.assertContains(response, 'Saat farkı')
        self.assertContains(response, 'Veritabanları uyumsuz')

    def test_status_page_lists_traffic_without_content(self):
        ali = make_user('ali')
        topic = Topic.objects.create(title='Bir', author=ali)
        comment = Comment.objects.create(target=topic, author=ali, body='gizli-metin')
        response = self.client.get('/sync/')
        self.assertContains(response, 'Yorum')  # satır başında: Türkçe capfirst (CLAUDE.md, etiketler)
        self.assertContains(response, f'#{comment.pk}')
        self.assertContains(response, digest())
        self.assertNotContains(response, 'gizli-metin')

    def test_status_page_has_no_inline_style_or_script(self):
        self.assertNotRegex(self.client.get('/sync/').content.decode(), r'style=|<style|<script>')
