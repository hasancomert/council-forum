from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .models import Topic, TopicVote


def home(request):  # 7. adıma kadar geçici
    return render(request, 'home.html', {'topics': Topic.objects.visible().filter(parent=None)})


def archive(request):
    # Kural 7: silinmiş konunun yalnızca başlığı ve tarihi görünür (şablonda); içerik gizli kalır.
    topics = Topic.objects.filter(Q(is_closed=True) | Q(is_deleted=True)).select_related('parent')
    return render(request, 'topics/archive.html', {'topics': topics, 'title': 'Arşiv'})


def detail(request, pk):
    topic = get_object_or_404(Topic.objects.visible(), pk=pk)  # gizli konu 404
    user = request.user
    return render(request, 'topics/detail.html', {
        'topic': topic, 'title': topic.title, 'children': topic.children.visible(),
        'votable': user.is_authenticated and topic.can_be_voted_by(user),
        # a and b or 0: giriş yoksa ya da oy yoksa 0
        'my_vote': user.is_authenticated and TopicVote.objects.filter(
            topic=topic, voter=user).values_list('value', flat=True).first() or 0,
    })


@login_required
@require_POST
def vote(request, pk):
    topic = get_object_or_404(Topic, pk=pk)
    try:
        TopicVote.cast(topic, request.user, {'1': 1, '-1': -1}.get(request.POST.get('value'), 0))
    except ValueError as e:
        messages.error(request, str(e))
    return redirect(topic)
