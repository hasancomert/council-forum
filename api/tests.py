from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from django.utils import timezone

from accounts.models import User
from comments.models import Comment
from topics.models import Topic
from voting.models import BaseProposal, RequestProposal, TopicCloseProposal, Vote
from voting.tests import make_user

from .views import make_token


def ct(obj):
    return ContentType.objects.get_for_model(obj).pk


class ApiTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.alice, cls.bob = make_user('alice'), make_user('bob')
        cls.topic = Topic.objects.create(title='Konu', description='Metin', author=cls.alice)

    def call(self, path, data=None, user=None, **headers):
        """GET (data yoksa) ya da JSON POST; user verilirse jetonuyla."""
        if user:
            headers['HTTP_AUTHORIZATION'] = f'Bearer {make_token(user)}'
        if data is None:
            return self.client.get(f'/api/{path}', **headers)
        return self.client.post(f'/api/{path}', data, content_type='application/json', **headers)


class AuthTests(ApiTestCase):
    def test_login_returns_token_that_authenticates(self):
        User.objects.create_user('ayse', 'ayse@example.com', 'uzun-bir-sifre-9', first_name='A', last_name='S')
        r = self.call('login/', {'username': 'ayse', 'password': 'yanlis'})
        self.assertEqual(r.status_code, 400)
        self.assertIn('takma ad', r.json()['error'])  # sitenin giriş formunun mesajı
        r = self.call('login/', {'username': 'ayse', 'password': 'uzun-bir-sifre-9'})
        self.assertEqual(r.json()['me']['username'], 'ayse')
        me = self.call('me/', HTTP_AUTHORIZATION=f"Bearer {r.json()['token']}")
        self.assertEqual((me.status_code, me.json()['role_label']), (200, 'Üye'))

    def test_unverified_account_cannot_log_in(self):
        User.objects.create_user('yeni', 'yeni@example.com', 'uzun-bir-sifre-9', is_active=False)
        self.assertEqual(self.call('login/', {'username': 'yeni', 'password': 'uzun-bir-sifre-9'}).status_code, 400)

    def test_bad_expired_or_stale_token_is_401(self):
        token = make_token(self.alice)
        self.assertEqual(self.call('me/', HTTP_AUTHORIZATION=f'Bearer {token}x').status_code, 401)
        self.alice.set_password('yeni-sifre-123')  # şifre değişince bütün jetonlar geçersiz
        self.alice.save()
        self.assertEqual(self.call('me/', HTTP_AUTHORIZATION=f'Bearer {token}').status_code, 401)
        with self.settings(FORUM={**settings.FORUM, 'API_TOKEN_DAYS': -1}):  # süresi dolmuş
            self.assertEqual(self.call('me/', user=self.bob).status_code, 401)
        User.objects.filter(pk=self.bob.pk).update(is_active=False)  # kapatılan hesap
        self.assertEqual(self.call('me/', user=self.bob).status_code, 401)

    def test_session_cookie_is_ignored(self):
        """CSRF'siz uç noktalar oturum çereziyle çalışsaydı başka bir site kullanıcı adına oy verdirebilirdi."""
        self.client.force_login(self.bob)
        self.assertEqual(self.call(f'topics/{self.topic.pk}/vote/', {'value': 1}).status_code, 401)
        self.assertEqual(self.call('me/').status_code, 401)

    def test_errors_are_json_and_cors_is_open(self):
        self.assertEqual(self.call('topics/999/').json(), {'error': 'Bulunamadı.'})
        self.assertEqual(self.call('topics/', {}).status_code, 405)
        r = self.client.options('/api/topics/')
        self.assertEqual((r.status_code, r['Access-Control-Allow-Origin']), (200, '*'))
        self.assertIn('Authorization', r['Access-Control-Allow-Headers'])
        r = self.client.post('/api/login/', '[1]', content_type='application/json')
        self.assertEqual(r.status_code, 400)


