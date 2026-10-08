from django.conf import settings
from django.contrib import admin

from config.utils import PrivateLookups

from .models import Topic


@admin.register(Topic)
class TopicAdmin(PrivateLookups, admin.ModelAdmin):
    # Puan herkese açık; kimin ne verdiği gizli kalsın diye TopicVote admin'e kaydedilmez.
    list_display = ('title', 'parent', 'author', 'created_at', 'score', 'is_closed', 'is_deleted')
    list_filter = ('is_closed', 'is_deleted')
    list_select_related = ('parent', 'author')
    search_fields = ('title',)
    readonly_fields = ('author', 'created_at', 'score', 'is_hidden')  # gizleme yalnızca moderasyonla

    def get_readonly_fields(self, request, obj=None):
        return self.readonly_fields + (('parent',) if obj else ())  # taşıma yok

    # Kural 9: kurucu konuları yalnızca kuruluşta açar ve düzenler; sonrası tamamen oylamayla.
    def has_add_permission(self, request):
        return settings.FORUM['FOUNDING'] and super().has_add_permission(request)

    def has_change_permission(self, request, obj=None):
        return settings.FORUM['FOUNDING'] and super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        return False  # kural 7: gerçek silme yok, is_deleted kullanılır

    def save_model(self, request, obj, form, change):
        if not change:
            obj.author = request.user
        super().save_model(request, obj, form, change)
