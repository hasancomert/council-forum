from django.apps import AppConfig
from django.core import checks
from django.db.models.signals import post_migrate


class SyncConfig(AppConfig):
    name = 'sync'
    verbose_name = 'LoRa eşitleme'

    def ready(self):
        from . import capture  # modeller ancak burada hazır
        post_migrate.connect(capture.reinstall, sender=self)  # eşitleme açıkken her migrate'ten sonra
        checks.register(capture.check_triggers)
