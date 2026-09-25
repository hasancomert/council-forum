from django.contrib.contenttypes.views import shortcut
from django.urls import path

from . import views

urlpatterns = [
    path('mod/', views.queue, name='mod_queue'),
    path('report/<int:ct>/<int:pk>/', views.report, name='report'),
    path('mod/log/', views.log, name='mod_log'),
    path('mod/user/<int:pk>/', views.member, name='mod_user'),
    path('mod/<int:ct>/<int:pk>/', views.content, name='mod_content'),
    # Kayıttaki içerik bağlantısı: nesneyi yükleyip get_absolute_url'ine yönlendirir (Django'nun hazır görünümü).
    path('r/<int:content_type_id>/<int:object_id>/', shortcut, name='goto'),
]
