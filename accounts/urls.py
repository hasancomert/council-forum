from django.contrib.auth.decorators import login_required
from django.urls import include, path
from django.views.generic import TemplateView

from . import views

urlpatterns = [
    path('', login_required(TemplateView.as_view(template_name='accounts/account.html', extra_context={
        'title': 'Hesabım'})), name='account'),
    path('delete/', views.delete_account, name='account_delete'),
    path('signup/', views.signup, name='signup'),
    path('activate/<uidb64>/<token>/', views.activate, name='activate'),
    path('', include('django.contrib.auth.urls')),  # giriş, çıkış, şifre değiştirme/sıfırlama
]
