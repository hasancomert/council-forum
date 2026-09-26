from datetime import timedelta
from io import StringIO

from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from accounts.models import User
from topics.models import Topic

from .models import (
    BaseProposal, ExpertProposal, RequestProposal, TopicCloseProposal, TopicEditProposal,
    TopicOpenProposal, TopicUndoProposal, Vote, open_proposal_count, required_quorum,
)

S = BaseProposal.Status
YES, NO = Vote.Choice.YES, Vote.Choice.NO


def make_user(name, role='A', days=10):
    # Şifresiz (None): hash'leme testleri yavaşlatır; giriş force_login ile yapılır.
    user = User.objects.create_user(name, f'{name}@example.com', None, first_name='Ad', last_name='Soyad', role=role)
    User.objects.filter(pk=user.pk).update(date_joined=timezone.now() - timedelta(days=days))
    user.refresh_from_db()
    return user


class VotingTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.voters = [make_user(f'v{i}') for i in range(5)]
        cls.expert = make_user('uzman', 'B')
        cls.proposer = make_user('oneren')

    def setUp(self):
        self.topic = Topic.objects.create(title='Konu', author=self.proposer)

    def vote(self, proposal, yes=(), no=()):
        for user in yes:
            Vote.cast(proposal=proposal, voter=user, choice=YES)
        for user in no:
            Vote.cast(proposal=proposal, voter=user, choice=NO)

    def expire(self, proposal):
        type(proposal).objects.filter(pk=proposal.pk).update(voting_ends_at=timezone.now())
        proposal.refresh_from_db()
        proposal.finalize()


