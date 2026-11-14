from django.urls import path

from . import views

urlpatterns = [
    path('', views.status, name='sync_status'),
    path('status.json', views.status_json, name='sync_json'),
]
