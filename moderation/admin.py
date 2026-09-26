from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html

from config.utils import ReadOnlyAdmin

from .models import Report


@admin.register(Report)
class ReportAdmin(ReadOnlyAdmin):
    # Kurucu için salt okunur liste. Şikayet eden hiçbir sütunda, süzgeçte ve aramada yok; işlem yalnızca
    # yöneticilerin mod/ sayfalarından yapılır ki herkese açık kayda düşsün.
    list_display = fields = readonly_fields = ('target_link', 'content_type', 'created_at', 'is_open')
    list_display_links = None  # içerik sütunu zaten bağlantı; ayrıntı sayfasında listeden fazlası yok
    list_filter = ('is_open', ('content_type', admin.RelatedOnlyFieldListFilter))

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('content_type').prefetch_related('target')

    @admin.display(description='içerik')
    def target_link(self, obj):
        return format_html('<a href="{}">{}</a>', reverse('goto', args=[obj.content_type_id, obj.object_id]),
                           str(obj.target) or '—')  # metni silinmiş yorum