class TopicTests(ApiTestCase):
    def test_list_tabs_sorts_and_badges(self):
        sub = Topic.objects.create(title='Alt', parent=self.topic)
        Topic.objects.create(title='Gizli', is_hidden=True)
        p = TopicCloseProposal.objects.create(proposer=self.bob, topic=self.topic)
        d = self.call('topics/').json()
        self.assertEqual([t['title'] for t in d['results']], ['Konu'])  # gizli konu listelenmez
        self.assertEqual(d['results'][0]['subs'], 1)
        self.assertEqual(d['results'][0]['pending'], [{'label': 'Kapatma oylamasında', 'slug': 'close', 'pk': p.pk}])
        d = self.call(f'topics/?tab=sub&sort=votes&parent={self.topic.pk}').json()
        self.assertEqual((d['tab'], d['sort'], d['parent']['pk']), ('sub', 'votes', self.topic.pk))
        self.assertEqual(d['results'][0]['pending'][0]['label'], 'Üst konu kapatma oylamasında')
        self.assertEqual([t['pk'] for t in d['results']], [sub.pk])
        self.assertEqual(self.call('topics/?tab=closed').json()['sorts'], [['votes', 'En çok oy'], ['new', 'En yeni']])

    def test_detail_masks_hidden_topic_and_lists_actions(self):
        d = self.call(f'topics/{self.topic.pk}/', user=self.bob).json()
        self.assertEqual([a for a, _ in d['actions']], ['open', 'request', 'edit', 'close', 'delete'])
        self.assertEqual((d['why'], d['can_report']), ('', True))
        self.assertEqual(self.call(f'topics/{self.topic.pk}/').json()['actions'], [])  # giriş yok
        Topic.objects.filter(pk=self.topic.pk).update(is_hidden=True)
        d = self.call(f'topics/{self.topic.pk}/', user=self.bob).json()
        self.assertEqual((d['title'], d['description'], d['masked']), ('Moderasyonla gizlendi', '', True))
        d = self.call(f'topics/{self.topic.pk}/', user=self.alice).json()  # sahibi görür
        self.assertEqual((d['title'], d['hidden']), ('Konu', True))
        Topic.objects.filter(pk=self.topic.pk).update(is_deleted=True)
        self.assertEqual(self.call(f'topics/{self.topic.pk}/').status_code, 404)

    def test_vote_uses_site_rules(self):
        url = f'topics/{self.topic.pk}/vote/'
        self.assertEqual(self.call(url, {'value': 1}, user=self.alice).json(), {'error': 'Buna oy verilemez.'})
        self.assertEqual(self.call(url, {'value': 1}, user=self.bob).json(), {'score': 1, 'mine': 1})
        self.assertEqual(self.call(url, {'value': 1}, user=self.bob).json(), {'score': 0, 'mine': 0})  # geri alır
        self.assertEqual(self.call(url, {'value': 5}, user=self.bob).status_code, 400)
        d = self.call(f'topics/{self.topic.pk}/', user=make_user('yeni', days=1)).json()
        self.assertIn('en az 7 günlük', d['why'])


class CommentTests(ApiTestCase):
    def url(self, target=None):
        target = target or self.topic
        return f'comments/{ct(target)}/{target.pk}/'

    def test_write_reply_list_delete(self):
        r = self.call(self.url(), {'body': 'İlk'}, user=self.bob)
        self.assertEqual(r.status_code, 201)
        top = r.json()['pk']
        reply = self.call(self.url(), {'body': 'Yanıt', 'parent': top}, user=self.alice).json()['pk']
        self.call(self.url(), {'body': 'Yanıta yanıt', 'parent': reply}, user=self.bob)  # ana yoruma bağlanır
        self.assertEqual(self.call(self.url(), {'body': ' '}, user=self.bob).json(), {'error': 'Yorum boş ya da çok uzun.'})
        self.assertEqual(self.call(self.url(), {'body': 'x'}).status_code, 401)
        d = self.call(self.url(), user=self.alice).json()
        self.assertEqual((d['count'], d['can_post'], len(d['results'])), (3, True, 1))
        c = d['results'][0]
        self.assertEqual((c['body'], c['own'], c['can_report']), ('İlk', False, True))
        self.assertEqual([r['body'] for r in c['replies']], ['Yanıt', 'Yanıta yanıt'])
        self.assertEqual(self.call(f'comments/{top}/delete/', {}, user=self.alice).status_code, 404)  # başkasının
        self.assertEqual(self.call(f'comments/{top}/delete/', {}, user=self.bob).json(), {'deleted': True})
        c = self.call(self.url()).json()['results'][0]
        self.assertTrue(c['deleted'])
        self.assertNotIn('body', c)
        self.assertEqual(len(c['replies']), 2)  # yanıtlar kalır

    def test_hidden_comment_body_only_for_author(self):
        c = Comment.objects.create(target=self.topic, author=self.bob, body='gizli metin', is_hidden=True)
        self.assertNotIn('gizli metin', self.call(self.url(), user=self.alice).content.decode())
        self.assertEqual(self.call(self.url(), user=self.bob).json()['results'][0]['body'], 'gizli metin')
        self.assertEqual(self.call(f'comments/{c.pk}/vote/', {'value': 1}, user=self.alice).status_code, 400)

    def test_vote_closed_target_and_deleted_topic(self):
        c = Comment.objects.create(target=self.topic, author=self.bob, body='yorum')
        self.assertEqual(self.call(f'comments/{c.pk}/vote/', {'value': -1}, user=self.alice).json(),
                         {'score': -1, 'mine': -1})
        Topic.objects.filter(pk=self.topic.pk).update(is_closed=True)
        self.assertEqual(self.call(self.url(), {'body': 'x'}, user=self.bob).status_code, 403)
        d = self.call(self.url(), user=self.bob).json()
        self.assertEqual((d['open'], d['results'][0]['frozen']), (False, True))
        Topic.objects.filter(pk=self.topic.pk).update(is_deleted=True)
        self.assertEqual(self.call(self.url()).status_code, 404)

    def test_report(self):
        c = Comment.objects.create(target=self.topic, author=self.bob, body='yorum')
        url = f'report/{ct(c)}/{c.pk}/'
        self.assertEqual(self.call(url, {}, user=self.alice).json(), {'message': 'Şikayetin yöneticilere iletildi.'})
        self.assertEqual(self.call(url, {}, user=self.alice).json(), {'message': 'Bunu zaten şikayet ettin.'})
        self.assertEqual(self.call(url, {}, user=self.bob).status_code, 403)  # kendi yorumu


