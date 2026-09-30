from collections import defaultdict

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from config.utils import back, get_target, over_limit

from .forms import CommentForm
from .models import Comment, Commentable, CommentVote, vote_block


def updown(request, model, target, url):
    """▲/▼ oyu (yorum ve konu, model: CommentVote ya da TopicVote). vote.js'in fetch'i Accept: application/json
    gönderir: yanıt {score, mine} ya da hata 400 {error}. JS yoksa tarayıcı text/html ister: bugünkü gibi
    mesaj + url'e yönlendirme.
    """
    as_json = request.get_preferred_type(['text/html', 'application/json']) == 'application/json'
    try:
        mine = model.cast(target, request.user, {'1': 1, '-1': -1}.get(request.POST.get('value'), 0))
    except ValueError as e:
        if as_json:
            return JsonResponse({'error': str(e)}, status=400)
        messages.error(request, str(e))
        return redirect(url)
    if as_json:
        target.refresh_from_db(fields=['score'])  # cast() puanı veritabanında F() ile değiştirdi
        return JsonResponse({'score': target.score, 'mine': mine})
    return redirect(url)


def _back(request, comment):
    """İşlemden sonra formun geldiği sayfaya (next; ör. yorumların 3. sayfası), yorumun çapasıyla."""
    return f'{back(request, comment.target.get_absolute_url())}#c{comment.pk}'


def section(target, user, sort=None, number=None):
    """Hedefin yorumlarının bir sayfası (yorum bölümü ve API). Ana yorumlar veritabanında sıralanıp sayfalanır
    (COMMENTS_PER_PAGE), yanıtlar yalnızca sayfadaki ana yorumlar için gelir. Yorum sayısından bağımsız 4 sorgu:
    sayımlar, sayfa, yanıtlar ve kullanıcının oyları. Tek seviye yanıt olduğundan özyineleme yok, gruplama Python'da.
    """
    top = target.comments.filter(parent=None).select_related('author')
    top = top.order_by('-created_at') if sort == 'new' else top.order_by('-score', 'created_at')  # eşit puanda eski önde
    n = target.comments.aggregate(top=Count('pk', filter=Q(parent=None)),
                                  shown=Count('pk', filter=Q(is_deleted=False, is_hidden=False)))
    paginator = Paginator(top, settings.FORUM['COMMENTS_PER_PAGE'])
    paginator.count = n['top']  # count bir cached_property: kendi sayım sorgusu yerine yukarıdaki kullanılır
    page = paginator.get_page(number)  # geçersiz sayfa → ilk/son
    top = list(page)
    replies = list(target.comments.filter(parent__in=top).select_related('author').order_by('created_at'))
    mine = {}
    if top and user.is_authenticated:
        mine = dict(CommentVote.objects.filter(voter=user, comment__in=top + replies).values_list('comment_id', 'value'))
    groups = defaultdict(list)
    is_open, why = target.is_open, vote_block(user)
    for c in top + replies:
        c.my_vote = mine.get(c.pk, 0)
        c.masked = c.hidden_from(user)  # gizli metni yalnızca yazarı ve yöneticiler görür
        c.frozen = c.is_hidden or not is_open  # yanıt, oy ve düzenleme yok; yazar yine silebilir
        # ▲/▼ hep görünür; verilemiyorsa düğmeler soluk ve nedeni yazar (sorgu yok)
        c.why = why or ('Kendi yorumuna oy verilmez' if c.author_id == user.pk else 'Oylama kapalı' if c.frozen else '')
    for r in replies:
        groups[r.parent_id].append(r)  # yanıtlar hep kronolojik
    for c in top:
        c.children = groups[c.pk]
    return {'open': is_open, 'comments': top, 'page': page, 'sort': sort, 'count': n['shown']}


def create(user, target, data):
    """Yorum ya da yanıt yazar (site ve API); data: 'body', isteğe bağlı 'parent'. Hedef kapalıysa ya da üye engelliyse
    PermissionDenied (engelli okur ama yazamaz), boş/uzun yorumda ve hız sınırında ValueError (mesajla).
    """
    if not target.is_open or not user.can_post:
        raise PermissionDenied
    form = CommentForm(data)
    if not form.is_valid():
        raise ValueError('Yorum boş ya da çok uzun.')
    if over_limit(Comment.objects.filter(author=user), 'COMMENT_RATE'):  # silinenler de sayılır
        raise ValueError('Çok sık yorum yazıyorsun, biraz bekle.')
    p = str(data.get('parent') or '')
    parent = target.comments.filter(pk=p, is_deleted=False, is_hidden=False).first() if p.isdigit() else None
    comment = form.save(commit=False)
    comment.target, comment.author = target, user
    comment.parent_id = parent and (parent.parent_id or parent.pk)  # yanıta yanıt → ana yoruma; başka hedefin yorumu → None
    comment.save()
    return comment


@login_required
@require_POST
def add(request, ct, pk):
    target = get_target(ct, pk, Commentable)
    url = target.get_absolute_url()
    try:
        comment = create(request.user, target, request.POST)
    except ValueError as e:
        messages.error(request, str(e))
        return redirect(back(request, url))
    # Yanıt bulunduğu sayfaya; yeni ana yorum "en yeni" sıralamasının başında görünür.
    return redirect(_back(request, comment) if comment.parent_id else f'{url}?sort=new#c{comment.pk}')


@login_required
def edit(request, pk):
    comment = get_object_or_404(Comment, pk=pk, author=request.user, is_deleted=False)
    if comment.is_hidden or not comment.target.is_open or not request.user.can_post:
        raise PermissionDenied  # gizli yorum ve kapanan hedef donar; engelli düzenleyemez (silebilir)
    form = CommentForm(request.POST if request.method == 'POST' else None, instance=comment)
    if form.is_valid():
        if form.has_changed():
            comment.edited_at = timezone.now()
            form.save()
        return redirect(_back(request, comment))
    return render(request, 'comments/edit.html', {'form': form, 'back': _back(request, comment), 'title': 'Yorumu düzenle'})


@login_required
@require_POST
def vote(request, pk):
    comment = get_object_or_404(Comment, pk=pk)
    return updown(request, CommentVote, comment, _back(request, comment))


@login_required
@require_POST
def delete(request, pk):
    comment = get_object_or_404(Comment, pk=pk, author=request.user)
    comment.is_deleted = True  # yumuşak silme; hedef kapalı olsa da serbest, geri alınmaz
    comment.save(update_fields=['is_deleted'])
    return redirect(_back(request, comment))
