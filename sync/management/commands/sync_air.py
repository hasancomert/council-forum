import random
import select
import socket
import struct
import time

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
        server = socket.create_server((host, port))
        clients, queue = {}, []  # soket -> SlipDecoder; (iletim zamanı, alıcı, çerçeve)
        self.stdout.write(f'Sahte hat {host}:{port} (kayıp {loss}, gecikme {delay} sn). Durdurmak için Ctrl+C.')
        try:
            while True:
                for sock in select.select([server, *clients], [], [], 0.01)[0]:
                    if sock is server:
                        conn, addr = server.accept()
                        if len(clients) == 2:
                            conn.close()  # en çok iki düğüm
                        else:
                            clients[conn] = SlipDecoder()
                            self.stdout.write(f'Bağlandı: {addr[0]}:{addr[1]}')
                        continue
                    try:
                        data = sock.recv(4096)
                    except OSError:
                        data = b''
                    if not data:
                        del clients[sock]
                        sock.close()
                        self.stdout.write('Bir düğüm ayrıldı.')
                        continue
                    for frame in clients[sock].feed(data):
                        if len(frame) == 1:  # modem yoklaması: iletilmez, "sürüm 1" diye yanıtlanır
                            send(sock, slip_encode(b'\x01'))
                        elif random.random() >= loss:
                            at, wire = time.monotonic() + delay, slip_encode(PREFIX + frame)
                            queue += [(at, other, wire) for other in clients if other is not sock]
                now = time.monotonic()
                while queue and queue[0][0] <= now:  # sıra korunur: gecikme herkese aynı
                    _, other, frame = queue.pop(0)
                    if other in clients:
                        send(other, frame)
        except KeyboardInterrupt:
            self.stdout.write('Durduruldu.')
        finally:
            server.close()
