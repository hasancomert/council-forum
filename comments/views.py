from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ObjectDoesNotExist, PermissionDenied
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from config.utils import back, over_limit

from .forms import CommentForm
from .models import Comment, Commentable, CommentVote


def _back(request, comment):
    """İşlemden sonra formun geldiği sayfaya (next; ör. yorumların 3. sayfası), yorumun çapasıyla."""
    return f'{back(request, comment.target.get_absolute_url())}#c{comment.pk}'


@login_required
@require_POST
def add(request, ct, pk):
    try:
        target = get_object_or_404(ContentType, pk=ct).get_object_for_this_type(pk=pk)
    except ObjectDoesNotExist:
        raise Http404
    if not isinstance(target, Commentable):  # beyaz liste: ör. bir User'a yorum yazılamaz
        raise Http404
    if not target.is_open or not request.user.can_post:  # engelli okur ama yazamaz
        raise PermissionDenied
    url = target.get_absolute_url()
    form = CommentForm(request.POST)
    if not form.is_valid():
        messages.error(request, 'Yorum boş ya da çok uzun.')
        return redirect(back(request, url))
    if over_limit(Comment.objects.filter(author=request.user), 'COMMENT_RATE'):  # silinenler de sayılır
        messages.error(request, 'Çok sık yorum yazıyorsun, biraz bekle.')
        return redirect(back(request, url))
    p = request.POST.get('parent', '')
    parent = target.comments.filter(pk=p, is_deleted=False, is_hidden=False).first() if p.isdigit() else None
    comment = form.save(commit=False)
    comment.target, comment.author = target, request.user
    comment.parent_id = parent and (parent.parent_id or parent.pk)  # yanıta yanıt → ana yoruma; başka hedefin yorumu → None
    comment.save()
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
    try:
        CommentVote.cast(comment, request.user, {'1': 1, '-1': -1}.get(request.POST.get('value'), 0))
    except ValueError as e:
        messages.error(request, str(e))
    return redirect(_back(request, comment))


@login_required
@require_POST
def delete(request, pk):
    comment = get_object_or_404(Comment, pk=pk, author=request.user)
    comment.is_deleted = True  # yumuşak silme; hedef kapalı olsa da serbest, geri alınmaz
    comment.save(update_fields=['is_deleted'])
    return redirect(_back(request, comment))
