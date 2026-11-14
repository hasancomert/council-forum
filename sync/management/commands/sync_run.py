import logging
import time

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from sync import capture
from sync.gate import enabled, is_arbiter
from sync.ports import SerialPort
from sync.runner import Runner


class Command(BaseCommand):
    help = 'Eşitleyici: karşı düğümle modem (ya da sahte hat) üzerinden eşitlenir. Ctrl+C ile durur.'
    requires_system_checks = []  # eksik tetikleyiciyi kendisi açıklar

    def handle(self, *args, **options):
        if not (enabled() and settings.SYNC['PORT']):  # anahtarı ayarlar zorunlu kılar
            raise CommandError("Eşitleme kapalı: .env'de SYNC_NODE (1 ya da 2), SYNC_PORT ve SYNC_KEY olmalı.")
        if not capture.installed():
            raise CommandError('Eşitleme tetikleyicileri kurulu değil: python manage.py sync_init')
        log = logging.getLogger('sync')  # giden/gelen mesajlar ve hatalar bu terminale (DEBUG'da da)
        handler = logging.StreamHandler(self.stdout)
        handler.setFormatter(logging.Formatter('%(asctime)s %(message)s', '%H:%M:%S'))
        log.addHandler(handler)
        log.setLevel(logging.INFO)
        log.propagate = False
        port = SerialPort(settings.SYNC['PORT'])
        port.ping()
        runner, online, modem = Runner(port), False, None
        node = f"{settings.SYNC['NODE']}{' (hakem)' if is_arbiter() else ''}"
        self.stdout.write(f"Düğüm {node}, hat {settings.SYNC['PORT']}. Durdurmak için Ctrl+C.")
        try:
            while True:
                runner.tick()
                if port.serial is None:
                    time.sleep(0.05)  # port yok: boşuna dönme (açıkken okuma 50 ms bekler)
                if port.modem != modem:
                    modem = port.modem
                    log.info('Modem yanıt verdi (sürüm %s).', modem)
                if runner.link.online != online:
                    online = runner.link.online
                    log.info('Bağlantı kuruldu.' if online else 'Bağlantı yok.')
        except KeyboardInterrupt:
            self.stdout.write('Durduruldu.')
