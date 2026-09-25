from datetime import timedelta

from django.conf import settings
from django.contrib import admin
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from comments.models import Comment, CommentVote
from voting.models import TopicCloseProposal
from voting.tests import make_user

from .models import Topic, TopicVote


class TopicTests(TestCase):
    def setUp(self):
        self.main = Topic.objects.create(title='Ana')
        self.sub = Topic.objects.create(title='Alt', parent=self.main)
        self.deleted_sub = Topic.objects.create(title='Silinmiş alt', parent=self.main, is_deleted=True)

    def set(self, topic, **fields):
        Topic.objects.filter(pk=topic.pk).update(**fields)

    def test_two_levels_only(self):
        Topic(title='Alt 2', parent=self.main).full_clean()
        with self.assertRaises(ValidationError):
            Topic(title='Torun', parent=self.sub).full_clean()

    def test_visible(self):
        self.assertQuerySetEqual(Topic.objects.visible(), [self.main, self.sub], ordered=False)
        self.set(self.main, is_deleted=True)
        self.assertFalse(Topic.objects.visible().exists())  # üst konusu silinen de gizli
        self.set(self.main, is_deleted=False)
        # Ana konu geri gelince her alt konu kendi durumuna döner
        self.assertQuerySetEqual(Topic.objects.visible(), [self.main, self.sub], ordered=False)

    def test_locked_is_inherited_not_written(self):
        self.assertFalse(Topic.objects.get(pk=self.sub.pk).is_locked)
        self.set(self.main, is_closed=True)
        sub = Topic.objects.get(pk=self.sub.pk)
        self.assertTrue(sub.is_locked)
        self.assertFalse(sub.is_closed)

    def test_pages(self):
        home = self.client.get('/')
        self.assertContains(home, self.main.get_absolute_url())
        self.assertNotContains(home, self.sub.get_absolute_url())  # ana sayfada yalnızca ana konular
        page = self.client.get(self.main.get_absolute_url())
        self.assertContains(page, self.sub.get_absolute_url())
        self.assertNotContains(page, self.deleted_sub.get_absolute_url())
        self.assertEqual(self.client.get(self.deleted_sub.get_absolute_url()).status_code, 404)
        self.set(self.main, is_closed=True)
        self.assertEqual(self.client.get(self.main.get_absolute_url()).status_code, 200)  # kapalı konu açılır
        self.set(self.main, is_deleted=True)
        self.assertEqual(self.client.get(self.sub.get_absolute_url()).status_code, 404)


class TopicVoteTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.alice, cls.bob = make_user('alice'), make_user('bob')

    def setUp(self):
        self.topic = Topic.objects.create(title='Konu', author=self.alice)

    def test_up_down_and_undo(self):
        for value, score in ((1, 1), (-1, -1), (-1, 0)):
            TopicVote.cast(self.topic, self.bob, value)
            self.topic.refresh_from_db()
            self.assertEqual(self.topic.score, score)
        self.assertFalse(TopicVote.objects.exists())  # ikinci ▼ oyu geri aldı

    def test_forbidden_votes(self):
        closed = Topic.objects.create(title='Kapalı', is_closed=True)
        cases = [
            (self.topic, self.alice),  # kendi konusu
            (self.topic, make_user('yeni', days=1)),  # 7 günlük olmayan hesap
            (closed, self.bob),
            (Topic.objects.create(title='Alt', parent=closed), self.bob),  # üst konusu kapalı: kilitli
            (Topic.objects.create(title='Silinmiş', is_deleted=True), self.bob),
        ]
        for topic, voter in cases:
            with self.subTest(topic=topic.title, voter=voter.username), self.assertRaisesMessage(ValueError, 'oy verilemez'):
                TopicVote.cast(topic, voter, 1)
        self.assertFalse(TopicVote.objects.exists())

    def test_view_and_privacy(self):
        self.client.force_login(self.bob)
        url = f'/topics/{self.topic.pk}/vote/'
        self.assertRedirects(self.client.post(url, {'value': '1'}), self.topic.get_absolute_url())
        self.assertContains(self.client.get(self.topic.get_absolute_url()), 'aria-pressed="true"')
        for value in ('5', 'abc'):
            self.assertContains(self.client.post(url, {'value': value}, follow=True), 'Geçersiz oy.')
        self.topic.refresh_from_db()
        self.assertEqual(self.topic.score, 1)
        self.assertFalse(admin.site.is_registered(TopicVote))  # kimin ne verdiği gizli

    def test_buttons_always_shown_disabled_with_reason(self):
        url = self.topic.get_absolute_url()
        cases = [(None, 'Oy vermek için giriş yap'), (self.alice, 'Kendi konuna oy verilmez'),
                 (make_user('yeni', days=1), 'hesabın en az'), (self.bob, None)]
        for user, why in cases:
            with self.subTest(user=user and user.username):
                self.client.logout() if user is None else self.client.force_login(user)
                html = self.client.get(url).content.decode()
                self.assertIn('aria-label="Artı oy"', html)  # ▲ puan ▼ her durumda
                self.assertEqual('disabled' in html.split('class="vote"')[1].split('</form>')[0], why is not None)
                if why:
                    self.assertIn(why, html)

    def test_page_groups_proposals_and_shows_running_close(self):
        child = Topic.objects.create(title='Alt', parent=self.topic, author=self.alice)
        p = TopicCloseProposal.objects.create(proposer=self.bob, topic=child)
        self.client.force_login(self.bob)
        r = self.client.get(self.topic.get_absolute_url())
        self.assertContains(r, '<summary>Diğer öneriler')
        self.assertContains(r, f'href="{p.get_absolute_url()}">Kapatma oylamasında</a>')  # alt konunun satırında
        self.assertContains(self.client.get(child.get_absolute_url()), 'Kapatma oylamasında')  # kendi başlığında
        self.assertContains(self.client.get('/?tab=sub'), 'Kapatma oylamasında')


