from django.urls import path

from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('topics/<int:pk>/', views.detail, name='topic'),
    path('topics/<int:pk>/vote/', views.vote, name='topic_vote'),
    path('topics/archive/', views.archive, name='archive'),
]
