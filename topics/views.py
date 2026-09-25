from django.db.models import Q
from django.shortcuts import get_object_or_404, render

from .models import Topic


def home(request):  # 7. adıma kadar geçici
    return render(request, 'home.html', {'topics': Topic.objects.visible().filter(parent=None)})


def archive(request):
    # Kural 7: silinmiş konunun yalnızca başlığı ve tarihi görünür (şablonda); içerik gizli kalır.
    topics = Topic.objects.filter(Q(is_closed=True) | Q(is_deleted=True)).select_related('parent')
    return render(request, 'topics/archive.html', {'topics': topics, 'title': 'Arşiv'})


def detail(request, pk):
    topic = get_object_or_404(Topic.objects.visible(), pk=pk)  # gizli konu 404
    return render(request, 'topics/detail.html', {
        'topic': topic, 'title': topic.title, 'children': topic.children.visible(),
    })
