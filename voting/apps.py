from django.apps import AppConfig
from django.core import checks

from .checks import forum_settings


class VotingConfig(AppConfig):
    name = 'voting'
    verbose_name = 'Oylama'

    def ready(self):
        checks.register(forum_settings)  # kural sayıları açılışta denetlenir
