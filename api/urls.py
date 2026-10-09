from django.urls import path

from . import views

# Mobil uygulamanın JSON API'si; sitenin adresleriyle aynı düzen (ct: içerik tipi, slug: öneri tipi).
urlpatterns = [
    path('login/', views.login),
    path('me/', views.me),
    path('topics/', views.topics),
    path('topics/<int:pk>/', views.topic),
    path('topics/<int:pk>/vote/', views.topic_vote),
    path('comments/<int:ct>/<int:pk>/', views.comments),
    path('comments/<int:pk>/delete/', views.comment_delete),
    path('comments/<int:pk>/vote/', views.comment_vote),
    path('proposals/', views.proposals),
    path('proposals/new/<slug:slug>/', views.proposal_new),
    path('proposals/new/<slug:slug>/<int:topic_pk>/', views.proposal_new),
    path('proposals/<slug:slug>/<int:pk>/', views.proposal),
    path('proposals/<slug:slug>/<int:pk>/vote/', views.proposal_vote),
    path('report/<int:ct>/<int:pk>/', views.report),
]
