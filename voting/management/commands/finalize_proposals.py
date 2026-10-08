from django.core.management.base import BaseCommand, CommandError

from voting.models import PROPOSAL_MODELS


class Command(BaseCommand):
    help = 'Süresi dolmuş önerileri sonuçlandırır (kural 3, 4); kabul edilenleri uygular.'

    def handle(self, *args, **options):
        done, failed = 0, 0
        for model in PROPOSAL_MODELS:
            for proposal in model.objects.due():
                try:
                    proposal.finalize()
                    done += 1
                except Exception as e:  # bir önerinin hatası ötekileri durdurmasın; sonraki çalışmada yeniden denenir
                    failed += 1
                    self.stderr.write(f'{proposal.SLUG}/{proposal.pk}: {e!r}')
        self.stdout.write(self.style.SUCCESS(f'{done} öneri işlendi.'))
        if failed:
            raise CommandError(f'{failed} öneri işlenemedi.')  # çıkış kodu 1: systemd birimi hatalı görünür
