"""Mobil uygulamanın JSON API'si (/api/). Kurallar burada yeniden yazılmaz: sitenin görünüm yardımcıları (listing,
page_data, section, create, new_form, file_report) ve model metotları (Vote.cast, UpDownVote.cast, clean()) çağrılır.
Bu dosyada yalnızca kimlik (jeton) ve JSON biçimi var; gizli içerik ve oy gizliliği sitedekiyle aynı.
"""
import json
from datetime import timedelta
from functools import wraps
from operator import attrgetter

from django.conf import settings
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.models import AnonymousUser, update_last_login
from django.contrib.contenttypes.models import ContentType
from django.core import signing
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import DateTimeField
from django.forms import Textarea
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.crypto import constant_time_compare
from django.utils.formats import date_format
from django.views.decorators.csrf import csrf_exempt

from accounts.models import User
from comments.models import Comment, Commentable, CommentVote, vote_block
from comments.views import create, section
from config.templatetags import ago, capfirst, left
from config.utils import get_target
from moderation.models import Hideable
from moderation.views import file_report
from topics.models import Topic, TopicVote
from topics.views import listing, page_data as topic_data
from voting.models import BaseProposal, Vote, active_proposals, mark_voted, open_proposal_count, required_quorum
from voting.views import model_for, new_form, page_data as proposal_data

SALT = 'api.token'


def make_token(user):
    """İmzalı jeton: [kullanıcı pk, şifre özeti]. Veritabanında tutulmaz; imza SECRET_KEY'le, kimse içeriğinden
    üretemez. Oturum gibi şifre özetine bağlı: şifre değişince ya da hesap silinince bütün jetonlar geçersiz.
    """
    return signing.dumps([user.pk, user.get_session_auth_hash()], salt=SALT)


def token_user(request):
    """'Authorization: Bearer <jeton>' başlığının kullanıcısı. Başlık yoksa AnonymousUser, jeton geçersiz, süresi
    dolmuş (API_TOKEN_DAYS) ya da hesap kapalıysa None.
    """
    kind, _, token = request.headers.get('Authorization', '').partition(' ')
    if kind != 'Bearer':
        return AnonymousUser()
    try:
        pk, auth_hash = signing.loads(token, salt=SALT, max_age=timedelta(days=settings.FORUM['API_TOKEN_DAYS']))
        user = User.objects.get(pk=pk, is_active=True)
    except (signing.BadSignature, ValueError, TypeError, User.DoesNotExist):
        return None
    return user if constant_time_compare(auth_hash, user.get_session_auth_hash()) else None


def reply(data, status=200):
    # CORS açık: kimlik çerezde değil başlıkta, başka bir site kullanıcının jetonunu bilemez (Expo web önizlemesi için).
    return JsonResponse(data, status=status, json_dumps_params={'ensure_ascii': False},
                        headers={'Access-Control-Allow-Origin': '*',
                                 'Access-Control-Allow-Headers': 'Authorization, Content-Type'})


def api(*methods, login=('POST',)):
    """API görünümü: yöntem denetimi, jetonla kimlik, JSON gövde (request.data), JSON yanıt. Görünüm sözlük ya da
    (sözlük, durum kodu) döndürür; kural ihlali (ValueError, ValidationError) 400, yetki 403, bulunamadı 404 olur.
    login: giriş isteyen yöntemler. Oturum çerezi okunmaz (request.user yalnızca jetondan): tarayıcı başka bir
    siteden gelen isteğe jetonu kendiliğinden eklemez, CSRF saldırısının taşıyacağı kimlik yok (csrf_exempt).
    """
    def decorator(view):
        @csrf_exempt
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            if request.method == 'OPTIONS':  # CORS ön denetimi
                return reply({})
            if request.method not in methods:
                return reply({'error': 'Bu yöntem desteklenmiyor.'}, 405)
            user = request.user = token_user(request)
            if user is None:
                return reply({'error': 'Oturumun sona erdi, yeniden giriş yap.'}, 401)
            if request.method in login and not user.is_authenticated:
                return reply({'error': 'Bunun için giriş yap.'}, 401)
            try:
                request.data = json.loads(request.body or '{}') if request.method == 'POST' else {}
            except ValueError:
                request.data = None
            if not isinstance(request.data, dict):
                return reply({'error': 'Gövde bir JSON nesnesi olmalı.'}, 400)
            try:
                result = view(request, *args, **kwargs)
            except Http404:
                return reply({'error': 'Bulunamadı.'}, 404)
            except PermissionDenied:
                return reply({'error': 'Bunu yapamazsın.'}, 403)
            except ValidationError as e:
                return reply({'error': ' '.join(e.messages)}, 400)
            except ValueError as e:  # model kuralları: Vote.cast, UpDownVote.cast, create, file_report
                return reply({'error': str(e)}, 400)
            return reply(*result) if isinstance(result, tuple) else reply(result)
        return wrapped
    return decorator


