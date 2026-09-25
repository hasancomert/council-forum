from django.contrib.contenttypes.models import ContentType
from django.template import Context, Template
from django.test import RequestFactory, TestCase
from django.utils import timezone

from topics.models import Topic
from voting.models import RequestProposal, TopicCloseProposal, active_member_count
from voting.tests import make_user

from .models import Comment, CommentVote


def add_url(target):
    return f'/comments/{ContentType.objects.get_for_model(target).pk}/{target.pk}/'


class CommentTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.alice, cls.bob = make_user('alice'), make_user('bob')

    def setUp(self):
        self.topic = Topic.objects.create(title='Konu', author=self.alice)

    def comment(self, body='Yorum', author=None, target=None, **kw):
        return Comment.objects.create(target=target or self.topic, author=author or self.alice, body=body, **kw)


class AddTests(CommentTestCase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.bob)

    def test_reply_to_reply_attaches_to_top_level(self):
        top = self.comment()
        reply = self.comment(parent=top)
        self.client.post(add_url(self.topic), {'body': 'Yanıta yanıt', 'parent': reply.pk})
        self.assertEqual(Comment.objects.get(body='Yanıta yanıt').parent, top)
        other = self.comment(target=Topic.objects.create(title='Başka'))
        self.client.post(add_url(self.topic), {'body': 'Yanlış hedef', 'parent': other.pk})
        self.assertIsNone(Comment.objects.get(body='Yanlış hedef').parent)
        self.client.post(add_url(self.topic), {'body': 'Bozuk', 'parent': 'abc'})
        self.assertIsNone(Comment.objects.get(body='Bozuk').parent)

    def test_closed_or_hidden_target_403_and_non_commentable_404(self):
        child = Topic.objects.create(title='Alt', parent=self.topic)
        Topic.objects.filter(pk=self.topic.pk).update(is_closed=True)
        self.assertEqual(self.client.post(add_url(child), {'body': 'x'}).status_code, 403)
        Topic.objects.filter(pk=self.topic.pk).update(is_closed=False, is_deleted=True)
        self.assertEqual(self.client.post(add_url(child), {'body': 'x'}).status_code, 403)
        self.assertEqual(self.client.post(add_url(self.alice), {'body': 'x'}).status_code, 404)
        self.assertEqual(self.client.post(f'{add_url(self.topic)[:-2]}999/', {'body': 'x'}).status_code, 404)
        self.assertFalse(Comment.objects.exists())

    def test_request_open_in_discussion_and_expired_proposal_closed(self):
        r = RequestProposal.objects.create(proposer=self.alice, topic=self.topic, title='İstek', content='.')
        self.assertTrue(r.in_discussion and r.is_open and not r.accepts_votes())
        self.assertEqual(self.client.post(add_url(r), {'body': 'Tartışma'}).status_code, 302)
        p = TopicCloseProposal.objects.create(proposer=self.alice, topic=self.topic)
        TopicCloseProposal.objects.filter(pk=p.pk).update(voting_ends_at=timezone.now())
        self.assertEqual(self.client.post(add_url(p), {'body': 'Geç'}).status_code, 403)

    def test_empty_and_too_long_rejected(self):
        for body in ('   ', 'x' * 5001):
            r = self.client.post(add_url(self.topic), {'body': body}, follow=True)
            self.assertContains(r, 'Yorum boş ya da çok uzun.')
        self.client.post(add_url(self.topic), {'body': 'x' * 5000})
        self.assertEqual(Comment.objects.count(), 1)


class EditDeleteTests(CommentTestCase):
    def test_only_author_edits_and_deletes(self):
        c = self.comment('İlk')
        self.client.force_login(self.bob)
        self.assertEqual(self.client.post(f'/comments/{c.pk}/edit/', {'body': 'X'}).status_code, 404)
        self.assertEqual(self.client.post(f'/comments/{c.pk}/delete/').status_code, 404)
        self.client.force_login(self.alice)
        self.client.post(f'/comments/{c.pk}/edit/', {'body': 'Yeni'})
        c.refresh_from_db()
        self.assertEqual(c.body, 'Yeni')
        self.assertIsNotNone(c.edited_at)

    def test_closed_target_freezes_edit_but_allows_delete(self):
        c = self.comment('Gizlenecek metin')
        reply = self.comment('Yanıt', author=self.bob, parent=c)
        Topic.objects.filter(pk=self.topic.pk).update(is_closed=True)
        self.client.force_login(self.alice)
        self.assertEqual(self.client.post(f'/comments/{c.pk}/edit/', {'body': 'X'}).status_code, 403)
        self.client.post(f'/comments/{c.pk}/delete/')
        c.refresh_from_db()
        self.assertTrue(c.is_deleted)
        self.assertEqual(c.body, 'Gizlenecek metin')  # veritabanında kalır
        r = self.client.get(self.topic.get_absolute_url())
        self.assertNotContains(r, 'Gizlenecek metin')
        self.assertContains(r, 'Bu yorum silindi.')
        self.assertContains(r, f'id="c{reply.pk}"')  # yanıt yerinde durur
        self.assertContains(r, 'Yorumlar kapalı.')


