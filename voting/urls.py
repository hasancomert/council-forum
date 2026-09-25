from django.urls import path

from . import views

urlpatterns = [
    path('proposals/', views.proposal_list, name='proposals'),
    path('proposals/new/<slug:slug>/', views.new, name='proposal_new'),
    path('proposals/new/<slug:slug>/<int:topic_pk>/', views.new, name='proposal_new'),
    path('proposals/<slug:slug>/<int:pk>/', views.detail, name='proposal'),
    path('proposals/<slug:slug>/<int:pk>/vote/', views.vote, name='proposal_vote'),
]
