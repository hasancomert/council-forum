from django.core.exceptions import ImproperlyConfigured
from django.core.management.base import BaseCommand, CommandError

from sync import capture
from sync.tables import tables


class Command(BaseCommand):
    help = 'Eşitleme tetikleyicilerini kurar; yeniden çalıştırılabilir, günlüğe dokunmaz.'
    requires_system_checks = []  # düzelteceği uyarıyı (sync.W001) önce basmasın

    def add_arguments(self, parser):
        parser.add_argument('--reset', action='store_true', help='Günlüğü ve durumu sıfırla (yalnızca ilk kurulumda).')

    def handle(self, *args, reset=False, **options):
        try:
            capture.install()
        except ImproperlyConfigured as e:
            raise CommandError(e)
        self.stdout.write(f'Tetikleyiciler kuruldu ({len(tables())} tablo).')
        if reset:
            capture.reset()
            self.stdout.write('Günlük, gelen kaydı, pk sayaçları ve durum sıfırlandı.')
