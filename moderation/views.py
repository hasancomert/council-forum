from datetime import timedelta
from functools import wraps

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from accounts.models import User
from comments.models import CommentVote
from config.utils import get_target
from topics.models import TopicVote
from voting.models import PANEL_CACHE_KEY, withdraw_running

from .forms import ActionForm, UserActionForm
from .models import Hideable, ModAction

Kind = ModAction.Kind
ROW = ('moderator', 'user', 'content_type')  # kayıt satırının (_action.html) ilişkileri: satır başına sorgu yok


def moderator_required(view):
    """Yalnızca yöneticiler (is_moderator): giriş yoksa giriş sayfasına, yönetici değilse 403."""
    @wraps(view)
    @login_required
    def wrapped(request, *args, **kwargs):
        if not request.user.is_moderator:
            raise PermissionDenied
        return view(request, *args, **kwargs)
    return wrapped


def _allowed(moderator, user):
    """Kendine, başka yöneticiye ve süper kullanıcıya işlem yapılamaz (sahibi silinmiş içerik serbest)."""
    return not (user and (user == moderator or user.is_moderator or user.is_superuser))


def _log(request, form, **fields):
    ModAction.objects.create(moderator=request.user, reason=form.cleaned_data['reason'],
                             note=form.cleaned_data['note'], **fields)
    cache.delete(PANEL_CACHE_KEY)  # gizlenen/iptal edilen öneri ve maskelenen konu adı panelden hemen çıksın


@moderator_required
def content(request, ct, pk):
    """Yorum, konu ya da öneriyi gizler veya gizlemeyi kaldırır."""
    target = get_target(ct, pk, Hideable)
    owner = target.owner
    allowed = _allowed(request.user, owner)
    form = ActionForm(request.POST if request.method == 'POST' else None)
    if form.is_bound:
        if not allowed:
            raise PermissionDenied
        if form.is_valid():
            hide = not target.is_hidden
            with transaction.atomic():
                target.set_hidden(hide)  # öneride süren oylama iptal olur
                _log(request, form, user=owner, target=target, kind=Kind.HIDE if hide else Kind.UNHIDE)
            messages.success(request, 'Gizlendi.' if hide else 'Gizleme kaldırıldı.')
            return redirect(target)
    return render(request, 'moderation/content.html', {
        'target': target, 'kind': target._meta.verbose_name, 'owner': owner, 'allowed': allowed, 'form': form,
        'title': 'Moderasyon',
        'history': ModAction.objects.filter(content_type_id=ct, object_id=pk).select_related(*ROW),
    })


@moderator_required
def member(request, pk):
    """Üyeyi engeller ya da engeli kaldırır; sahte hesabı kapatır ya da yeniden açar."""
    user = get_object_or_404(User, pk=pk)
    allowed = _allowed(request.user, user)
    if user.is_active:
        kinds = [Kind.BAN, *([Kind.UNBAN] if user.is_banned else []), Kind.CLOSE]
    else:  # yalnızca moderasyonla kapatılan hesap açılır; doğrulanmamış hesap e-posta bağlantısıyla açılır
        last = ModAction.objects.filter(user=user, kind__in=[Kind.CLOSE, Kind.REOPEN]).values_list('kind', flat=True)
        kinds = [Kind.REOPEN] if last.first() == Kind.CLOSE else []
    form = UserActionForm(request.POST if request.method == 'POST' else None, kinds=kinds)
    if form.is_bound:
        if not allowed:
            raise PermissionDenied
        if form.is_valid():
            kind, until = form.cleaned_data['kind'], None
            with transaction.atomic():
                if kind == Kind.BAN:
                    user.banned_until = until = timezone.now() + timedelta(days=form.cleaned_data['days'])
                elif kind == Kind.UNBAN:
                    user.banned_until = None
                elif kind == Kind.CLOSE:  # yalnızca sahte hesap (form denetler)
                    user.is_active = False
                    CommentVote.withdraw_all(user)
                    TopicVote.withdraw_all(user)
                    withdraw_running(user)
                else:
                    user.is_active = True  # silinen oylar ve iptal edilen öneriler geri gelmez
                user.save(update_fields=['banned_until', 'is_active'])
                _log(request, form, user=user, kind=kind, until=until)
            messages.success(request, f'{Kind(kind).label.capitalize()} kaydedildi.')
            return redirect('mod_user', user.pk)
    return render(request, 'moderation/member.html', {
        'member': user, 'allowed': allowed, 'kinds': kinds, 'form': form, 'title': f'Moderasyon: {user}',
        'history': ModAction.objects.filter(user=user).select_related(*ROW)[:20],
    })


def log(request):
    """Herkese açık moderasyon kaydı: sayfalı; işlem, gerekçe ve kişiye (yönetici ya da üye) göre süzülür."""
    g = request.GET
    qs = ModAction.objects.select_related(*ROW)
    if g.get('kind') in Kind.values:
        qs = qs.filter(kind=g['kind'])
    if g.get('reason') in ModAction.Reason.values:
        qs = qs.filter(reason=g['reason'])
    if g.get('user'):
        qs = qs.filter(Q(user__username__iexact=g['user']) | Q(moderator__username__iexact=g['user']))
    return render(request, 'moderation/log.html', {
        'page': Paginator(qs, settings.FORUM['MOD_PER_PAGE']).get_page(g.get('page')),
        'kinds': Kind.choices, 'reasons': ModAction.Reason.choices, 'title': 'Moderasyon kaydı',
    })