class HomeTests(TestCase):
    """Sekmeler, sıralama ve sayfalama."""

    @classmethod
    def setUpTestData(cls):
        cls.alice, cls.bob, cls.carol = make_user('alice'), make_user('bob'), make_user('carol')

    def setUp(self):
        cache.clear()  # panel önbelleği testler arasında taşınmasın

    def titles(self, url='/'):
        return [t.title for t in self.client.get(url).context['page']]

    def test_popular(self):
        a, b, c = [Topic.objects.create(title=x, author=self.alice) for x in 'ABC']
        Comment.objects.create(target=a, author=self.bob, body='.')  # 3 puan
        old = Comment.objects.create(target=b, author=self.alice, body='.')
        Comment.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(days=8))  # pencere dışı
        CommentVote.cast(old, self.bob, 1)
        CommentVote.cast(old, self.carol, -1)  # 2 yorum oyu: 2 puan, yönüne bakılmaz
        Comment.objects.create(target=c, author=self.bob, body='.', is_deleted=True)  # silinmiş sayılmaz
        TopicVote.cast(c, self.bob, 1)  # 1 puan
        ranked = {t.title: t for t in Topic.objects.ranked('popular')}
        self.assertEqual({k: (t.heat, t.n_comments) for k, t in ranked.items()}, {'A': (3, 1), 'B': (2, 1), 'C': (1, 0)})
        self.assertIs(type(ranked['C'].heat), int)
        self.assertEqual(self.titles(), ['A', 'B', 'C'])
        with override_settings(FORUM={**settings.FORUM, 'POPULAR_WEIGHTS': {'comment': 1, 'vote': 1}}):
            self.assertEqual(self.titles(), ['B', 'C', 'A'])  # 2, 1, 1: eşitse yeni önde

    def test_most_votes_ties_newest_first(self):
        a, b, c = [Topic.objects.create(title=x, author=self.alice) for x in 'ABC']
        TopicVote.cast(a, self.bob, 1)
        self.assertEqual(self.titles('/?sort=votes'), ['A', 'C', 'B'])

    def test_tabs(self):
        main = Topic.objects.create(title='Ana')
        Topic.objects.create(title='Alt', parent=main)
        closed = Topic.objects.create(title='Kapalı ana', is_closed=True)
        Topic.objects.create(title='Kapalı alt', parent=main, is_closed=True)
        Topic.objects.create(title='Üstü kapalı alt', parent=closed)  # kendisi açık ama is_locked
        deleted = Topic.objects.create(title='Silinmiş', is_deleted=True)
        Topic.objects.create(title='Üstü silinmiş alt', parent=deleted)
        self.assertEqual(self.titles(), ['Ana'])
        self.assertEqual(self.titles('/?tab=sub'), ['Alt'])
        self.assertEqual(self.titles('/?tab=closed'), ['Üstü kapalı alt', 'Kapalı alt', 'Kapalı ana'])
        self.client.force_login(self.bob)
        r = self.client.get('/?tab=closed')
        self.assertContains(r, 'class="badge"', count=3)
        self.assertContains(r, 'Yeniden açmayı öner', count=2)  # miras kapalılıkta bağlantı üst konunun satırında
        self.assertContains(r, f'/proposals/new/undo/{closed.pk}/')
        self.assertEqual(self.titles(f'/?parent={main.pk}'), ['Alt'])  # süzgeçte varsayılan: alt konular
        self.assertEqual(self.titles(f'/?tab=closed&parent={main.pk}'), ['Kapalı alt'])

    def test_invalid_params_fall_back_to_defaults(self):
        Topic.objects.create(title='Ana')
        r = self.client.get('/?tab=x&sort=y&page=abc&parent=zz')
        self.assertEqual((r.context['tab'], r.context['sort'], r.context['page'].number), ('main', 'popular', 1))
        self.assertEqual(self.client.get('/?parent=999').status_code, 404)

    def test_queries_independent_of_topic_count(self):
        def queries():
            cache.clear()
            with CaptureQueriesContext(connection) as q:
                self.client.get('/')
            return len(q)

        self.client.get('/')  # ContentType önbelleği ısınsın
        Topic.objects.bulk_create([Topic(title=f'K{i}') for i in range(3)])
        few = queries()
        Topic.objects.bulk_create([Topic(title=f'K{i}') for i in range(3, 25)])
        self.assertEqual(queries(), few)
        self.assertEqual(len(self.client.get('/?page=2').context['page']), 5)

    def test_topic_page_lists_open_subtopics(self):
        main = Topic.objects.create(title='Ana')
        Topic.objects.bulk_create([Topic(title=f'Alt{i}', parent=main) for i in range(22)])
        Topic.objects.create(title='Kapalı alt', parent=main, is_closed=True)
        r = self.client.get(main.get_absolute_url())
        self.assertEqual(len(r.context['subs']), settings.FORUM['TOPICS_PER_PAGE'])
        self.assertContains(r, f'/?tab=sub&amp;parent={main.pk}">Tüm alt konular (22)')
        self.assertContains(r, f'/?tab=closed&amp;parent={main.pk}">Kapalı alt konular (1)')

    def test_archive_lists_only_deleted(self):
        Topic.objects.create(title='KapalıX', is_closed=True)
        Topic.objects.create(title='SilinenX', is_deleted=True)
        r = self.client.get('/topics/archive/')
        self.assertContains(r, 'SilinenX')
        self.assertNotContains(r, 'KapalıX')
