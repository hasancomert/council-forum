import random
import select
import socket
import struct
import time

from django.conf import settings
from django.core.management.base import BaseCommand

from sync.ports import SlipDecoder, slip_encode

PREFIX = struct.pack('bb', -50, 10)  # modem gibi: RSSI −50, SNR 10


def send(sock, data):
    try:
        sock.sendall(data)
    except OSError:
        pass  # ayrılan düğüm: okuma tarafı fark edip listeden çıkarır


class Command(BaseCommand):
    help = 'Sahte hat: iki eşitleyiciyi TCP ile bağlar (modem yerine SYNC_PORT=socket://127.0.0.1:9100).'
    requires_system_checks = []

    def add_arguments(self, parser):
        parser.add_argument('--host', default='127.0.0.1')
        parser.add_argument('--port', type=int, default=9100)
        parser.add_argument('--loss', type=float, default=0.0, help='paket kaybı olasılığı (0-1)')
        parser.add_argument('--delay', type=float, default=0.0, help='iletim gecikmesi (sn)')

    def handle(self, *args, host, port, loss, delay, **options):
        self.listen(host, port, loss, delay)
        self.stdout.write(f'Sahte hat {host}:{port} (kayıp {loss}, gecikme {delay} sn). Durdurmak için Ctrl+C.')
        try:
            while True:
                self.step()
        except KeyboardInterrupt:
            self.stdout.write('Durduruldu.')
        finally:
            self.server.close()

    def listen(self, host, port, loss=0.0, delay=0.0):
        self.server, self.loss, self.delay = socket.create_server((host, port)), loss, delay
        self.clients, self.queue = {}, []  # soket -> [SlipDecoder, son duyulduğu an]; (iletim zamanı, alıcı, çerçeve)

    def step(self):
        for sock in select.select([self.server, *self.clients], [], [], 0.01)[0]:
            now = time.monotonic()
            if sock is self.server:
                self.accept(now)
            elif sock in self.clients:  # bu turda düşürülmüş olabilir
                self.receive(sock, now)
        now = time.monotonic()
        while self.queue and self.queue[0][0] <= now:  # sıra korunur: gecikme herkese aynı
            _, other, frame = self.queue.pop(0)
            if other in self.clients:
                send(other, frame)

    def accept(self, now):
        conn, addr = self.server.accept()
        if len(self.clients) == 2:  # en çok iki düğüm
            # Kablosu çekilen düğümün bağlantısı kapanış gelmeden yarı açık kalır: uzun süredir susan, yeniden
            # bağlanana yer açar (canlı düğüm durum paketleri yüzünden normalde bu kadar susmaz).
            quiet = min(self.clients, key=lambda s: self.clients[s][1])
            if now - self.clients[quiet][1] <= settings.SYNC['ONLINE_SECONDS']:
                conn.close()
                self.stdout.write(f'Reddedildi (en çok iki düğüm): {addr[0]}:{addr[1]}')
                return
            self.drop(quiet, 'Uzun süredir susan düğüm çıkarıldı (yarı açık bağlantı).')
        self.clients[conn] = [SlipDecoder(), now]
        self.stdout.write(f'Bağlandı: {addr[0]}:{addr[1]}')

    def drop(self, sock, note='Bir düğüm ayrıldı.'):
        del self.clients[sock]
        sock.close()
        self.stdout.write(note)

    def receive(self, sock, now):
        try:
            data = sock.recv(4096)
        except OSError:
            data = b''
        if not data:
            self.drop(sock)
            return
        self.clients[sock][1] = now
        for frame in self.clients[sock][0].feed(data):
            if len(frame) == 1:  # modem yoklaması: iletilmez, "sürüm 1" diye yanıtlanır
                send(sock, slip_encode(b'\x01'))
            elif random.random() >= self.loss:
                at, wire = now + self.delay, slip_encode(PREFIX + frame)
                self.queue += [(at, other, wire) for other in self.clients if other is not sock]
