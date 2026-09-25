from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from comments.models import Comment, CommentVote
from topics.models import Topic
from voting.models import BaseProposal, TopicCloseProposal, TopicOpenProposal, active_proposals, open_proposal_count
from voting.tests import make_user

S = BaseProposal.Status


def make_moderator(name='yonetici'):
    user = make_user(name)
    user.is_moderator = True
    user.save(update_fields=['is_moderator'])
    return user


class ModTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.alice, cls.bob, cls.mod = make_user('alice'), make_user('bob'), make_moderator()

    def setUp(self):
        cache.clear()  # panel önbelleği testler arasında taşınmasın
        self.topic = Topic.objects.create(title='Konu', author=self.alice)

    def login(self, user):
        self.client.logout() if user is None else self.client.force_login(user)


class HidingTests(ModTestCase):
    def test_hidden_comment_masked_frozen_and_uncounted(self):
        c = Comment.objects.create(target=self.topic, author=self.alice, body='Gizli metin')
        Comment.objects.create(target=self.topic, author=self.bob, body='Duran yanıt', parent=c)
        c.set_hidden(True)
        url = self.topic.get_absolute_url()
        for user, sees in ((None, False), (self.bob, False), (self.alice, True), (self.mod, True)):
            with self.subTest(user=user and user.username):
                self.login(user)
                r = self.client.get(url)
                (self.assertContains if sees else self.assertNotContains)(r, 'Gizli metin')
                self.assertContains(r, 'Duran yanıt')  # yanıtlar yerinde kalır
        self.assertContains(r, 'Yorumlar (1)')  # gizli yorum sayılmaz
        self.assertEqual(Topic.objects.ranked('new').get().n_comments, 1)
        with self.assertRaisesMessage(ValueError, 'oy verilemez'):
            CommentVote.cast(c, self.bob, 1)
        self.login(self.alice)
        self.assertEqual(self.client.post(f'/comments/{c.pk}/edit/', {'body': 'x'}).status_code, 403)
        self.client.post(f'/comments/{c.pk}/delete/')  # yazarı yine silebilir
        c.refresh_from_db()
        self.assertTrue(c.is_deleted and c.is_hidden)

    def test_hidden_topic_page_opens_but_leaves_lists(self):
        t = Topic.objects.create(title='Troll başlık', description='Troll metin', author=self.alice)
        sub = Topic.objects.create(title='Alt başlık', parent=t)
        p = TopicCloseProposal.objects.create(proposer=self.bob, topic=t)
        t.set_hidden(True)
        r = self.client.get(t.get_absolute_url())  # 404 değil
        self.assertContains(r, 'Bu konu moderasyonla gizlendi.')
        self.assertNotContains(r, 'Troll')
        for url in ('/', '/?tab=sub', '/?tab=closed'):
            with self.subTest(url):
                self.assertNotContains(self.client.get(url), 'başlık')  # konu da alt konusu da listede yok
        self.assertEqual(str(p), 'Kapat: gizlenmiş konu')  # adı panelde ve öneri sayfasında da görünmez
        sub = Topic.objects.get(pk=sub.pk)
        self.assertFalse(sub.is_open)  # üst konusu gizli alt konu donar
        self.assertEqual(self.client.get(sub.get_absolute_url()).status_code, 200)
        self.login(self.alice)
        self.assertContains(self.client.get(t.get_absolute_url()), 'Troll metin')  # sahibi görür
        for kind in ('edit', 'undo'):
            self.assertEqual(self.client.get(f'/proposals/new/{kind}/{t.pk}/').status_code, 404)  # öneri almaz
        Topic.objects.filter(pk=t.pk).update(is_deleted=True)
        self.assertNotContains(self.client.get('/topics/archive/'), 'Troll')

    def test_hiding_running_proposal_cancels_it(self):
        p = TopicCloseProposal.objects.create(proposer=self.bob, topic=self.topic)
        self.assertEqual(open_proposal_count(self.bob), 1)
        p.set_hidden(True)
        self.assertEqual((p.status, open_proposal_count(self.bob)), (S.CANCELLED, 0))  # açık öneri sayısından düşer
        self.assertNotIn(p, active_proposals())  # panelde ve açık önerilerde yok
        self.assertFalse(TopicCloseProposal(proposer=self.alice, topic=self.topic).is_duplicate())  # ret yasağı yok
        TopicCloseProposal.objects.filter(pk=p.pk).update(voting_ends_at=timezone.now())
        p.refresh_from_db()
        p.finalize()
        self.topic.refresh_from_db()
        self.assertEqual((p.status, self.topic.is_closed), (S.CANCELLED, False))  # finalize atlar
        r = self.client.get(p.get_absolute_url())
        self.assertContains(r, 'Bu öneri moderasyonla gizlendi.')
        self.assertContains(r, 'İptal edildi')
        p.set_hidden(False)
        self.assertEqual(p.status, S.CANCELLED)  # gizleme kalkınca iptal kalır

    def test_hiding_expired_proposal_finalizes_it_first(self):
        p = TopicOpenProposal.objects.create(proposer=self.bob, title='Yeni')
        TopicOpenProposal.objects.filter(pk=p.pk).update(voting_ends_at=timezone.now())
        p.refresh_from_db()
        p.set_hidden(True)
        self.assertEqual(p.status, S.REJECTED)  # bitmiş oylama iptal edilmez (burada yeter sayı yok)