class SectionTests(CommentTestCase):
    def test_order_by_score_then_age_and_newest(self):
        old, new, best = self.comment('Y-eski'), self.comment('Y-yeni'), self.comment('Y-iyi')
        Comment.objects.filter(pk=best.pk).update(score=3)

        def order(url):
            body = self.client.get(url).content.decode()
            return sorted(['Y-eski', 'Y-yeni', 'Y-iyi'], key=body.index)

        self.assertEqual(order(self.topic.get_absolute_url()), ['Y-iyi', 'Y-eski', 'Y-yeni'])  # eşit puanda eski önde
        self.assertEqual(order(f'{self.topic.get_absolute_url()}?sort=new'), ['Y-iyi', 'Y-yeni', 'Y-eski'])

    def test_body_is_plain_text_with_links(self):
        self.comment('<b>kalın</b> https://example.com')
        r = self.client.get(self.topic.get_absolute_url())
        self.assertContains(r, '&lt;b&gt;kalın&lt;/b&gt;')
        self.assertContains(r, 'rel="nofollow"')


class VoteTests(CommentTestCase):
    def test_up_down_and_undo(self):
        c = self.comment()
        for value, score in ((1, 1), (-1, -1), (-1, 0)):
            CommentVote.cast(c, self.bob, value)
            c.refresh_from_db()
            self.assertEqual(c.score, score)
        self.assertFalse(CommentVote.objects.exists())  # ikinci ▼ oyu geri aldı

    def test_forbidden_votes(self):
        c = self.comment()
        cases = [(c, self.alice), (c, make_user('yeni', days=1))]  # kendi yorumu, 7 günlük olmayan hesap
        deleted = self.comment(is_deleted=True)
        cases.append((deleted, self.bob))
        for comment, voter in cases:
            with self.subTest(voter=voter.username), self.assertRaisesMessage(ValueError, 'oy verilemez'):
                CommentVote.cast(comment, voter, 1)
        Topic.objects.filter(pk=self.topic.pk).update(is_closed=True)
        with self.assertRaisesMessage(ValueError, 'oy verilemez'):
            CommentVote.cast(c, self.bob, 1)  # kapalı hedefte donar
        c.refresh_from_db()
        self.assertEqual(c.score, 0)

    def test_view_redirects_to_anchor_and_highlights(self):
        c = self.comment()
        self.client.force_login(self.bob)
        r = self.client.post(f'/comments/{c.pk}/vote/', {'value': '1'})
        self.assertRedirects(r, f'{self.topic.get_absolute_url()}#c{c.pk}')
        self.assertContains(self.client.get(self.topic.get_absolute_url()), 'class="on"')
        r = self.client.post(f'/comments/{c.pk}/vote/', {'value': '5'}, follow=True)
        self.assertContains(r, 'Geçersiz oy.')

    def test_section_in_four_queries(self):
        for i in range(5):
            top = self.comment(f'ana {i}')
            for j in range(3):
                self.comment(f'yanıt {i}.{j}', author=self.bob, parent=top)
        request = RequestFactory().get('/')
        request.user = self.bob
        template = Template('{% load comments %}{% comment_section target %}')
        with self.assertNumQueries(4):  # sayımlar, sayfa, yanıtlar, kullanıcının oyları
            html = template.render(Context({'request': request, 'target': self.topic}))
        self.assertEqual(html.count('class="comment"'), 5)
        self.assertEqual(html.count('class="comment reply"'), 15)


class ActiveMemberTests(CommentTestCase):
    def test_commenter_counts_comment_voter_does_not(self):
        self.assertEqual(active_member_count(), 1)  # konuyu açan alice
        c = self.comment(author=self.bob)
        CommentVote.cast(c, make_user('carol'), 1)
        self.assertEqual(active_member_count(), 2)  # bob sayıldı, carol sayılmadı


class AdminTests(CommentTestCase):
    def test_read_only_admin(self):
        admin = make_user('yonetici')
        admin.is_staff = admin.is_superuser = True
        admin.save()
        self.client.force_login(admin)
        c = self.comment('Aranan metin')
        r = self.client.get('/admin/comments/comment/?q=Aranan')
        self.assertContains(r, 'Aranan metin')
        self.assertContains(r, 'Konu')  # hedef sütunu
        r = self.client.get(f'/admin/comments/comment/{c.pk}/change/')
        self.assertEqual(r.status_code, 200)
        self.assertNotContains(r, 'name="_save"')  # kaydet düğmesi yok
        self.assertEqual(self.client.get('/admin/comments/comment/add/').status_code, 403)
