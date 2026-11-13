import json
from unittest import skipUnless

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.core import checks
from django.core.cache import cache
from django.core.management import call_command
from django.db import connection
from django.test import TestCase, override_settings
from django.utils import timezone

from accounts.models import User
from topics.models import Topic, TopicVote
from voting.tests import make_user

from . import capture
from .models import Change, Counter, State
from .tables import columns, digest, fingerprint, label, scored, tables

SQLITE = skipUnless(connection.vendor == 'sqlite', 'eşitleme yalnızca SQLite')
BASE = settings.SYNC['PK_BASE']
NODE1 = {**settings.SYNC, 'NODE': 1, 'KEY': 'k'}
NODE2 = {**settings.SYNC, 'NODE': 2, 'KEY': 'k'}


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

    def test_counters_are_per_node(self):  # veritabanı 1. düğümden kopyalandıktan sonra 2. düğüm kendi aralığını kullanır
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