class FinalizeTests(VotingTestCase):
    """5. adımın 11 senaryosu ve 6. adımdaki düzeltmeler."""

    def test_weighted_majority_accepts_and_applies(self):
        p = TopicCloseProposal.objects.create(proposer=self.proposer, topic=self.topic)
        self.assertAlmostEqual(p.voting_ends_at - p.created_at, timedelta(days=2), delta=timedelta(seconds=5))
        self.vote(p, yes=[self.expert, *self.voters[:2]], no=self.voters[2:])  # 10+1+1 evet, 3 hayır
        self.assertEqual(p.participant_count, 6)
        self.assertFalse(p.results_visible)
        self.expire(p)
        self.topic.refresh_from_db()
        self.assertEqual(p.status, S.APPLIED)
        self.assertEqual(p.quorum, 5)
        self.assertIsNotNone(p.applied_at)
        self.assertTrue(self.topic.is_closed)
        self.assertEqual(p.tally(), {'yes': 12, 'no': 3, 'count': 6})

    def test_tie_rejects(self):
        p = TopicCloseProposal.objects.create(proposer=self.proposer, topic=self.topic)
        self.vote(p, yes=self.voters[:3], no=[*self.voters[3:], self.proposer])
        self.expire(p)
        self.assertEqual(p.status, S.REJECTED)
        self.topic.refresh_from_db()
        self.assertFalse(self.topic.is_closed)

    def test_quorum_not_met_rejects(self):
        p = TopicCloseProposal.objects.create(proposer=self.proposer, topic=self.topic)
        self.vote(p, yes=self.voters[:4])
        self.expire(p)
        self.assertEqual((p.status, p.quorum), (S.REJECTED, 5))

    def test_open_proposal_count_spans_all_types(self):
        TopicOpenProposal.objects.create(proposer=self.proposer, title='A')
        TopicCloseProposal.objects.create(proposer=self.proposer, topic=self.topic)
        TopicCloseProposal.objects.create(proposer=self.proposer, topic=self.topic, status=S.REJECTED)
        self.assertEqual(open_proposal_count(self.proposer), 2)

    def test_expert_two_thirds_unweighted(self):
        exact, below = make_user('aday1'), make_user('aday2')
        p = ExpertProposal.objects.create(proposer=exact, target_user=exact, action='grant', reason='.')
        q = ExpertProposal.objects.create(proposer=below, target_user=below, action='grant', reason='.')
        self.vote(p, yes=self.voters[:4], no=[self.voters[4], self.expert])  # 4/6 = 2/3
        self.vote(q, yes=self.voters[:3], no=[self.voters[3], self.expert])  # 3/5 < 2/3
        self.assertEqual(p.votes.get(voter=self.expert).weight, 1)
        self.expire(p)
        self.expire(q)
        exact.refresh_from_db()
        below.refresh_from_db()
        self.assertEqual((p.status, exact.role), (S.APPLIED, 'B'))
        self.assertEqual((q.status, below.role), (S.REJECTED, 'A'))

    def test_request_discussion_then_voting(self):
        r = RequestProposal.objects.create(proposer=self.proposer, topic=self.topic, title='İstek', content='.')
        self.assertAlmostEqual(r.voting_ends_at - r.created_at, timedelta(days=6), delta=timedelta(seconds=5))
        self.assertTrue(r.is_open)  # tartışmada yoruma açık
        with self.assertRaises(ValueError):
            Vote.cast(proposal=r, voter=self.voters[0], choice=YES)
        RequestProposal.objects.filter(pk=r.pk).update(discussion_ends_at=timezone.now())
        r.refresh_from_db()
        Vote.cast(proposal=r, voter=self.voters[0], choice=YES)
        self.assertEqual(r.participant_count, 1)

    def test_accepted_but_unapplicable_fails_without_waiting(self):
        p = TopicCloseProposal.objects.create(proposer=self.proposer, topic=self.topic)
        self.vote(p, yes=self.voters)
        Topic.objects.filter(pk=self.topic.pk).update(is_deleted=True)
        self.expire(p)
        self.assertEqual((p.status, p.applied_at), (S.FAILED, None))
        Topic.objects.filter(pk=self.topic.pk).update(is_deleted=False)
        p = TopicCloseProposal.objects.get(pk=p.pk)
        p.finalize()  # sonuçlandı: hedef sonradan uygun olsa da yeniden denenmez
        self.topic.refresh_from_db()
        self.assertEqual(p.status, S.FAILED)
        self.assertFalse(self.topic.is_closed)
        # kural 8: açık öneri sayılmaz, ret yasağına girmez; aynısı yeniden açılabilir
        self.assertEqual(open_proposal_count(self.proposer), 0)
        self.assertFalse(TopicCloseProposal(proposer=self.proposer, topic=self.topic).is_duplicate())

    def test_command_finalizes_expired(self):
        p = TopicCloseProposal.objects.create(proposer=self.proposer, topic=self.topic)
        self.vote(p, yes=self.voters)
        TopicCloseProposal.objects.filter(pk=p.pk).update(voting_ends_at=timezone.now())
        # bu sürümden önce 'kabul' durumunda bekletilmiş öneri: komut sonuçlandırır
        parent = Topic.objects.create(title='Silinen', is_deleted=True)
        old = TopicOpenProposal.objects.create(proposer=self.proposer, parent=parent, title='Eski')
        TopicOpenProposal.objects.filter(pk=old.pk).update(status=S.ACCEPTED)
        call_command('finalize_proposals', stdout=StringIO())
        p.refresh_from_db()
        old.refresh_from_db()
        self.assertEqual((p.status, old.status), (S.APPLIED, S.FAILED))

    def test_undo_reopen(self):
        Topic.objects.filter(pk=self.topic.pk).update(is_closed=True)
        p = TopicUndoProposal.objects.create(proposer=self.proposer, topic=self.topic, action='reopen')
        self.vote(p, yes=self.voters)
        self.expire(p)
        self.topic.refresh_from_db()
        self.assertEqual(p.status, S.APPLIED)
        self.assertFalse(self.topic.is_closed)

    def test_open_under_closed_parent_fails(self):
        p = TopicOpenProposal.objects.create(proposer=self.proposer, parent=self.topic, title='Alt')
        self.vote(p, yes=self.voters)
        Topic.objects.filter(pk=self.topic.pk).update(is_closed=True)
        self.expire(p)
        self.assertEqual(p.status, S.FAILED)
        self.assertContains(self.client.get(p.get_absolute_url()), 'uygulanamadı. Aynı öneri yeniden açılabilir.')
        self.assertFalse(Topic.objects.filter(title='Alt').exists())

    def test_edit_fails_if_topic_closed_during_voting(self):
        p = TopicEditProposal.objects.create(proposer=self.proposer, topic=self.topic, new_title='Yeni')
        self.vote(p, yes=self.voters)
        Topic.objects.filter(pk=self.topic.pk).update(is_closed=True)
        self.expire(p)
        self.topic.refresh_from_db()
        self.assertEqual((p.status, self.topic.title), (S.FAILED, 'Konu'))

    def test_stale_copy_does_not_apply_twice(self):
        p = TopicOpenProposal.objects.create(proposer=self.proposer, title='Tek')
        self.vote(p, yes=self.voters)
        TopicOpenProposal.objects.filter(pk=p.pk).update(voting_ends_at=timezone.now())
        a, b = TopicOpenProposal.objects.get(pk=p.pk), TopicOpenProposal.objects.get(pk=p.pk)
        a.finalize()
        b.finalize()  # b hâlâ 'oylanıyor' sanıyor
        self.assertEqual(b.status, S.APPLIED)
        self.assertEqual(Topic.objects.filter(title='Tek').count(), 1)


