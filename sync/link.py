"""Taşıma protokolü: imzalı küçük paketler, dur-ve-bekle, durum paketi, yayın bütçesi. Veritabanı bilmez; mesajları
`host`'tan alır ve ona teslim eder (Runner ya da testteki sahte host). step() beklemez, uyumaz: döngü dışarıda.
"""
import hmac
import random
import struct
import time
from collections import deque

from django.conf import settings

from .ports import airtime

# Büyük uçlu. Her pakette ikinci bayt gönderen düğüm; sonunda HMAC-SHA256 etiketi (TAG bayt).
DATA = struct.Struct('>cBIHH')  # 'D', düğüm, sıra no, parça, parça sayısı + parça
ACK = struct.Struct('>cBIH')  # 'A', düğüm, sıra no, beklenen parça (parça sayısına eşitse mesaj tamam)
STATUS = struct.Struct('>cBIIII')  # 'S', düğüm, saat, son sıra no, uygulanan, şema özeti
KINDS = {b'D': DATA, b'A': ACK, b'S': STATUS}


class Link:
    def __init__(self, port, host, *, node, key, now=time.monotonic, rng=random.random):
        self.port, self.host, self.node, self.key, self.now, self.rng = port, host, node, key, now, rng
        self.cfg = settings.SYNC
        self.budget = 3600 * self.cfg['AIRTIME_PERCENT'] / 100
        self.online, self.heard, self.rssi, self.snr = False, None, None, None
        self.sent, self.used = deque(), 0.0  # son bir saatte gönderilenler: (zaman, yayın süresi)
        self.rx_seq, self.rx = None, []  # gelen yarım mesaj
        self.out, self.part, self.retry_at, self.misses = None, 0, 0.0, 0  # giden mesaj: (sıra no, parçalar)
        self.status_at = 0.0

    def step(self):
        got = self.port.read()
        if got:
            self.receive(*got)
        self.send()

    def sign(self, body):
        return hmac.new(self.key, body, 'sha256').digest()[:self.cfg['TAG']]

    def write(self, body):
        packet = body + self.sign(body)
        self.port.write(packet)
        self.sent.append((self.now(), airtime(len(packet))))
        self.used += self.sent[-1][1]

    def airtime_used(self):
        while self.sent and self.sent[0][0] <= self.now() - 3600:
            self.used -= self.sent.popleft()[1]
        if not self.sent:
            self.used = 0.0  # kayan toplamın küsurat birikmesin
        return self.used

    def receive(self, rssi, snr, packet):
        body, tag = packet[:-self.cfg['TAG']], packet[-self.cfg['TAG']:]
        kind = KINDS.get(body[:1])
        # başka grubun ya da yabancının paketi, kendi yankımız, kısa kalmış paket: yok sayılır
        if not kind or len(body) < kind.size or body[1] == self.node or not hmac.compare_digest(tag, self.sign(body)):
            return
        self.heard, self.rssi, self.snr, self.online = self.now(), rssi, snr, True
        letter, _, *fields = kind.unpack_from(body)
        if letter == b'D':
            self.on_data(*fields, body[DATA.size:])
        elif letter == b'A':
            self.on_ack(*fields)
        else:
            self.host.on_status(*fields)

    def ack(self, seq, expected):
        self.write(ACK.pack(b'A', self.node, seq, expected))  # onay hemen gider: beklemez, bütçeye sayılır

    def on_data(self, seq, part, count, chunk):
        if seq <= self.host.applied():
            return self.ack(seq, count)  # uygulanmış mesajın yinelemesi: yalnızca onay
        if self.rx_seq != seq:
            self.rx_seq, self.rx = seq, []
        if part == len(self.rx) < count:  # yalnızca beklenen parça; başkası atılır
            self.rx.append(chunk)
        if len(self.rx) < count:  # toplu onay: "sıradaki beklediğim parça" (yeniden başlamış alıcı 0 der)
            return self.ack(seq, len(self.rx))
        if self.host.deliver(seq, b''.join(self.rx)):
            self.ack(seq, count)
            self.rx_seq, self.rx = None, []
        # teslim reddedildiyse onay yok: son parça yeniden gelince yeniden denenir

    def on_ack(self, seq, expected):
        if self.out and self.out[0] == seq:
            self.part, self.retry_at, self.misses = expected, 0.0, 0
            if expected >= len(self.out[1]):
                self.host.delivered(seq)
                self.out = None

    def send(self):
        t, cfg = self.now(), self.cfg
        # yarı çift yönlü: son duyulan paketten sonra GUARD bekle; bütçe dolduysa veri ve durum bekler
        if (self.heard is not None and t < self.heard + cfg['GUARD']) or self.airtime_used() > self.budget:
            return
        if t >= self.status_at:  # mesaj sürerken de: alıcı şemayı her an öğrenebilsin
            clock, last, schema = self.host.status()
            self.write(STATUS.pack(b'S', self.node, clock, last, self.host.applied(), schema))
            self.status_at = t + cfg['STATUS_SECONDS']
            return
        if self.out is None and (message := self.host.next_message()):
            seq, body = message
            self.out = (seq, [body[i:i + cfg['CHUNK']] for i in range(0, len(body), cfg['CHUNK'])] or [b''])
            self.part, self.retry_at = 0, t
        if self.out and t >= self.retry_at:
            seq, parts = self.out
            self.write(DATA.pack(b'D', self.node, seq, self.part, len(parts)) + parts[self.part])
            self.misses += 1
            if self.misses >= cfg['DOWN_AFTER']:  # art arda onaysız: bağlantı yok, daha seyrek dene
                self.online = False
                self.retry_at = t + cfg['DOWN_RETRY']
            else:
                self.retry_at = t + cfg['ACK_TIMEOUT'][self.node] + self.rng() * cfg['JITTER']
