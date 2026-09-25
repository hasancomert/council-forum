from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ObjectDoesNotExist, PermissionDenied
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .forms import CommentForm
from .models import Comment, Commentable


@login_required
@require_POST
def add(request, ct, pk):
    try:
        target = get_object_or_404(ContentType, pk=ct).get_object_for_this_type(pk=pk)
    except ObjectDoesNotExist:
        raise Http404
    if not isinstance(target, Commentable):  # beyaz liste: ör. bir User'a yorum yazılamaz
        raise Http404
    if not target.is_open:
        raise PermissionDenied
    form = CommentForm(request.POST)
    if not form.is_valid():
        messages.error(request, 'Yorum boş ya da çok uzun.')
        return redirect(target)
    p = request.POST.get('parent', '')
    parent = target.comments.filter(pk=p, is_deleted=False).first() if p.isdigit() else None
    comment = form.save(commit=False)
    comment.target, comment.author = target, request.user
    comment.parent_id = parent and (parent.parent_id or parent.pk)  # yanıta yanıt → ana yoruma; başka hedefin yorumu → None
    comment.save()
    return redirect(comment)


@login_required
def edit(request, pk):
    comment = get_object_or_404(Comment, pk=pk, author=request.user, is_deleted=False)
    if not comment.target.is_open:
        raise PermissionDenied  # hedef kapanınca yorumlar donar
    form = CommentForm(request.POST if request.method == 'POST' else None, instance=comment)
    if form.is_valid():
        if form.has_changed():
            comment.edited_at = timezone.now()
            form.save()
        return redirect(comment)
    return render(request, 'comments/edit.html', {'form': form, 'comment': comment, 'title': 'Yorumu düzenle'})


@login_required
@require_POST
def delete(request, pk):
    comment = get_object_or_404(Comment, pk=pk, author=request.user)
    comment.is_deleted = True  # yumuşak silme; hedef kapalı olsa da serbest, geri alınmaz
    comment.save(update_fields=['is_deleted'])
    return redirect(comment)
