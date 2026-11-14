from django.apps import AppConfig
from django.core import checks
from django.db.models.signals import post_migrate, pre_save


class SyncConfig(AppConfig):
    name = 'sync'
    verbose_name = 'LoRa eşitleme'

    def ready(self):
        from . import capture  # modeller ancak burada hazır
        post_migrate.connect(capture.reinstall, sender=self)  # eşitleme açıkken her migrate'ten sonra
        pre_save.connect(capture.assign_pk)  # göndericisiz: eşitlenen her model
        checks.register(capture.check_triggers)
