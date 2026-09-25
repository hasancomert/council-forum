from django.core.management.base import BaseCommand
from django.utils import timezone

from voting.models import PROPOSAL_MODELS, BaseProposal


class Command(BaseCommand):
    help = 'Süresi dolmuş önerileri sonuçlandırır (kural 3, 4); kabul edilenleri uygular.'

    def handle(self, *args, **options):
        now = timezone.now()
        count = 0
        for model in PROPOSAL_MODELS:
            queryset = model.objects.filter(status=BaseProposal.Status.VOTING, voting_ends_at__lte=now)
            queryset = queryset | model.objects.filter(status=BaseProposal.Status.ACCEPTED, applied_at__isnull=True)
            for proposal in queryset:
                proposal.finalize()
                count += 1
        self.stdout.write(self.style.SUCCESS(f'{count} öneri işlendi.'))
