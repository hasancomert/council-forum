from django.contrib import admin

from .models import Comment


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    # Salt okunur: yorum yazarındır, moderasyonla gizleme 8. adımda. Kural 6 gereği
    # kimin ne oy verdiği gizli kalsın diye CommentVote admin'e kaydedilmez.
    list_display = ('__str__', 'author', 'target_display', 'created_at', 'score', 'is_deleted')
    list_filter = ('is_deleted',)
    search_fields = ('body',)
    fields = readonly_fields = (
        'target_display', 'parent', 'author', 'body', 'created_at', 'edited_at', 'is_deleted', 'score',
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('author').prefetch_related('target')

    @admin.display(description='hedef')
    def target_display(self, obj):
        return obj.target

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
