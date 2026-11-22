# LoRa ile iki forum: kurulum ve demo

İnternet olmayan bir yerde iki bilgisayardaki forum, STM32 Black Pill + Ra-02 modemlerle telsizden eşitlenir. Bu belge
kurulumu ve beş dakikalık demoyu anlatır. Komutlar PowerShell içindir; `python` komutları proje klasöründe, `.venv`
etkinken (`.venv\Scripts\Activate.ps1`) çalışır.

> **Taslak.** Yazılım adımları iki bilgisayar benzetimiyle (iki proje kopyası, modem yerine `sync_air`) baştan sona
> denendi. "(kartla doğrulanacak)" yazan yerler kartlarla ilk denemede doğrulanıp düzeltilecek.

## 1. Parçalar ve kablolama

Her bilgisayar için: STM32F401CC Black Pill (WeAct) ve veri taşıyan bir USB-C kablosu, Ra-02 (SX1278, 433 MHz) ve
433 MHz anten, 8 kablo.

| Ra-02 | Black Pill |
|-------|------------|
| 3.3V  | 3V3        |
| GND   | G          |
| NSS   | A4         |
| SCK   | A5         |
| MISO  | A6         |
| MOSI  | A7         |
| RST   | B0         |
| DIO0  | B1         |

Üç uyarı:

1. Ra-02 yalnızca **3,3 V** ile beslenir. Black Pill'in 5V pinine bağlanırsa bozulur.
2. **Anten takılı olmadan** modemi çalıştırmayın: antensiz yayın Ra-02'nin vericisine zarar verebilir.
3. Ra-02'nin pin aralığı **2,0 mm**: standart (2,54 mm) atlama kabloları ve breadboard oturmaz. Kabloları lehimleyin ya
   da 2,0 → 2,54 mm adaptör kullanın.

## 2. Firmware'i yükleme (bir kez, internet varken)

PlatformIO tek bilgisayarda yeterli, iki kart da oradan yüklenir. Ana `.venv`'e değil ayrı bir ortama kurulur
(`requirements.txt` temiz kalsın):

```powershell
python -m venv firmware\.venv
firmware\.venv\Scripts\python -m pip install platformio
```

Kartı DFU kipine alın: BOOT0'a basılı tutun, NRST'ye basıp bırakın, sonra BOOT0'ı bırakın (olmazsa BOOT0 basılıyken
USB'yi takın; bazı kartlar birkaç deneme ister). Sonra derleyip yükleyin (ilk seferde derleyici ve kütüphaneler iner):

```powershell
firmware\.venv\Scripts\pio run -d firmware -t upload
```

Beklenen: `SUCCESS`. Kart kendiliğinden yeniden başlar ve yeni bir COM portu görünür:

```powershell
[System.IO.Ports.SerialPort]::GetPortNames()
```