# Biçim yardımcıları: süreler sitedeki ago/left süzgeçleriyle, tarihler sitedeki "j F Y H:i" biçiminde.

def when(dt, fmt='j F Y H:i'):
    return dt and date_format(timezone.localtime(dt), fmt)


def name(user):
    return str(user) if user else 'silinmiş üye'  # User.__str__ silinen hesabı zaten maskeler


def ct_of(obj):
    return ContentType.objects.get_for_model(obj).pk


def pages(page):
    return {'page': page.number, 'pages': page.paginator.num_pages}


def ref(topic, label='Konu'):
    """Başka bir konuya bağlantı. Gizli konunun adı maskeli (Topic.__str__), silinmişin sayfası yok."""
    return topic and {'pk': topic.pk, 'title': str(topic), 'has_page': topic.has_page, 'label': label}


def errors(form):
    return {k: [e['message'] for e in v] for k, v in form.errors.get_json_data().items()}


# topics/_pending.html: (with_pending() alanı, öneri tipi, rozet)
PENDING = (('closing', 'close', 'Kapatma oylamasında'), ('deleting', 'delete', 'Silme oylamasında'),
           ('parent_closing', 'close', 'Üst konu kapatma oylamasında'),
           ('parent_deleting', 'delete', 'Üst konu silme oylamasında'))
# konu sayfasındaki öneri bağlantıları (topics/detail.html)
ACTIONS = {'open': 'Alt konu öner', 'request': 'İstek aç', 'edit': 'Düzenleme öner', 'close': 'Kapatma öner',
           'delete': 'Silme öner', 'undo': 'Yeniden açmayı öner'}


def pending(t):
    """Süren kapatma/silme önerisi rozetleri: with_pending()'ten geçmiş konu."""
    return [{'label': label, 'slug': slug, 'pk': getattr(t, a)} for a, slug, label in PENDING if getattr(t, a, None)]


def row(t):
    """Konu satırı (topics/_row.html): listing() ya da page_data()'dan gelen konu."""
    return {'pk': t.pk, 'title': t.title, 'parent': ref(t.parent, 'Üst konu'), 'score': t.score,
            'comments': t.n_comments, 'subs': getattr(t, 'n_sub', 0), 'created': ago(t.created_at),
            'locked': t.is_locked, 'closed': t.is_closed, 'pending': pending(t)}


def me_data(user):
    days = settings.FORUM['MIN_ACCOUNT_AGE_DAYS']
    return {'username': user.username, 'role': user.role, 'role_label': user.get_role_display(),
            'weight': user.vote_weight, 'can_post': user.can_post, 'can_vote': user.can_vote,
            'why': vote_block(user), 'banned_until': when(user.banned_until) if user.is_banned else None,
            'joined': when(user.date_joined, 'j F Y'), 'vote_from': when(user.date_joined + timedelta(days=days)),
            'moderator': user.is_moderator, 'open_proposals': open_proposal_count(user),
            'max_open_proposals': settings.FORUM['MAX_OPEN_PROPOSALS']}


@api('POST', login=())
def login(request):
    """Takma ad + şifre → jeton. Sitenin giriş formu: aynı denetimler ve hata mesajları (doğrulanmamış hesap vb.)."""
    form = AuthenticationForm(request, data=request.data)
    if not form.is_valid():
        return {'error': ' '.join(sum(errors(form).values(), []))}, 400
    user = form.get_user()
    update_last_login(None, user)
    return {'token': make_token(user), 'me': me_data(user)}


@api('GET', login=('GET',))
def me(request):
    return me_data(request.user)


