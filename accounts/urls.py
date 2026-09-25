from django.urls import include, path

from . import views

urlpatterns = [
    path('signup/', views.signup, name='signup'),
    path('activate/<uidb64>/<token>/', views.activate, name='activate'),
    path('', include('django.contrib.auth.urls')),  # giriş, çıkış, şifre değiştirme/sıfırlama
]