class PageTests(VotingTestCase):
    def test_detail_hides_result_until_voting_ends(self):
        p = TopicCloseProposal.objects.create(proposer=self.proposer, topic=self.topic)
        self.vote(p, yes=self.voters[:3], no=self.voters[3:])
        r = self.client.get(p.get_absolute_url())
        self.assertContains(r, '5/5 katılım · yeter sayı tamam')  # kural 3: yeter sayı en az 5
        self.assertNotContains(r, 'Evet 3')
        self.assertNotContains(r, 'class="result"')  # kural 6: oran oylama bitince
        TopicCloseProposal.objects.filter(pk=p.pk).update(voting_ends_at=timezone.now())
        r = self.client.get(p.get_absolute_url())  # sayfa ziyareti sonuçlandırır
        self.assertContains(r, 'Uygulandı')
        self.assertContains(r, 'Evet 3 · Hayır 2 (ağırlıklı) · katılım 5, yeter sayı 5')
        self.assertContains(r, 'class="result" max="5" value="3"')  # 3/5 yeşil, 2/5 kırmızı

    def test_vote_view(self):
        p = TopicCloseProposal.objects.create(proposer=self.proposer, topic=self.topic)
        url = f'{p.get_absolute_url()}vote/'
        self.assertRedirects(self.client.post(url, {'choice': 'yes'}), f'/accounts/login/?next={url}',
                             fetch_redirect_response=False)
        self.client.force_login(self.voters[0])
        self.client.post(url, {'choice': 'yes'})
        self.client.post(url, {'choice': 'no'})  # oy değiştirilebilir
        self.assertEqual(p.votes.get().choice, NO)
        r = self.client.post(url, {'choice': 'belki'}, follow=True)
        self.assertContains(r, 'Geçersiz oy.')

    def test_every_type_renders(self):
        kw = {'proposer': self.proposer}
        for p in (
            TopicOpenProposal.objects.create(**kw, title='Ana'),
            TopicOpenProposal.objects.create(**kw, parent=self.topic, title='Alt'),
            TopicEditProposal.objects.create(**kw, topic=self.topic, new_title='Yeni'),
            TopicCloseProposal.objects.create(**kw, topic=self.topic),
            TopicUndoProposal.objects.create(**kw, topic=self.topic, action='restore'),
            ExpertProposal.objects.create(**kw, target_user=self.proposer, action='grant', reason='Gerekçe'),
            RequestProposal.objects.create(**kw, topic=self.topic, title='İstek', content='İçerik'),
        ):
            with self.subTest(p.SLUG):
                self.assertContains(self.client.get(p.get_absolute_url()), str(p))

    def test_list_and_unknown_type(self):
        p = TopicCloseProposal.objects.create(proposer=self.proposer, topic=self.topic)
        self.assertContains(self.client.get('/proposals/'), str(p))
        self.assertEqual(self.client.get(f'/proposals/yok/{p.pk}/').status_code, 404)