@api('GET')
def topics(request):
    """Ana sayfa: ?tab=main|sub|closed, ?sort=popular|votes|new, ?page=, ?parent=<pk>."""
    d = listing(request.GET)
    return {'tab': d['tab'], 'sort': d['sort'], 'tabs': [*d['tabs'].items()], 'sorts': [*d['sorts'].items()],
            'parent': ref(d['parent'], 'Üst konu'), 'results': [row(t) for t in d['page']], **pages(d['page'])}


@api('GET')
def topic(request, pk):
    d, user = topic_data(pk, request.user), request.user
    t, masked = d['topic'], d['masked']
    actions = []
    if user.is_authenticated and t.is_open:
        actions = [*([] if t.parent_id else ['open']), 'request', 'edit', 'close', 'delete']
    elif user.is_authenticated and t.is_closed and not t.is_hidden:
        actions = ['undo']
    return {
        'pk': t.pk, 'ct': ct_of(t), 'title': d['title'], 'description': '' if masked else t.description,
        'masked': masked, 'hidden': t.is_hidden and not masked, 'author': name(t.author), 'created': when(t.created_at),
        'score': t.score, 'mine': d['my_vote'], 'why': d['vote_why'], 'locked': t.is_locked, 'open': t.is_open,
        'parent': ref(t.parent, 'Üst konu'), 'pending': pending(t), 'can_report': t.can_be_reported_by(user),
        'actions': [[a, ACTIONS[a]] for a in actions],
        'subs': [row(s) for s in d.get('subs', ())], 'n_subs': d.get('n_subs'),
    }


def updown(model, target, request):
    mine = model.cast(target, request.user, request.data.get('value'))  # 1, -1; aynısı ikinci kez: geri alır
    target.refresh_from_db(fields=['score'])  # cast() puanı veritabanında F() ile değiştirdi
    return {'score': target.score, 'mine': mine}


@api('POST')
def topic_vote(request, pk):
    return updown(TopicVote, get_object_or_404(Topic, pk=pk), request)


def comment(c, user):
    """Yorum (comments/comment.html): silinen ve başkasına gizli yorumun metni ve yazarı gönderilmez."""
    d = {'pk': c.pk, 'deleted': c.is_deleted, 'masked': c.masked,
         'replies': [comment(r, user) for r in getattr(c, 'children', ())]}
    if not (c.is_deleted or c.masked):
        d |= {'author': name(c.author), 'body': c.body, 'created': ago(c.created_at), 'edited': bool(c.edited_at),
              'hidden': c.is_hidden, 'score': c.score, 'mine': c.my_vote, 'why': c.why, 'frozen': c.frozen,
              'own': user.is_authenticated and c.author_id == user.pk, 'can_report': c.can_be_reported_by(user)}
    return d


@api('GET', 'POST')
def comments(request, ct, pk):
    """GET: yorumların bir sayfası (?sort=new, ?page=). POST {body, parent?}: yorum ya da yanıt yaz."""
    target, user = get_target(ct, pk, Commentable), request.user
    if not getattr(target, 'has_page', True):
        raise Http404  # silinmiş konu (sitede de sayfası yok)
    if request.method == 'POST':
        return {'pk': create(user, target, request.data).pk}, 201
    s = section(target, user, request.GET.get('sort'), request.GET.get('page'))
    return {'count': s['count'], 'open': s['open'], 'can_post': user.is_authenticated and user.can_post,
            'sort': 'new' if s['sort'] == 'new' else 'top', 'results': [comment(c, user) for c in s['comments']],
            **pages(s['page'])}


@api('POST')
def comment_delete(request, pk):
    c = get_object_or_404(Comment, pk=pk, author=request.user)
    c.is_deleted = True  # yumuşak silme; hedef kapalı olsa da serbest, geri alınmaz
    c.save(update_fields=['is_deleted'])
    return {'deleted': True}


@api('POST')
def comment_vote(request, pk):
    return updown(CommentVote, get_object_or_404(Comment, pk=pk), request)


@api('GET')
def proposals(request):
    """Açık öneriler (voting/_item.html): evresinin bitişi yakın önce; voted yalnızca oy hakkı olana (yoksa null)."""
    props = sorted(active_proposals(), key=attrgetter('deadline'))
    mark_voted([p for p in props if not p.in_discussion], request.user)
    return {'quorum': required_quorum(), 'results': [
        {'slug': p.SLUG, 'pk': p.pk, 'kind': capfirst(p.kind), 'title': str(p), 'discussion': p.in_discussion,
         'left': left(p.deadline), 'participants': p.participants, 'voted': getattr(p, 'voted', None)}
        for p in props]}


