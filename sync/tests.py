from unittest import skipUnless

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.core.cache import cache
from django.db import connection
from django.test import TestCase, override_settings
from django.utils import timezone

from accounts.models import User
from voting.tests import make_user

from .models import State
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
