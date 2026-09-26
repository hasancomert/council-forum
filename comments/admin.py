from django.contrib import admin

from config.utils import ReadOnlyAdmin

from .models import Comment


@admin.register(Comment)
class CommentAdmin(ReadOnlyAdmin):
    # Yorum yazarındır, gizleme yalnızca moderasyonla. Kural 6 gereği
    # kimin ne oy verdiği gizli kalsın diye CommentVote admin'e kaydedilmez.
    list_display = ('__str__', 'author', 'target_display', 'created_at', 'score', 'is_deleted', 'is_hidden')
    list_filter = ('is_deleted', 'is_hidden')
    search_fields = ('body',)
    fields = readonly_fields = (
        'target_display', 'parent', 'author', 'body', 'created_at', 'edited_at', 'is_deleted', 'is_hidden', 'score',
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('author').prefetch_related('target')

    @admin.display(description='hedef')
    def target_display(self, obj):
        return obj.target
