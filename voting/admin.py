from django.contrib import admin

from config.utils import ReadOnlyAdmin

from .models import (
    ExpertProposal, RequestProposal, TopicCloseProposal, TopicDeleteProposal,
    TopicEditProposal, TopicOpenProposal, TopicUndoProposal,
)


class ProposalAdmin(ReadOnlyAdmin):
    # Öneri yalnızca sitedeki formdan açılır ve yalnızca oylamayla sonuçlanır. Kural 6 gereği kimin ne oy
    # verdiği gizli kalsın diye Vote admin'e kaydedilmez: kurucu da görmez.
    list_display = ('__str__', 'proposer', 'status', 'created_at', 'voting_ends_at', 'participant_count')
    list_filter = ('status',)
    readonly_fields = ('proposer', 'created_at', 'status', 'quorum', 'applied_at', 'is_hidden')


admin.site.register(
    (TopicOpenProposal, TopicEditProposal, TopicCloseProposal, TopicDeleteProposal,
     TopicUndoProposal, ExpertProposal, RequestProposal),
    ProposalAdmin,
)
