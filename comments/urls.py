from django.urls import path

from . import views

urlpatterns = [
    path('comments/<int:ct>/<int:pk>/', views.add, name='comment_add'),
    path('comments/<int:pk>/edit/', views.edit, name='comment_edit'),
    path('comments/<int:pk>/delete/', views.delete, name='comment_delete'),
]
