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
            # kabul edilip uygulanmamış: yarıda kalmış ya da bu sürümden önce bekletilmiş öneri
            queryset = queryset | model.objects.filter(status=BaseProposal.Status.ACCEPTED)
            for proposal in queryset:
                proposal.finalize()
                count += 1
        self.stdout.write(self.style.SUCCESS(f'{count} öneri işlendi.'))