class PanelTests(VotingTestCase):
    def setUp(self):
        super().setUp()
        cache.clear()  # panel önbelleği testler arasında taşınmasın

    def panel(self, url='/'):
        html = self.client.get(url).content.decode()
        return html[html.index('<aside>'):html.index('</aside>')]

    def test_order_phases_and_expiry(self):
        now = timezone.now()
        late = TopicCloseProposal.objects.create(proposer=self.proposer, topic=self.topic)  # 2 gün
        soon = TopicOpenProposal.objects.create(proposer=self.proposer, title='Yakın', voting_ends_at=now + timedelta(hours=1))
        TopicOpenProposal.objects.create(proposer=self.proposer, title='Bitti', voting_ends_at=now - timedelta(minutes=1))
        r = RequestProposal.objects.create(proposer=self.proposer, topic=self.topic, title='İstek', content='.')
        Vote.cast(proposal=late, voter=self.voters[0], choice=YES)
        panel = self.panel()
        self.assertLess(panel.index(str(soon)), panel.index(str(late)))  # bitişi yakın önce
        self.assertLess(panel.index(str(late)), panel.index('Tartışmada'))
        self.assertLess(panel.index('Tartışmada'), panel.index('İstek'))  # tartışmadaki istek yalnızca orada
        self.assertIn(f'1/{required_quorum()} katılım', panel)  # kural 6: sonuç değil, yalnızca katılım
        self.assertNotIn('Evet', panel)
        self.assertNotIn('Bitti', panel)
        RequestProposal.objects.filter(pk=r.pk).update(discussion_ends_at=now)  # oylama evresine geçti
        cache.clear()
        panel = self.panel(self.topic.get_absolute_url())  # konu sayfasında da var
        self.assertNotIn('Tartışmada', panel)
        self.assertIn('İstek', panel)

    def test_overflow_links_to_all(self):
        for i in range(12):
            TopicOpenProposal.objects.create(proposer=self.proposer, title=f'Öneri {i}')
        panel = self.panel()
        self.assertEqual(panel.count('<li>'), 10)
        self.assertIn('Tümü (12)', panel)

    def test_unvoted_marker(self):
        p = TopicCloseProposal.objects.create(proposer=self.proposer, topic=self.topic)
        self.assertNotIn('Oy ver', self.panel())  # giriş yok
        self.client.force_login(make_user('yeni', days=1))
        self.assertNotIn('Oy ver', self.panel())  # oy hakkı yok
        self.client.force_login(self.voters[0])
        self.assertIn('Oy ver', self.panel())
        Vote.cast(proposal=p, voter=self.voters[0], choice=YES)
        self.assertNotIn('Oy ver', self.panel())  # ortak kısım önbellekte, işaret yine de güncel


class FormTests(VotingTestCase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.proposer)

    def test_open_main_topic(self):
        r = self.client.post('/proposals/new/open/', {'title': 'Yeni ana konu', 'description': ''})
        p = TopicOpenProposal.objects.get()
        self.assertRedirects(r, p.get_absolute_url())
        self.assertEqual((p.proposer, p.parent, p.status), (self.proposer, None, S.VOTING))

    def test_edit_prefilled_and_hidden_topic_404(self):
        self.assertContains(self.client.get(f'/proposals/new/edit/{self.topic.pk}/'), 'value="Konu"')
        Topic.objects.filter(pk=self.topic.pk).update(is_deleted=True)
        self.assertEqual(self.client.get(f'/proposals/new/edit/{self.topic.pk}/').status_code, 404)
        self.assertContains(self.client.get(f'/proposals/new/undo/{self.topic.pk}/'), 'value="restore" selected')

    def test_topic_required_where_needed(self):
        self.assertEqual(self.client.get('/proposals/new/close/').status_code, 404)
        self.assertEqual(self.client.get(f'/proposals/new/expert/{self.topic.pk}/').status_code, 404)

    def test_close_has_no_fields(self):
        self.client.post(f'/proposals/new/close/{self.topic.pk}/')
        self.assertTrue(TopicCloseProposal.objects.filter(topic=self.topic, proposer=self.proposer).exists())

    def test_expert_grant_and_revoke(self):
        self.client.post('/proposals/new/expert/', {'action': 'grant', 'reason': 'Deneyim'})
        self.client.post('/proposals/new/expert/', {'action': 'revoke', 'username': 'UZMAN', 'reason': 'Neden'})
        self.assertEqual(
            {(p.action, p.target_user) for p in ExpertProposal.objects.all()},
            {('grant', self.proposer), ('revoke', self.expert)},
        )
        r = self.client.post('/proposals/new/expert/', {'action': 'revoke', 'username': 'yok', 'reason': '.'})
        self.assertContains(r, 'Bu takma adla bir üye yok.')

    def test_fourth_proposal_shows_error(self):
        for i in range(3):
            TopicOpenProposal.objects.create(proposer=self.proposer, title=f'K{i}')
        r = self.client.post('/proposals/new/open/', {'title': 'K3'})
        self.assertContains(r, 'en fazla 3 açık önerin')
        self.assertEqual(TopicOpenProposal.objects.count(), 3)

    def test_archive_hides_deleted_content(self):
        Topic.objects.filter(pk=self.topic.pk).update(is_deleted=True, description='Gizli içerik')
        r = self.client.get('/topics/archive/')
        self.assertContains(r, 'Konu')
        self.assertNotContains(r, 'Gizli içerik')
        self.assertContains(r, f'/proposals/new/undo/{self.topic.pk}/')


