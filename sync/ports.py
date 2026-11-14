"""Hatlar: modemin seri portu (ya da sahte hat, socket://), testlerdeki bellek içi hat; SLIP çerçeveleme ve yayın süresi.
Üç hat aynı arayüzü sunar: write(paket), read() -> (RSSI, SNR, paket) ya da None.
"""
import math
import random
import struct
import time
from collections import deque

import serial
from django.conf import settings

END, ESC, ESC_END, ESC_ESC = b'\xc0', b'\xdb', b'\xdc', b'\xdd'


def slip_encode(data):
    """Çerçeve: END + kaçışlı veri + END (önce ESC kaçar, yoksa END'in kaçışı yeniden kaçardı)."""
    return END + data.replace(ESC, ESC + ESC_ESC).replace(END, ESC + ESC_END) + END


class SlipDecoder:
    def __init__(self):
        self.buf = b''

    def feed(self, data):
        """Tamamlanan çerçeveler; boş çerçeve atılır. Son parça (END gelmemiş) sonraki veriyi bekler."""
        *frames, self.buf = (self.buf + data).split(END)
        return [f.replace(ESC + ESC_END, END).replace(ESC + ESC_ESC, ESC) for f in frames if f]


def airtime(nbytes):
    """Paketin havada kalma süresi (sn); Semtech AN1200.13, açık başlık, CRC açık, düşük hız iyileştirmesi kapalı."""
    radio = settings.SYNC['RADIO']
    sf, symbol = radio['sf'], 2 ** radio['sf'] / radio['bw']
    payload = 8 + max(math.ceil((8 * nbytes - 4 * sf + 28 + 16) / (4 * sf)) * radio['cr'], 0)
    return (radio['preamble'] + 4.25 + payload) * symbol


class SerialPort:
    """Modem (Black Pill + Ra-02) ya da sahte hat. Giden çerçeve = paket; gelen = [RSSI int8][SNR int8] + paket;
    1 baytlık gelen çerçeve modemin yoklama yanıtı (sürüm). Port hatasında istisna atmaz: kapanır, DOWN_RETRY
    saniyede bir yeniden açmayı dener (modem çekilse de forum ve eşitleyici çalışmaya devam eder).
    """
    def __init__(self, url):
        self.url, self.serial, self.retry_at, self.modem = url, None, 0.0, None
        self.decoder, self.frames = SlipDecoder(), deque()

    def port(self):
        if self.serial is None and time.monotonic() >= self.retry_at:
            try:
                self.serial = serial.serial_for_url(self.url, baudrate=115200, timeout=0.05)
            except (OSError, serial.SerialException, ValueError):
                self.retry_at = time.monotonic() + settings.SYNC['DOWN_RETRY']
        return self.serial

    def fail(self):
        try:
            self.serial.close()
        except (OSError, serial.SerialException):
            pass
        self.serial, self.retry_at = None, time.monotonic() + settings.SYNC['DOWN_RETRY']

    def write(self, packet):
        if self.port():
            try:
                self.serial.write(slip_encode(packet))
            except (OSError, serial.SerialException):
                self.fail()

    def read(self):
        while not self.frames:
            if not self.port():
                return None
            try:
                data = self.serial.read(self.serial.in_waiting or 1)  # ilk baytı en çok 50 ms bekler
            except (OSError, serial.SerialException):
                self.fail()
                return None
            if not data:
                return None
            self.frames.extend(self.decoder.feed(data))
        frame = self.frames.popleft()
        if len(frame) == 1:
            self.modem = frame[0]
            return None
        if len(frame) < 3:
            return None
        rssi, snr = struct.unpack('bb', frame[:2])
        return rssi, snr, frame[2:]

    def ping(self):
        """Modem takılı mı: 1 baytlık çerçeve havaya verilmez, modem sürümüyle yanıtlar."""
        self.write(b'\x00')


class MemoryPort:
    """Testlerdeki bellek içi hat: birinin yazdığı öbürünün kuyruğuna düşer; rng() < loss ise kaybolur."""
    def __init__(self, loss, rng):
        self.inbox, self.peer, self.loss, self.rng = deque(), None, loss, rng

    @classmethod
    def pair(cls, loss=0.0, rng=random.random):
        a, b = cls(loss, rng), cls(loss, rng)
        a.peer, b.peer = b, a
        return a, b

    def write(self, packet):
        if self.rng() >= self.loss:
            self.peer.inbox.append((-50, 10, packet))

    def read(self):
        return self.inbox.popleft() if self.inbox else None
