import json
import zlib
from unittest import skipUnless

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.core import checks
from django.core.cache import cache
from django.core.management import call_command
from django.db import connection
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone

from accounts.models import User
from comments.models import Comment, CommentVote
from moderation.models import ModAction
from topics.models import Topic, TopicVote
from voting.models import TopicCloseProposal, Vote
from voting.tests import make_user

from . import capture
from .models import Change, Counter, Received, State
from .replay import apply, pack
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

    def test_fingerprint_follows_content_types(self):
        before = fingerprint()
        ContentType.objects.create(app_label='x', model='y')
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