class ProposalTests(ApiTestCase):
    def test_list_and_detail_keep_results_secret_until_the_end(self):
        p = TopicCloseProposal.objects.create(proposer=self.alice, topic=self.topic)
        RequestProposal.objects.create(proposer=self.alice, topic=self.topic, title='İstek', content='Metin')
        url = f'proposals/close/{p.pk}/'
        self.assertEqual(self.call(f'{url}vote/', {'choice': 'yes'}, user=self.bob).json(),
                         {'mine': 'yes', 'participants': 1})
        self.assertEqual(self.call(f'{url}vote/', {'choice': 'no'}, user=self.bob).json()['mine'], 'no')  # değişir
        d = self.call('proposals/', user=self.bob).json()
        self.assertEqual([(i['slug'], i['voted'], i['discussion']) for i in d['results']],
                         [('close', True, False), ('request', None, True)])  # tartışmadaki istek oylanmaz
        self.assertEqual(self.call('proposals/', user=self.alice).json()['results'][0]['voted'], False)
        d = self.call(url, user=self.bob).json()
        self.assertEqual((d['result'], d['turnout'], d['mine'], d['accepts']), (None, {'n': 1, 'quorum': 5}, 'no', True))
        self.assertEqual(d['topic'], {'pk': self.topic.pk, 'title': 'Konu', 'has_page': True, 'label': 'Konu'})
        TopicCloseProposal.objects.filter(pk=p.pk).update(voting_ends_at=timezone.now())
        d = self.call(url).json()  # sayfa ziyareti sonuçlandırır
        self.assertEqual((d['status'], d['turnout']), ('rejected', None))
        self.assertEqual(d['result'], {'yes': 0, 'no': 1, 'count': 1, 'quorum': 5, 'weighted': True, 'applied': None})
        self.assertEqual(self.call(f'{url}vote/', {'choice': 'yes'}, user=self.bob).json(),
                         {'error': 'Bu öneri şu anda oylanamıyor.'})

    def test_vote_needs_account_age(self):
        p = TopicCloseProposal.objects.create(proposer=self.alice, topic=self.topic)
        young = make_user('yeni', days=1)
        self.assertIn('en az 7 günlük', self.call(f'proposals/close/{p.pk}/', user=young).json()['why'])
        self.assertEqual(self.call(f'proposals/close/{p.pk}/vote/', {'choice': 'yes'}, user=young).status_code, 400)
        self.assertFalse(Vote.objects.exists())

    def test_new_form_schema_errors_and_create(self):
        self.assertEqual(self.call('proposals/new/expert/').status_code, 401)
        d = self.call('proposals/new/expert/', user=self.bob).json()
        self.assertEqual([(f['name'], f['type'], f['label']) for f in d['fields']],
                         [('action', 'choice', 'İşlem'), ('username', 'line', 'Üye (takma ad)'),
                          ('reason', 'text', 'Gerekçe')])
        url = f'proposals/new/edit/{self.topic.pk}/'
        fields = {f['name']: f for f in self.call(url, user=self.bob).json()['fields']}
        self.assertEqual((fields['new_title']['initial'], fields['new_title']['max_length']), ('Konu', 200))
        r = self.call(url, {'new_title': ''}, user=self.bob)
        self.assertEqual(r.json(), {'errors': {'new_title': ['Bu alan zorunludur.']}})
        r = self.call(url, {'new_title': 'Yeni ad', 'new_description': 'Yeni metin'}, user=self.bob)
        self.assertEqual(r.status_code, 201)
        d = self.call(f"proposals/edit/{r.json()['pk']}/").json()
        self.assertEqual(d['details'], [{'label': 'Yeni başlık', 'value': 'Yeni ad'},
                                        {'label': 'Yeni açıklama', 'value': 'Yeni metin'}])
        r = self.call(url, {'new_title': 'Yeni ad', 'new_description': 'Yeni metin'}, user=self.bob)
        self.assertIn('aynısı oylamada', r.json()['errors']['__all__'][0])  # kural 8, modelin clean()'i
        self.assertEqual(self.call('proposals/new/undo/', user=self.bob).status_code, 404)  # konu gerekli

    def test_hidden_proposal_is_masked(self):
        p = TopicCloseProposal.objects.create(proposer=self.alice, topic=self.topic)
        p.set_hidden(True)
        d = self.call(f'proposals/close/{p.pk}/', user=self.bob).json()
        self.assertEqual((d['title'], d['topic'], d['status'], d['result']),
                         ('Moderasyonla gizlendi', None, BaseProposal.Status.CANCELLED, None))
