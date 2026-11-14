// LoRa modem: bilgisayarla USB seri (SLIP) <-> Ra-02 (SX1278). Protokol sync/ports.py'deki SerialPort ile aynı:
// gelen çerçeve = havaya verilecek paket (2-255 bayt); 1 baytlık çerçeve yoklamadır, havaya verilmez, sürümle
// yanıtlanır; giden çerçeve = [RSSI int8][SNR int8] + paket. Dinamik bellek yok.
#include <Arduino.h>
#include <LoRa.h>

const uint8_t END = 0xC0, ESC = 0xDB, ESC_END = 0xDC, ESC_ESC = 0xDD, VERSION = 1;
const uint32_t LED = PC13;  // düşükte yanar

uint8_t frame[255];  // bilgisayardan gelen çerçeve (LoRa paketinin en büyük boyu)
size_t len = 0;
bool escaped = false, overflow = false;

void put(uint8_t b) {  // kaçışlı tek bayt
  if (b == END || b == ESC) {
    Serial.write(ESC);
    Serial.write(b == END ? ESC_END : ESC_ESC);
  } else {
    Serial.write(b);
  }
}

void handle() {  // tamamlanan çerçeve; boş çerçeve (baştaki END) atlanır
  if (len == 1) {
    Serial.write(END);
    put(VERSION);
    Serial.write(END);
  } else if (len > 1) {
    LoRa.beginPacket();
    LoRa.write(frame, len);
    LoRa.endPacket();  // yayın bitene kadar bekler; gelen baytlar USB arabelleğinde birikir
    digitalToggle(LED);
  }
}

void setup() {
  pinMode(LED, OUTPUT);
  digitalWrite(LED, HIGH);
  Serial.begin(115200);  // USB CDC: hız önemsiz
  LoRa.setPins(PA4, PB0, PB1);  // NSS, RST, DIO0; SPI varsayılan pinlerde (PA5, PA6, PA7)
  if (!LoRa.begin(LORA_FREQ)) {
    for (;;) {  // Ra-02 yanıt vermiyor (kablo, besleme): hızlı yanıp söner
      digitalToggle(LED);
      delay(100);
    }
  }
  LoRa.setSpreadingFactor(LORA_SF);
  LoRa.setSignalBandwidth(LORA_BW);
  LoRa.setCodingRate4(LORA_CR);
  LoRa.enableCrc();
  LoRa.setSyncWord(LORA_SYNC);
  LoRa.setTxPower(LORA_POWER);
}

void loop() {
  while (Serial.available()) {
    uint8_t b = Serial.read();
    if (b == END) {
      if (!overflow) handle();
      len = 0;
      escaped = overflow = false;
    } else if (b == ESC) {
      escaped = true;
    } else {
      if (escaped) b = b == ESC_END ? END : b == ESC_ESC ? ESC : b;
      escaped = false;
      if (len < sizeof frame) frame[len++] = b;
      else overflow = true;  // 255 bayttan uzun: sonraki END'e kadar atılır
    }
  }
  if (LoRa.parsePacket() > 0) {  // CRC'si bozuk paketi kütüphane vermez
    Serial.write(END);
    put((int8_t)constrain(LoRa.packetRssi(), -128, 127));
    put((int8_t)lround(LoRa.packetSnr()));
    while (LoRa.available()) put(LoRa.read());
    Serial.write(END);
    digitalToggle(LED);
  }
}
