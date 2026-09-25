from django.contrib import admin

from .models import (
    ExpertProposal, RequestProposal, TopicCloseProposal, TopicDeleteProposal,
    TopicEditProposal, TopicOpenProposal, TopicUndoProposal, Vote,
)


class ProposalAdmin(admin.ModelAdmin):
    # Test amaçlı: tüm öneri tipleri aynı admin sınıfını paylaşır (ortak alanlar yeter).
    list_display = ('__str__', 'proposer', 'status', 'created_at', 'voting_ends_at', 'participant_count')
    list_filter = ('status',)
    readonly_fields = ('proposer', 'created_at', 'status', 'applied_at')

    def save_model(self, request, obj, form, change):
        if not change:
            obj.proposer = request.user
        super().save_model(request, obj, form, change)


admin.site.register(
    (TopicOpenProposal, TopicEditProposal, TopicCloseProposal, TopicDeleteProposal,
     TopicUndoProposal, ExpertProposal, RequestProposal),
    ProposalAdmin,
)


@admin.register(Vote)
class VoteAdmin(admin.ModelAdmin):
    list_display = ('voter', 'proposal', 'choice', 'weight', 'voted_at')
    list_filter = ('choice',)
    readonly_fields = ('content_type', 'object_id', 'voter', 'choice', 'weight', 'voted_at')

    def has_add_permission(self, request):
        return False  # oylar yalnızca Vote.cast() ile oluşturulur