`dfu-util` kartı bulamazsa ("No DFU capable USB device"): Windows'ta DFU aygıtı WinUSB sürücüsüne kaydedilmelidir
([dfu-util](https://dfu-util.sourceforge.net/); [libusb wiki](https://github.com/libusb/libusb/wiki/Windows#driver-installation)
bunun için Zadig'i önerir). Kart DFU kipindeyken [Zadig](https://zadig.akeo.ie)'i açın, Options → List All Devices,
"STM32 BOOTLOADER"ı seçin, sürücü olarak WinUSB'yi seçip kurun, yüklemeyi yineleyin. (kartla doğrulanacak)

LED (PC13): her gönderme ve almada durum değiştirir; Ra-02 yanıt vermezse (kablolama, besleme) hızlı yanıp söner.

Radyo ayarları `firmware/platformio.ini`'de: 434,5 MHz, SF7, 125 kHz, 4/5, preamble 8, sync word `0x5A`, 10 dBm.
Değiştirirseniz iki kartı da yeniden yükleyin. SF, bant genişliği, kodlama oranı ya da preamble değişirse
`config/settings.py`'deki `SYNC['RADIO']` da aynı yapılır (yayın süresi hesabı).

## 3. Projeyi iki bilgisayara kurma (bir kez, internet varken)

Her iki bilgisayarda projeyi aynı sürümle kopyalayın (`git clone` ya da klasörü USB bellekle), sonra proje klasöründe:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

`.env`'in sonundaki satırları doldurun. 1. bilgisayar (hakem, oylamaları o sonuçlandırır):

```ini
DEBUG=1
OFFLINE=1
SYNC_NODE=1
SYNC_PORT=COM5
SYNC_KEY=grubunuza-ozel-uzun-bir-soz
FORUM_OVERRIDES={"QUORUM_MIN": 2, "MIN_ACCOUNT_AGE_DAYS": 0, "PROPOSAL_VOTING_DAYS": 0.003, "REQUEST_DISCUSSION_DAYS": 0.002, "REQUEST_VOTING_DAYS": 0.003, "PANEL_CACHE_SECONDS": 0}
```

2. bilgisayar: aynısı, yalnızca `SYNC_NODE=2` ve kendi COM portu.

- `OFFLINE=1`: kayıtta CAPTCHA ve e-posta doğrulaması yok, hesap hemen açılır.
- `SYNC_PORT`: o bilgisayara takılı modemin portu (bölüm 2'deki komutla bulunur).
- `SYNC_KEY` iki bilgisayarda aynı olmalı. Paketler bununla imzalanır, başka grupların paketleri yok sayılır.
- `FORUM_OVERRIDES` (tek satır): demo süreleri. Oylama 0,003 gün ≈ 4 dk 20 sn, yeter sayı 2, oy için hesap yaşı 0.

## 4. İlk kurulum (yalnızca 1. bilgisayarda, bir kez)

```powershell
python manage.py migrate
python manage.py createcachetable
python manage.py createsuperuser
python manage.py runserver
```

Tarayıcıda http://127.0.0.1:8000/admin/ adresine kurucu hesabıyla girin, **Konular → Ekle** ile ilk konuları açın
(ör. "Deneme"). Sonra `runserver`'ı Ctrl+C ile durdurun ve eşitlemeyi sıfırdan başlatın:

```powershell
python manage.py sync_init --reset
```

Hiçbir forum süreci açık değilken (klasörde `db.sqlite3-wal` kalmamışken) `db.sqlite3`'ü USB bellekle 2. bilgisayarın
proje klasörüne kopyalayın. 2. bilgisayarda başka kurulum gerekmez (`migrate`, `createsuperuser` çalıştırmayın).

- `sync_init --reset` kopyadan hemen önce bir kez çalışır. Kopyadan sonra bir tarafta yeniden çalıştırılırsa iki forum
  "Veritabanları uyumsuz" olur, kopya yinelenir.
- Kurucu hesabı iki tarafta da var: yalnızca 1. bilgisayarda kullanın.
- İki bilgisayarın saatini aynı dakikaya getirin (Ayarlar → Zaman ve dil → Tarih ve saat: otomatik ayarı kapatıp
  "Değiştir"). Fark 60 saniyeyi aşarsa durum sayfası uyarır. Sonuç iki tarafta yine aynı çıkar, yalnızca oylama saati
  geride olan tarafta daha geç kapanır.

## 5. Çalıştırma

Modemi takın, sonra her bilgisayarda iki PowerShell penceresi açın (`.venv` etkin, proje klasöründe):

```powershell
python manage.py runserver
```

```powershell
python manage.py sync_run
```

`sync_run` penceresinde sırayla "Hat açıldı: COM5", "Modem yanıt verdi (sürüm 1)" ve karşı taraf da çalışınca
"Bağlantı kuruldu." görünür; giden ve gelen her kayıt bir satırdır. Forum: http://127.0.0.1:8000. Menüdeki rozet
"LoRa: bağlı" (yeşil) olmalı.

## 6. Beş dakikalık demo

Her üye yalnızca kayıt olduğu bilgisayardan giriş yapar.

1. **Kayıt.** 1. bilgisayarda "Kayıt ol" ile Ali, 2. bilgisayarda Veli kaydolur; hesap hemen açılır.
2. **Öneri** (oylama yaklaşık 4 dakika sürdüğü için önce bu). 1. bilgisayarda Ali "Deneme" konusunu açar,
   "Diğer öneriler" → "Kapatma öner" → "Öneriyi aç", sonra "Evet". Birkaç saniye içinde öneri 2. bilgisayarın
   panelinde görünür; Veli de "Evet" der. Kimin ne oy verdiği görünmez, yalnızca katılım ("2/2 katılım").
3. **Yorum ve ▲/▼.** 1. bilgisayarda konu sayfası açıkken Veli konuya yorum yazar. Birkaç saniye içinde 1. bilgisayarda
   sayfanın üstünde "Karşı taraftan yeni içerik geldi · Yenile" çıkar (sayfa kendiliğinden yenilenmez, yazılan yorum
   kaybolmasın diye). Ali yenileyip yorumu ▲'lar; puan 2. bilgisayarda da 1 olur.
4. **Bağlantı kopması.** 2. bilgisayarın modemini çekin: yaklaşık 20 saniyede rozet "LoRa: bağlantı yok" olur. Veli bir
   yorum daha yazar, rozet "· bekleyen 1" gösterir. Modemi geri takın: `sync_run` "Hat açıldı", "Modem yanıt verdi" ve
   "Bağlantı kuruldu." yazar, yorum 1. bilgisayara gider, rozet yeniden "LoRa: bağlı" olur.
5. **Sonuç.** Oylama bitince 2. bilgisayardaki öneri sayfası birkaç saniye "Oylama bitti; sonuç iki forum eşitlenince
   açıklanacak." der. Hakem sonuçlandırınca iki tarafta da "Sonuç: Uygulandı" ve konu kapalı görünür.
6. **Eşitlik.** İki bilgisayarda http://127.0.0.1:8000/sync/ açılır: "İçerik özeti" iki tarafta aynıdır. Sayfada
   sinyal (RSSI/SNR), son bir saatteki yayın süresi, bekleyenler ve son giden/gelen kayıtlar görünür.

## 7. Sorun giderme

- **Rozet "LoRa: bağlantı yok":**
  - `sync_run` iki bilgisayarda da çalışıyor mu?
  - "Hat açılamadı (COM5)": port adı yanlış ya da modem takılı değil. Komut: `[System.IO.Ports.SerialPort]::GetPortNames()`.
  - "Modem yanıt verdi" satırı yok: LED hızlı yanıp sönüyorsa Ra-02 kablolaması; LED hiç değişmiyorsa firmware
    yüklü değil (bölüm 2).
  - "kendi düğüm numaramızla imzalı paket": iki bilgisayarda aynı `SYNC_NODE` var, biri 1 öbürü 2 olmalı.
  - `SYNC_KEY` iki tarafta farklıysa paketler sessizce yok sayılır.
  - Anten iki modemde de takılı mı?
- **"Veritabanları uyumsuz"** (durum sayfası ve `sync_run`): 2. bilgisayardaki `db.sqlite3` 1.'nin kopyası değil ya da
  kopyadan sonra `sync_init --reset` çalıştırıldı. İki taraftaki süreçleri kapatıp bölüm 4'teki kopyayı yineleyin
  (2. bilgisayarda o zamana kadar yazılanlar kaybolur).
- **"Saat farkı"** uyarısı: iki bilgisayarın saatini aynı dakikaya getirin.
- **COM portu görünmüyor:** kablo yalnızca şarj kablosu olabilir; kart DFU kipinde kalmış olabilir (BOOT0'a basmadan
  NRST'ye basın). Aygıt Yöneticisi → Bağlantı noktaları (COM ve LPT).
- **Başka grubun paketleri:** imza sayesinde forumunuza giremezler, ama aynı frekansta yayın süresini paylaşırsınız.
  `firmware/platformio.ini`'de `LORA_FREQ`'i (433,05–434,79 MHz arası, ör. `433500000`) ya da `LORA_SYNC`'i değiştirip
  iki kartı yeniden yükleyin.
- **Donanım yoksa ya da çalışmazsa:** modem yerine ağ (aynı Wi-Fi ya da kablo). 1. bilgisayarda üçüncü bir pencerede
  `python manage.py sync_air --host 0.0.0.0` çalıştırın (Windows güvenlik duvarı sorarsa özel ağlara izin verin).
  `.env`'de `SYNC_PORT`, 1. bilgisayarda `socket://127.0.0.1:9100`, 2. bilgisayarda `socket://<1. bilgisayarın IP'si>:9100`
  olur (IP: `ipconfig` → IPv4 adresi). `runserver` ve `sync_run`'ı yeniden başlatın. Ağ kısa süre koparsa bağlantı
  kendiliğinden geri gelir.

## 8. Bilinen sınırlar

- Telsiz trafiği şifresiz: takma adlar, yorumlar, kimin ne oy verdiği ve şikayet edenin kimliği havada okunabilir.
  Paketler imzalı olduğu için başkası sahte kayıt gönderemez.
- Aynı satır iki tarafta aynı anda değişirse 2. bilgisayarın değişikliği kaybolur (ör. yazar yorumunu düzenlerken öbür
  taraftaki yönetici aynı yorumu gizlerse).
- Aynı hesapla iki bilgisayardan işlem yapılmamalı: aynı öneriye iki taraftan verilen oy benzersizlik hatasına düşer.
- Üye yalnızca kayıt olduğu bilgisayardan giriş yapabilir (şifre telsizden gitmez).
- Aynı takma ad iki tarafta aynı anda alınırsa iki forum o üyeyi farklı adla gösterir (karşıda `-<numara>` ekli); o
  zaman içerik özetleri de farklı kalır.
- Bağlantı yokken oylama sonuçlanmaz; sonucu bekleyen öneri yalnızca durum sayfasında görünür.
- Saatlik yayın süresi bütçesi (%10) `sync_run` yeniden başlayınca sıfırdan sayılır.