class CleanTests(VotingTestCase):
    def assertInvalid(self, proposal, message):
        with self.assertRaisesMessage(ValidationError, message):
            proposal.clean()

    def test_open_proposal_limit(self):
        for i in range(3):
            TopicOpenProposal.objects.create(proposer=self.proposer, title=f'K{i}')
        self.assertInvalid(TopicOpenProposal(proposer=self.proposer, title='K3'), 'en fazla 3')

    def test_new_account_cannot_propose(self):
        self.assertInvalid(TopicOpenProposal(proposer=make_user('yeni', days=1), title='X'), 'en az 7 günlük')

    def test_banned_cannot_propose_or_vote(self):
        p = TopicCloseProposal.objects.create(proposer=self.voters[0], topic=self.topic)
        User.objects.filter(pk=self.proposer.pk).update(banned_until=timezone.now() + timedelta(days=1))
        self.proposer.refresh_from_db()
        self.assertInvalid(TopicOpenProposal(proposer=self.proposer, title='X'), 'Engelin sürerken')
        with self.assertRaisesMessage(ValueError, 'oy hakkı yok'):
            Vote.cast(proposal=p, voter=self.proposer, choice=YES)

    def test_duplicate_of_voting_proposal(self):
        TopicCloseProposal.objects.create(proposer=self.voters[0], topic=self.topic)
        self.assertInvalid(TopicCloseProposal(proposer=self.proposer, topic=self.topic), 'aynısı')

    def test_rejection_cooldown_counts_from_voting_end(self):
        old = TopicCloseProposal.objects.create(proposer=self.voters[0], topic=self.topic, status=S.REJECTED)
        now = timezone.now()
        TopicCloseProposal.objects.filter(pk=old.pk).update(
            created_at=now - timedelta(days=40), voting_ends_at=now - timedelta(days=20))
        self.assertInvalid(TopicCloseProposal(proposer=self.proposer, topic=self.topic), 'aynısı')
        TopicCloseProposal.objects.filter(pk=old.pk).update(voting_ends_at=now - timedelta(days=31))
        TopicCloseProposal(proposer=self.proposer, topic=self.topic).clean()

    def test_closed_topic_takes_undo_but_not_edit(self):
        Topic.objects.filter(pk=self.topic.pk).update(is_closed=True)
        self.topic.refresh_from_db()
        self.assertInvalid(TopicEditProposal(proposer=self.proposer, topic=self.topic, new_title='X'), 'Kapalı')
        TopicUndoProposal(proposer=self.proposer, topic=self.topic, action='reopen').clean()
        self.assertInvalid(TopicUndoProposal(proposer=self.proposer, topic=self.topic, action='restore'), 'geri alınacak')

    def test_subtopic_only_under_open_main_topic(self):
        child = Topic.objects.create(title='Alt', parent=self.topic)
        self.assertInvalid(TopicOpenProposal(proposer=self.proposer, parent=child, title='X'), 'ana konunun')

    def test_expert_rules(self):
        other = self.voters[0]
        grant = ExpertProposal.Action.GRANT
        self.assertInvalid(ExpertProposal(proposer=self.proposer, target_user=other, action=grant), 'kendi adına')
        ExpertProposal(proposer=self.proposer, target_user=self.proposer, action=grant).clean()
        self.assertInvalid(ExpertProposal(proposer=self.proposer, target_user=other, action='revoke'), 'bilirkişi değil')
        ExpertProposal(proposer=self.proposer, target_user=self.expert, action='revoke').clean()
