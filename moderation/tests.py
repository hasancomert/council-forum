from datetime import timedelta

from django.conf import settings
from django.contrib import admin
from django.contrib.contenttypes.models import ContentType
from django.core.cache import cache
from django.db.models import ProtectedError
from django.test import TestCase, override_settings
from django.utils import timezone

from accounts.models import User
from comments.models import Comment, CommentVote
from topics.models import Topic, TopicVote
from voting.models import (
    BaseProposal, TopicCloseProposal, TopicOpenProposal, Vote, active_proposals, open_proposal_count,
)
from voting.tests import make_user

from .models import ModAction, Report

S = BaseProposal.Status
NOTE = {'reason': 'troll', 'note': 'Kurala aykırı.'}


def mod_url(obj, prefix='mod'):
    return f'/{prefix}/{ContentType.objects.get_for_model(obj).pk}/{obj.pk}/'


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


class ActionTests(ModTestCase):
    def test_only_moderators(self):
        c = Comment.objects.create(target=self.topic, author=self.alice, body='x')
        url = mod_url(c)
        self.assertRedirects(self.client.get(url), f'/accounts/login/?next={url}')
        self.login(self.bob)
        self.assertEqual(self.client.get(url).status_code, 403)
        self.assertEqual(self.client.get(f'/mod/user/{self.alice.pk}/').status_code, 403)
        self.login(self.mod)
        self.assertEqual(self.client.get(mod_url(self.alice)).status_code, 404)  # yalnızca gizlenebilir içerik

    def test_hide_needs_reason_and_note_and_is_logged(self):
        c = Comment.objects.create(target=self.topic, author=self.alice, body='x')
        self.login(self.mod)
        for bad in ({'note': ''}, {'reason': 'other'}):  # not zorunlu, "diğer" gerekçe yok
            self.assertEqual(self.client.post(mod_url(c), NOTE | bad).status_code, 200)
        self.assertFalse(ModAction.objects.exists())
        self.client.post(mod_url(c), NOTE)
        c.refresh_from_db()
        a = ModAction.objects.get()
        self.assertTrue(c.is_hidden)
        self.assertEqual((a.kind, a.reason, a.moderator, a.user, a.target), ('hide', 'troll', self.mod, self.alice, c))
        self.client.post(mod_url(c), {'reason': 'troll', 'note': 'Yanlış gizleme.'})  # geri alma da kayda düşer
        c.refresh_from_db()
        self.assertFalse(c.is_hidden)
        self.assertEqual(list(ModAction.objects.order_by('pk').values_list('kind', flat=True)), ['hide', 'unhide'])

    def test_cannot_act_on_self_moderators_or_superusers(self):
        root = make_user('kurucu')
        User.objects.filter(pk=root.pk).update(is_superuser=True)
        self.login(self.mod)
        for owner in (self.mod, make_moderator('yonetici2'), root):
            with self.subTest(owner.username):
                c = Comment.objects.create(target=self.topic, author=owner, body='x')
                self.assertEqual(self.client.post(mod_url(c), NOTE).status_code, 403)
                data = NOTE | {'kind': 'ban', 'days': 1}
                self.assertEqual(self.client.post(f'/mod/user/{owner.pk}/', data).status_code, 403)
        self.assertFalse(ModAction.objects.exists())

    def test_hiding_clears_panel_cache(self):
        p = TopicOpenProposal.objects.create(proposer=self.bob, title='Panel önerisi')
        self.assertContains(self.client.get('/'), 'Panel önerisi')  # panel önbelleğe girdi
        self.login(self.mod)
        self.client.post(mod_url(p), NOTE)
        p.refresh_from_db()
        self.assertEqual(p.status, S.CANCELLED)
        self.assertNotContains(self.client.get('/'), 'Panel önerisi')

    def test_ban_and_unban(self):
        url = f'/mod/user/{self.bob.pk}/'
        self.login(self.mod)
        self.assertContains(self.client.post(url, NOTE | {'kind': 'ban'}), 'Engel süresini seç.')
        self.client.post(url, NOTE | {'kind': 'ban', 'days': 7})
        self.bob.refresh_from_db()
        self.assertTrue(self.bob.is_banned)
        self.assertAlmostEqual(self.bob.banned_until, timezone.now() + timedelta(days=7), delta=timedelta(minutes=1))
        self.assertEqual(ModAction.objects.get().until, self.bob.banned_until)
        self.client.post(url, NOTE | {'kind': 'unban'})
        self.bob.refresh_from_db()
        self.assertFalse(self.bob.is_banned)

    def test_close_fake_account(self):
        fake = make_user('sahte')
        running = TopicCloseProposal.objects.create(proposer=self.alice, topic=self.topic)
        finished = TopicOpenProposal.objects.create(proposer=self.alice, title='Bitti')
        own = TopicOpenProposal.objects.create(proposer=fake, title='Sahtenin önerisi')
        for p in (running, finished):
            Vote.cast(proposal=p, voter=fake, choice='yes')
        TopicOpenProposal.objects.filter(pk=finished.pk).update(voting_ends_at=timezone.now())  # oylama bitti
        c = Comment.objects.create(target=self.topic, author=self.alice, body='x')
        CommentVote.cast(c, fake, 1)
        TopicVote.cast(self.topic, fake, -1)
        url = f'/mod/user/{fake.pk}/'
        self.login(self.mod)
        self.assertContains(self.client.post(url, NOTE | {'kind': 'close'}), 'yalnızca')  # yalnızca sahte hesap
        self.client.post(url, {'kind': 'close', 'reason': 'fake', 'note': 'Çoklu hesap.'})
        for obj in (fake, c, self.topic, own):
            obj.refresh_from_db()
        self.assertFalse(fake.is_active)
        self.assertEqual((c.score, self.topic.score), (0, 0))  # ▲/▼ oyları silindi, puanlar düzeldi
        self.assertFalse(CommentVote.objects.exists() or TopicVote.objects.exists())
        self.assertFalse(running.votes.filter(voter=fake).exists())  # süren oylamadaki oy silindi
        self.assertTrue(finished.votes.filter(voter=fake).exists())  # bitmiş oylamaya dokunulmaz
        self.assertEqual(own.status, S.CANCELLED)
        self.client.post(url, {'kind': 'reopen', 'reason': 'fake', 'note': 'Yanlış tespit.'})
        fake.refresh_from_db()
        self.assertTrue(fake.is_active)

    def test_log_lists_moderators(self):
        User.objects.filter(pk=self.bob.pk).update(is_active=False, is_moderator=True)  # kapalı hesap listelenmez
        r = self.client.get('/mod/log/')
        self.assertEqual(list(r.context['moderators']), [self.mod])
        self.assertContains(r, f'?user={self.mod.username}">{self.mod.username}</a>')

    def test_log_is_append_only_public_and_filterable(self):
        c = Comment.objects.create(target=self.topic, author=self.alice, body='Çok gizli söz')
        self.login(self.mod)
        self.client.post(mod_url(c), NOTE | {'note': 'Hakaret içeriyor.'})
        a = ModAction.objects.get()
        a.note = 'değişti'
        with self.assertRaisesMessage(ValueError, 'değiştirilemez'):
            a.save()
        with self.assertRaisesMessage(ValueError, 'silinemez'):
            a.delete()
        with self.assertRaises(ProtectedError):
            self.alice.delete()  # kayıttaki üye de silinemez
        self.login(None)
        r = self.client.get('/mod/log/?kind=hide&user=ALICE')
        for text in ('Hakaret içeriyor.', 'alice', 'yonetici', 'trollük'):
            self.assertContains(r, text)
        self.assertNotContains(r, 'Çok gizli söz')  # gizli metin kayıtta yok
        self.assertNotContains(self.client.get('/mod/log/?kind=ban'), 'Hakaret içeriyor.')
        r = self.client.get(f'/r/{ContentType.objects.get_for_model(c).pk}/{c.pk}/')  # kayıttaki bağlantı
        self.assertTrue(r['Location'].endswith(c.get_absolute_url()))