BASE_FIELDS = {f.name for f in BaseProposal._meta.fields} | {'id', 'topic', 'parent'}


def details(p):
    """Önerinin kendi alanları (başlık, açıklama, üye, işlem, gerekçe…) etiketiyle; boşlar ve tarihler hariç."""
    out = []
    for f in p._meta.concrete_fields:
        if f.name not in BASE_FIELDS and not isinstance(f, DateTimeField):
            value = getattr(p, f'get_{f.name}_display')() if f.choices else getattr(p, f.name)
            if value:
                out.append({'label': capfirst(f.verbose_name), 'value': str(value)})
    return out


@api('GET')
def proposal(request, slug, pk):
    """Öneri (voting/detail.html). Kural 6: oylama sürerken yalnızca katılım; sonuç (result) bitince."""
    d, user = proposal_data(slug, pk, request.user), request.user
    p, masked, tally = d['proposal'], d['masked'], d['tally']
    target = p.TARGET and getattr(p, p.TARGET)
    return {
        'slug': p.SLUG, 'pk': p.pk, 'ct': ct_of(p), 'kind': capfirst(p.kind), 'title': d['title'], 'masked': masked,
        'hidden': p.is_hidden and not masked, 'proposer': name(p.proposer), 'created': when(p.created_at),
        'topic': None if masked else ref(target, 'Üst konu' if p.TARGET == 'parent' else 'Konu'),
        'details': [] if masked else details(p),
        'status': p.status, 'status_label': p.get_status_display(),
        'discussion_ends': when(p.discussion_ends_at) if p.in_discussion else None, 'ends': when(p.voting_ends_at),
        'left': left(p.voting_ends_at),
        # katılım çubuğu yalnızca oylamada; sonuç yalnızca bitince (tally False iken None)
        'turnout': {'n': p.participant_count, 'quorum': d['quorum']} if d['quorum'] and not p.in_discussion else None,
        'result': {**tally, 'quorum': p.quorum, 'weighted': p.WEIGHTED, 'applied': when(p.applied_at)} if tally else None,
        'accepts': p.accepts_votes(), 'mine': d['my_vote'].choice if d['my_vote'] else None, 'why': vote_block(user),
        'can_report': p.can_be_reported_by(user),
    }


@api('POST')
def proposal_vote(request, slug, pk):
    """{choice: 'yes'|'no'}; oylama bitene kadar değiştirilebilir (kural 6)."""
    p = get_object_or_404(model_for(slug), pk=pk)
    return {'mine': Vote.cast(proposal=p, voter=request.user, choice=request.data.get('choice')).choice,
            'participants': p.participant_count}


def field(bf):
    """Form alanının tarifi: uygulama tek genel form ekranıyla her öneri tipini çizer."""
    f = bf.field
    choices = [[str(v), str(label)] for v, label in getattr(f, 'choices', ()) if v != '']
    return {'name': bf.name, 'label': str(bf.label), 'help': str(f.help_text), 'required': f.required,
            'type': 'choice' if choices else 'text' if isinstance(f.widget, Textarea) else 'line',
            'choices': choices, 'max_length': getattr(f, 'max_length', None), 'initial': bf.value() or ''}


@api('GET', 'POST', login=('GET', 'POST'))
def proposal_new(request, slug, topic_pk=None):
    """GET: formun alanları. POST {alan: değer}: öneriyi açar ya da alan bazında hataları döner (__all__: genel)."""
    proposal, form = new_form(slug, topic_pk, request.user, request.data if request.method == 'POST' else None)
    if request.method == 'POST':
        if not form.is_valid():
            return {'errors': errors(form)}, 400
        form.save()
        return {'slug': proposal.SLUG, 'pk': proposal.pk}, 201
    target = proposal.TARGET and getattr(proposal, proposal.TARGET)
    return {'title': f'Yeni {proposal._meta.verbose_name}', 'target': target and str(target),
            'fields': [field(bf) for bf in form]}


@api('POST')
def report(request, ct, pk):
    return {'message': file_report(request.user, get_target(ct, pk, Hideable))}