class ReportTests(ModTestCase):
    def report(self, obj, user):
        self.login(user)
        return self.client.post(mod_url(obj, 'report'), follow=True)

    def test_who_can_report_and_only_once(self):
        c = Comment.objects.create(target=self.topic, author=self.alice, body='x')
        self.assertEqual(self.report(c, make_user('yeni', days=1)).status_code, 403)  # oy hakkı gerekir
        self.assertEqual(self.report(c, self.alice).status_code, 403)  # kendi içeriği
        self.assertContains(self.report(c, self.bob), 'yöneticilere iletildi')
        self.assertContains(self.report(c, self.bob), 'zaten şikayet ettin')  # içerik başına bir şikayet
        self.assertEqual(Report.objects.count(), 1)
        c.set_hidden(True)
        self.assertEqual(self.report(c, make_user('carol')).status_code, 403)  # gizli içerik şikayet edilmez
        self.assertFalse(admin.site.is_registered(Report))

    @override_settings(FORUM={**settings.FORUM, 'REPORT_RATE': (2, 60)})
    def test_report_rate_limit(self):
        comments = [Comment.objects.create(target=self.topic, author=self.alice, body=str(i)) for i in range(3)]
        for c in comments:
            r = self.report(c, self.bob)
        self.assertContains(r, 'Çok sık şikayet')
        self.assertEqual(Report.objects.count(), 2)

    def test_queue_most_reported_first_reporters_hidden(self):
        once = Comment.objects.create(target=self.topic, author=self.alice, body='Bir kez')
        twice = Comment.objects.create(target=self.topic, author=self.alice, body='İki kez')
        reporters = [make_user('ihbarci1'), make_user('ihbarci2')]
        self.report(once, reporters[0])
        for user in reporters:
            self.report(twice, user)
        self.login(self.bob)
        self.assertEqual(self.client.get('/mod/').status_code, 403)
        self.login(self.mod)
        r = self.client.get('/mod/')
        html = r.content.decode()
        self.assertLess(html.index('İki kez'), html.index('Bir kez'))
        self.assertContains(r, '2 şikayet')
        self.assertNotContains(r, 'ihbarci')  # şikayet edenin kimliği gizli
        self.assertNotContains(self.client.get(mod_url(twice)), 'ihbarci')

    def test_hiding_closes_reports_dismiss_does_not_hide(self):
        a = Comment.objects.create(target=self.topic, author=self.alice, body='Gizlenecek')
        b = Comment.objects.create(target=self.topic, author=self.alice, body='Yersiz şikayet')
        for c in (a, b):
            self.report(c, self.bob)
        self.login(self.mod)
        self.client.post(mod_url(a), NOTE)
        self.client.post(mod_url(b), {'dismiss': '1'})
        b.refresh_from_db()
        self.assertFalse(Report.objects.filter(is_open=True).exists())
        self.assertFalse(b.is_hidden)
        self.assertEqual(ModAction.objects.count(), 1)  # şikayet kapatmak kayda düşmez
        self.assertContains(self.client.get('/mod/'), 'Açık şikayet yok.')


class AdminTests(ModTestCase):
    def test_founding_and_moderation_fields_read_only(self):
        root = make_user('kurucu')
        User.objects.filter(pk=root.pk).update(is_staff=True, is_superuser=True)
        self.login(root)
        user_page = f'/admin/accounts/user/{self.bob.pk}/change/'
        r = self.client.get(user_page)
        for field in ('is_active', 'banned_until'):  # yalnızca moderasyonla (kayda düşsün)
            self.assertNotContains(r, f'name="{field}')
        self.assertContains(r, 'name="role"')  # kuruluşta açık
        p = TopicCloseProposal.objects.create(proposer=self.bob, topic=self.topic)
        for url in (f'/admin/topics/topic/{self.topic.pk}/', f'/admin/voting/topiccloseproposal/{p.pk}/'):
            self.assertNotContains(self.client.get(f'{url}change/'), 'name="is_hidden"')
        self.assertEqual(self.client.get('/admin/topics/topic/add/').status_code, 200)
        with override_settings(FORUM={**settings.FORUM, 'FOUNDING': False}):  # kural 9: kuruluş bitti
            self.assertEqual(self.client.get('/admin/topics/topic/add/').status_code, 403)
            r = self.client.get(user_page)
            for field in ('role', 'is_moderator'):  # B statüsü oylamayla; yönetici ataması kuruluşla kapanır
                self.assertNotContains(r, f'name="{field}"')
