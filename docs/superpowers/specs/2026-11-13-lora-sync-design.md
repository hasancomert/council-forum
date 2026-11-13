# 11. adım tasarımı: iki forumun LoRa ile eşitlenmesi

Tarih: 2026-11-13. Durum: bağımsız gözden geçirmeden geçti, kullanıcı onayladı. Bu belge "ne ve neden"i anlatır;
adım adım uygulama planı ayrı dosyada.

## Amaç ve neden

İnternet olmayan bir yerde iki kişi, iki ayrı bilgisayarda aynı forumu kullanabilsin: ikisi de aynı anda gezsin,
yorum yazsın, oy versin, öneri açsın; bir taraftaki eylem birkaç saniye içinde öbür tarafta görünsün.

Bu bir ders projesi. Hoca çalışan sisteme ve arayüze bakacak (vize notunun %30'u). Teslim yaklaşık 2026-11-27;
vizeler yüzünden fiilî çalışma süresi yaklaşık bir hafta. Bu yüzden en az riskli ve en az kod isteyen yol seçildi.

## Donanım

- 2 × STM32F401 Black Pill (USB-C, 3,3 V).
- 2 × Ai-Thinker Ra-02 (SX1278, 433 MHz, SPI) + 2 × 433 MHz anten. Modül ürün sayfasının adından çıkarıldı
  ("10 km menzilli LoRa modülü SX1278"); kutudan çıkınca üstündeki yazıyla doğrulanacak.
- İki Windows bilgisayar (VS Code, PowerShell).

## Hedefler

1. Her bilgisayarda forumun tam kopyası çalışır (Django + SQLite), tarayıcıdan `http://127.0.0.1:8000`.
2. Bir taraftaki her eylem (kayıt, konu, yorum, ▲/▼, öneri, karar oyu, moderasyon) öbür tarafa ulaşır:
   kısa eylem 1–2 saniyede, en uzun yorum (5000 karakter) yaklaşık 15–20 saniyede.
3. Bağlantı kopukken iki taraf da çalışır; bağlantı gelince birikenler sırayla gider.
4. Bir oylamanın sonucu iki tarafta her zaman aynıdır.
5. Bağlantı durumu ve trafik arayüzde görünür (hocanın göreceği kısım).
6. Bütün mantık donanım olmadan geliştirilip test edilir (sahte hat).
7. İnternetli normal yayın bozulmaz: `SYNC_NODE` boşken hiçbir davranış değişmez, mevcut testler aynen geçer.

## Hedef dışı

- Forumun STM32'nin içinde çalışması (F401'de Linux yok, RAM 64–96 KB; Django çalışmaz).
- İkiden fazla düğüm.
- Telsiz trafiğinin şifrelenmesi (yalnızca imzalanır; Python standart kütüphanesinde AES yok).
- Şifre, e-posta, ad ve soyadın telsizden gitmesi; bir üyenin öbür bilgisayardan giriş yapması.
- PostgreSQL'de eşitleme (yalnızca SQLite).
- Sayfanın kendiliğinden yenilenmesi (yalnızca "yeni içerik geldi" uyarısı).
- Firmware'in STM32CubeIDE/HAL ile yazılması.

## Kaçınılacaklar

- İki forumun sessizce farklılaşması, özellikle oylama sonucunun.
- Eşitleme kodunun mevcut uygulamalara (accounts, topics, voting, comments, moderation) yayılması.
- Yalnızca donanımla denenebilen mantık.

## Kısıtlar

- LoRa yarı çift yönlüdür (aynı anda ya gönderir ya dinler), paket en fazla 255 bayt, SF7/125 kHz'de
  yaklaşık 5 kbit/sn; paket kaybı olağandır.
- Türkiye'de 433,05–434,79 MHz lisanssız bant, 10 mW: frekans bandın içinde, güç 10 dBm olacak.
- Aynı bantta yayın süresi sınırı: BTK'nın sınıf 1 teknik ölçüt tablosuna göre saatte en çok %10 (tablo bir web
  aramasında görüldü; yönetmelik metninden teyit edilmedi). Taşıma katmanı bu bütçeyi aşmaz.
- Aynı sınıfta aynı modülü kullanan başka gruplar var: frekans, sync word ve imza anahtarı grup başına ayarlanır.
- CLAUDE.md kuralları geçerli: kod kısa, ek paket en az, sayılar ayarda, arayüz Türkçe, satır içi script/stil yok.

## Yaklaşımlar

**Forum nerede çalışır**

| Yol | Değerlendirme |
|---|---|
| STM32'de C ile yeniden yazım | Bütün forumun baştan yazılması; bir haftaya sığmaz, mevcut kod çöpe gider. |
| **Bilgisayarda Django, STM32 + LoRa telsiz modem (seçildi)** | Mevcut forum aynen kalır; yalnızca eşitleme katmanı yazılır. |

**Eşitleme yöntemi**

| Yol | Değerlendirme |
|---|---|
| Olay günlüğü: her eylem için "kaydet" + "uygula" kodu | Açık ve okunur, ama yaklaşık 20 eylem türü tek tek yazılıp sınanır; biri unutulursa forumlar sessizce ayrışır. Süreye sığmaz. |
| Django sinyalleriyle satır kopyalama | Kısa, ama koddaki `.update()` çağrıları sinyal üretmez (sonuçlandırma, puan, iptal); ▲/▼ puanı ezilir. |
| **Veritabanı tetikleyicisiyle satır günlüğü (seçildi)** | Satır hangi yoldan değişirse değişsin yakalanır; mevcut uygulamalara neredeyse dokunulmaz; forumun tamamı eşitlenir. Bedeli: SQLite'a özgü ve aynı satırın iki tarafta aynı anda değişmesi için bir kural gerekir. |

**Oylama sonucu**

| Yol | Değerlendirme |
|---|---|
| İki taraf da kendi hesaplar | Son saniyede verilen ve henüz ulaşmamış bir oy yüzünden iki forum farklı sonuç gösterebilir. |
| **Hakem düğüm (seçildi)** | Yalnızca 1. düğüm sonuçlandırır, karşı tarafın bitişe kadarki bütün oylarını aldıktan sonra. Bağlantı yoksa sonuç bekler. |

**Modül:** E32 (UART, hazır paketleme) daha kolaydı; ekip Ra-02 (SPI) aldığı için o kullanılıyor. Fark yalnızca
firmware'de: telsizi STM32 sürer.

## Genel resim

```
Bilgisayar 1 (düğüm 1, hakem)                         Bilgisayar 2 (düğüm 2)
 tarayıcı -> runserver --+                        +-- runserver <- tarayıcı
                         +- db.sqlite3      db.sqlite3 -+
 sync_run ---------------+  (tetikleyiciler)            +--------------- sync_run
    | USB (seri port)                                          USB |
 Black Pill + Ra-02   ~~~~~~~~~  LoRa 434,5 MHz  ~~~~~~~~~   Black Pill + Ra-02
```

Her bilgisayarda iki süreç çalışır: `runserver` (forum) ve `sync_run` (eşitleyici). İkisi aynı SQLite dosyasını kullanır.

## 1. İnternetsiz mod ve demo ayarları

- `.env`'de `OFFLINE=1` -> `settings.OFFLINE`.
  - Kayıt: CAPTCHA denetimi atlanır, şablonda Turnstile kutusu ve Cloudflare script'i çıkmaz. Hesap doğrudan
    açık (`is_active=True`) oluşur, doğrulama e-postası gitmez, üye giriş yapmış olarak ana sayfaya döner.
  - Kayıttaki "süresi dolan doğrulanmamış hesapları sil" temizliği `OFFLINE` ya da eşitleme açıkken atlanır.
    Gerekçe: karşıdan gelen üyelerde `last_login` yerelde boş kalır; moderasyonla kapatılmış bir hesap bu sorguya
    takılır, silme `ModAction`'ın `PROTECT`'ine çarpar ve kayıt sayfası 500 verir.
  - Şifre sıfırlama e-postası bugünkü gibi konsola yazılır; dokunulmaz.
- `FORUM_OVERRIDES` (JSON): `FORUM` sözlüğünün üzerine yazılır, kural sayıları yine tek yerde kalır. Demo örneği:
  `{"QUORUM_MIN": 2, "MIN_ACCOUNT_AGE_DAYS": 0, "PROPOSAL_VOTING_DAYS": 0.003, "REQUEST_DISCUSSION_DAYS": 0.002, "REQUEST_VOTING_DAYS": 0.003, "PANEL_CACHE_SECONDS": 0}`.
  Gün değerleri kesirli olabilir (0.003 gün yaklaşık 4 dakika). Kesirli günün metinlerde garip görünmesi kabul.
- `SQLITE_NAME` (varsayılan `db.sqlite3`): aynı bilgisayarda iki düğümü denemek için ayrı veritabanı dosyası.
- `SYNC_NODE` doluyken SQLite seçenekleri: `timeout` 20 sn, `transaction_mode` IMMEDIATE, WAL günlüğü. Gerekçe:
  aynı dosyaya iki süreç yazıyor; "database is locked" hatası çıkmasın.

## 2. `sync` uygulaması

Yeni Django uygulaması; her zaman kurulu, yalnızca `SYNC['NODE']` doluyken etkin. Ayarlar `config/settings.py`'de
`SYNC` sözlüğünde: `NODE` (0 = kapalı, 1 = hakem, 2), `PORT`, `KEY`, `PK_BASE` (1 000 000 000) ve bu belgedeki bütün
süre/boyut sayıları. `.env`: `SYNC_NODE`, `SYNC_PORT`, `SYNC_KEY`.

### Eşitlenen tablolar

`accounts`, `topics`, `voting`, `comments`, `moderation` uygulamalarının bütün somut modelleri (15 tablo: üye, konu,
konu oyu, yedi öneri tipi, karar oyu, yorum, yorum oyu, moderasyon kaydı, şikayet). Liste elle yazılmaz,
`apps.get_app_config(...).get_models()` ile bulunur. Otomatik oluşan çoktan-çoğa tablolar, oturumlar, önbellek ve
admin kaydı eşitlenmez.

**Yerelde kalan sütunlar** (telsizden gitmez; karşıda satır ilk kez oluşurken yazılacak değer):

| Tablo | Sütun | Karşıdaki değer |
|---|---|---|
| `accounts_user` | `password` | `!` (kullanılamaz şifre) |
| | `last_login` | boş |
| | `email` | `<pk>@uzak.invalid` (benzersiz kalsın) |
| | `first_name`, `last_name` | boş metin |
| | `is_staff`, `is_superuser` | 0 (yetki telsizden gelmez) |
| `comments_comment`, `topics_topic` | `score` | 0, sonra oylardan hesaplanır |

### Değişikliği yakalama (tetikleyici)

Her eşitlenen tabloya üç SQLite tetikleyicisi (ekleme, güncelleme, silme) konur. Tetikleyici `sync_change` tablosuna
bir satır yazar:

- `id`: sıra numarası (otomatik artan). Düğümün giden akışı bu numarayla sıralıdır.
- `tbl`, `row`: tablo adı ve satırın pk'si.
- `data`: satırın **o anki** hali, `json_array(NEW.sütun, ...)` ile (yerelde kalan sütunlar hariç); silmede boş.
  Anlık görüntü saklandığı için karşı taraf değişiklikleri tam oluş sırasıyla ve o anki haliyle uygular; yabancı
  anahtar sırası hiç bozulmaz.
- `seen`: kayıt anında karşıdan uygulanmış son sıra numarası (çakışma kuralı bunu kullanır).
- `at`: kayıt zamanı.

Koşullar: tetikleyici, eşitleyici karşıdan gelen satırı uygularken çalışmaz (`sync_state.applying` bayrağı; yankı
olmasın). Güncelleme tetikleyicisi yalnızca eşitlenen sütunlardan biri değiştiyse çalışır (`OLD.x IS NOT NEW.x`):
puan ya da `last_login` değişikliği kayıt üretmez.

Tetikleyicileri `python manage.py sync_init` kurar: yeniden çalıştırılabilir, günlüğe ve duruma dokunmaz, SQLite
değilse hata verir. Günlüğü ve durumu sıfırlamak ayrı ve açık bir seçenektir (`sync_init --reset`, yalnızca ilk kurulumda).

Django, SQLite'ta bir tabloyu değiştiren migration'da tabloyu yeniden kurar ve tetikleyicilerini düşürür. Bu yüzden
eşitleme açıkken tetikleyiciler her `migrate`'ten sonra kendiliğinden yeniden kurulur (`post_migrate`); eksikse Django
sistem denetimi (`check`, `runserver` açılışı) uyarır ve `sync_run` açık bir mesajla durur.

### Numara aralıkları

Aynı içerik iki tarafta aynı pk'ye sahip olmalı (adresler ve `object_id` alanları tutsun). 1. düğüm 1'den,
2. düğüm `PK_BASE`'den numara verir. Atama uygulama düzeyinde yapılır: eşitlenen modellerde `pre_save` sinyali, pk'si
boş yeni nesneye kendi aralığından sıradaki numarayı yazar.

- SQLite'ın kendi sayacı kullanılamaz: 1. düğüme karşıdan gelen büyük numaralı satır sayacı yukarı çeker.
- Atama aynı düğümdeki eşzamanlı iki kayda aynı numarayı vermemelidir. Django, pk'si elle verilmiş yeni nesnede önce
  UPDATE dener: aynı numara iki kez verilirse ikinci kayıt birincinin satırını sessizce ezer. Bu yüzden numara,
  yazma kilidi alan bir sayaç satırından alınır ("en büyük + 1" sorgusu yetmez).

### Karşıdan geleni uygulama

Her mesaj bir değişikliktir ve tek bir veritabanı işleminde uygulanır:

1. İlk iş `applying = 1` yazılır (yazma kilidi de böyle alınır; bayrak aynı işlemde 0'a döner, başka bağlantı 1'i görmez).
2. **Çakışma kuralı (yalnızca 1. düğümde):** aynı `(tbl, row)` için kendi günlüğünde `id > mesajın seen değeri` olan
   bir kayıt varsa gelen değişiklik atlanır. Anlamı: iki taraf aynı satırı birbirini görmeden değiştirdi, hakemin
   sürümü geçerli. 2. düğüm gelen her değişikliği uygular; hakemin sürümü ona zaten ulaşır.
3. Ham SQL ile yazılır: `INSERT ... ON CONFLICT(id) DO UPDATE` (yerelde kalan sütunlar yalnızca eklemede yazılır,
   güncellemede dokunulmaz) ya da `DELETE`. Django modelleri kullanılmaz: `auto_now` alanları ve `ModAction`'ın
   değişmezlik denetimi araya girmesin.
4. Değişen tablo bir ▲/▼ oy tablosuysa hedefin `score` alanı o hedefin oylarının toplamından yeniden hesaplanır.
   Silmede hedef, satır silinmeden önce okunur.
5. `sync_state.applied` bu mesajın sıra numarasına çekilir, `applying = 0`.
6. İşlemden sonra önbellek temizlenir (ana sayfa paneli güncellensin).

**Takma ad çakışması:** aynı takma ad iki tarafta aynı anda alınmışsa gelen üye atlanmaz (atlanırsa yabancı anahtar
yüzünden o üyenin sonraki bütün yorum ve oyları da reddedilirdi); takma adının sonuna `-<pk>` eklenerek yazılır. Kural
o üyenin satırı her geldiğinde yeniden uygulanır (ad, başka pk'li bir yerel üyede varsa eklenir). Her taraf kendi
üyesini asıl adıyla, karşıdakini ekli adla görür; durum sayfası bunu uyarı olarak gösterir.

**Uygulanamayan mesaj:** herhangi bir bütünlük hatası (`IntegrityError`; yabancı anahtar hatası SQLite'ta işlem
kapanırken çıkar) o mesajın işlemini geri alır; ayrı bir işlemde `applied` ilerletilir ve durum sayfasına
"uygulanamadı" diye yazılır. Akış hiçbir hatada durmaz.

### Oylama sonucu: hakem kuralı

Mevcut uygulamalarda yalnızca `voting/models.py`'de iki küçük değişiklik yapılır:

1. `BaseProposal.finalize()`'ın ilk satırına bir kapı: `sync.gate.may_finalize(self)` (`sync/gate.py` hiçbir modeli
   modül düzeyinde import etmez).
2. `BaseProposal.set_hidden()` yalnızca oylaması hâlâ süren öneriyi iptal eder (`voting_ends_at > şimdi`). Bugün önce
   `finalize()` çağrıldığı için davranış değişmez; kapı kapalıyken ise süresi dolmuş ama henüz sonuçlanmamış öneri
   gizlenince iptal olur ve hakem onu bir daha sonuçlandıramazdı.

Kapının kuralı:

- Eşitleme kapalıysa her zaman doğru: bugünkü davranış.
- 2. düğümde her zaman yanlış: sonuçlandırmaz ve uygulamaz; sonuç 1. düğümden satır olarak gelir.
- 1. düğümde: öneri hâlâ oylamadaysa `sync_state.synced_until >= voting_ends_at + pay` olmalı. `synced_until`, karşı
  düğümün **kendi saatiyle** "bu ana kadarki bütün değişikliklerim sende" dediği andır (bkz. durum paketi). Karşı taraf
  oyları kendi saatine göre kabul ettiği için iki bilgisayarın saat farkı sonucu bozmaz. Ara durumdaki (kabul edilmiş,
  uygulanmamış) öneri 1. düğümde beklemeden uygulanır.

1. düğümün `sync_run` süreci süresi dolan önerileri belirli aralıkla sonuçlandırır (`finalize_proposals` mantığı);
sonuç sayfa ziyaretini beklemez. Öneri sayfasında, süresi dolmuş ama henüz sonuçlanmamış öneride "Oylama bitti; sonuç
iki forum eşitlenince açıklanacak" yazar.

## 3. Hat protokolü (bilgisayardan bilgisayara)

Taşıma katmanı, `gönder(paket)` / `al()` sunan bir "hat" nesnesi üzerinde çalışır; gerçek seri port, sahte hat ve
testteki bellek içi kayıplı hat aynı arayüzü sunar.

**Mesaj:** bir `sync_change` satırı. Gövde: `[tablo sırası, row, seen, data]` JSON'u, zlib ile sıkıştırılmış.
Tablo sırası, eşitlenen tabloların ada göre sıralı listesindeki yeridir.

**Paketler** (her biri en fazla yaklaşık 240 bayt; hepsinin sonunda 4 baytlık HMAC-SHA256 etiketi, anahtar `SYNC_KEY`;
etiketi tutmayan paket atılır, böylece başka grupların ve yabancıların paketleri elenir):

| Tür | İçerik | Amaç |
|---|---|---|
| Veri | sıra no, parça no, parça sayısı, parça | Mesajın bir parçası (parça en fazla `CHUNK` bayt). |
| Onay | sıra no, parça no | O parça alındı. Son parçanın onayı, mesajın uygulandığı (ya da bilerek atlandığı) anlamına gelir. |
| Durum | saat, son sıra no, karşıdan uygulanan son sıra no, şema özeti | Bağlantı canlılığı, toplu onay, hakem kuralı, uyumluluk. |

**Gönderme:** dur ve bekle. Aynı anda tek mesaj, parça parça; her parçadan sonra onay beklenir, gelmezse rastgele
gecikmeyle yeniden gönderilir. Art arda başarısızlıkta bağlantı "yok" sayılır, daha seyrek denenmeye devam edilir.
Hiçbir mesaj atılmaz.

**Alma:** beklenen parça gelirse saklanır ve onaylanır; daha önce alınmış parça ya da uygulanmış mesaj yeniden
gelirse yalnızca onaylanır (kaybolan onay böyle telafi edilir). Mesajlar artan sıra numarasıyla gelir; numaralarda
boşluk olabilir.

**Yarı çift yönlülük:** onay hemen gönderilir; başka paket göndermeden önce son duyulan paketten sonra kısa bir süre
beklenir. İki düğümün zaman aşımı farklıdır ki aynı anda konuşup sürekli çarpışmasınlar.

**Yayın süresi bütçesi:** eşitleyici gönderdiği her paketin havada kalma süresini (paket boyutu ve telsiz
ayarlarından) toplar. Son bir saatteki toplam `AIRTIME_PERCENT` (10) sınırına gelince onay dışındaki paketleri
bekletir. Olağan kullanım sınırın çok altındadır: en uzun yorum yaklaşık 15 saniye yayın eder, bütçe saatte 360 saniyedir.

**Durum paketi:** boştayken belirli aralıkla gönderilir. Alan taraf: (a) `heard_at`'i günceller (arayüzdeki "bağlı"),
(b) `peer_applied`'ı ilerletir, (c) şema özeti (tablo/sütun listesi + ContentType kimlikleri) kendisininkiyle
tutmuyorsa hiçbir mesajı uygulamaz ve durum sayfasında "veritabanları uyumsuz" der, (d) karşının bildirdiği son sıra
numarasına kadar her şeyi uygulamışsa `synced_until = bildirilen saat` yapar (yalnızca ileri gider), (e) saat farkını
kaydeder.

## 4. Modem: Black Pill + Ra-02

Firmware yalnızca köprüdür; bütün akıl bilgisayardadır.

- Araç: VS Code + PlatformIO, Arduino çatısı (STM32duino), `sandeepmistry/LoRa` kütüphanesi. Kaynak `firmware/`
  klasöründe (`platformio.ini`, `src/main.cpp`). Gerekçe: PlatformIO komut satırından derlenip yüklenir, Opus kendisi
  çalıştırabilir.
- USB: sanal seri port (CDC). Bilgisayar ile modem arası SLIP çerçeveleme.
  - Bilgisayar -> modem: bir çerçeve = havaya verilecek bir paket.
  - Modem -> bilgisayar: bir çerçeve = `[RSSI][SNR]` + alınan paket.
- Telsiz ayarları derleme bayrağı olarak `platformio.ini`'de: frekans 434,5 MHz, SF7, 125 kHz, kodlama 4/5, CRC açık,
  güç 10 dBm, sync word. Grup başına frekans ve sync word değiştirilebilir.
- Kart üstü LED (PC13) her gönderme/almada yanıp söner.
- Bağlantı (Ra-02 -> Black Pill): 3.3V -> 3V3, GND -> G, NSS -> A4, SCK -> A5, MISO -> A6, MOSI -> A7, RST -> B0,
  DIO0 -> B1.
- Uyarılar: Ra-02 yalnızca 3,3 V ile çalışır (5 V'a bağlanmaz); anten takılmadan çalıştırılmaz; pin aralığı 2,0 mm
  olduğundan adaptör kartı ya da lehim gerekir.

**Sahte hat:** `python manage.py sync_air` küçük bir TCP aktarıcıdır: iki eşitleyici bağlanır, çerçeveleri birbirine
iletir, isteğe göre kayıp ve gecikme ekler. Eşitleyici için fark yoktur: `SYNC_PORT=socket://127.0.0.1:9100`.
Seri port ve `socket://` adresi için `pyserial` eklenir (`requirements.txt`).

Donanım teslime yetişmezse aynı sistem iki bilgisayar arasında ağ üzerinden sahte hatla gösterilebilir.

## 5. Arayüz

- Üst çubukta rozet (yalnızca eşitleme açıkken): "LoRa: bağlı" ya da "LoRa: bağlantı yok", yanında "bekleyen N".
  Rozet `/sync/` sayfasına gider.
- `/sync/` durum sayfası: düğüm numarası ve hakem olup olmadığı, bağlantı, son duyulma, sinyal (RSSI/SNR), saat farkı
  uyarısı, son bir saatte kullanılan yayın süresi, bekleyen mesaj sayısı, sonuç bekleyen öneriler, son giden ve
  gelen kayıtlar (tür, satır no, zaman, yön, atlandıysa nedeni). İçerik metni ve kimin ne oy verdiği görünmez (kural 6).
- `/sync/status.json`: `site.js` rozet varken belirli aralıkla sorar, rozeti günceller; sayfa açıldıktan sonra karşıdan
  yeni kayıt geldiyse "Karşı taraftan yeni içerik geldi · Yenile" şeridi çıkar.
- Görünüm `site.css`'teki mevcut sınıflarla; satır içi stil/script yok.

## 6. Kurulum ve demo

`LORA.md` (Türkçe, PowerShell komutlarıyla): parça listesi, kablolama, firmware yükleme, `.env` örnekleri, ilk kurulum,
çalıştırma, 5 dakikalık demo senaryosu, sorun giderme.

İlk kurulumun özü: veritabanı 1. bilgisayarda hazırlanır (migrate, kurucu hesap, önbellek tablosu, ilk konular,
`sync_init`), iki süreç kapalıyken `db.sqlite3` dosyası 2. bilgisayara kopyalanır. Böylece iki taraf aynı başlangıç
durumundan, aynı ContentType kimlikleriyle başlar. Sonra yalnızca `.env`'deki `SYNC_NODE` ve `SYNC_PORT` farklıdır.
İki bilgisayarın saati elle birbirine yakın ayarlanır.

## Test

- Mevcut testler `SYNC_NODE` boşken değişmeden geçer (SQLite ve PostgreSQL).
- `sync/tests.py` (yalnızca SQLite): tetikleyici anlık görüntüyü yazar; yerel sütun değişikliği kayıt üretmez;
  ekleme/güncelleme/silme karşıda aynen oluşur; puan yeniden hesaplanır; çakışma kuralı; takma ad çakışması;
  uygulanamayan mesajda akışın sürmesi; numara ataması; hakem kapısı (süresi dolmuş öneriyi gizleme dahil);
  migration'dan sonra tetikleyicilerin geri gelmesi; kayıplı bellek içi hatta taşıma (kayıp, yineleme, çarpışma);
  yayın süresi bütçesi; internetsiz kayıt.
- İki düğümü tek süreçte sınayan en az bir uçtan uca test: iki ayrı SQLite veritabanı, yakala -> paketle -> uygula;
  sonunda eşitlenen tablolar iki tarafta satır satır aynı (yerelde kalan sütunlar hariç).

## Aşamalar

Her aşama Opus ile ayrı sohbet; sonunda testler geçer, CLAUDE.md güncellenir, commit kullanıcıya sorulur.

| | Aşama | Donanım |
|---|---|---|
| A | İnternetsiz mod ve demo ayarları | gerekmez |
| B | `sync` çekirdeği: tetikleyiciler, numara aralıkları, uygulama, çakışma kuralı | gerekmez |
| C | Taşıma protokolü, `sync_run`, `sync_air`; aynı bilgisayarda iki forum eşitlenir | gerekmez |
| D | Hakem kuralı ve arayüz (rozet, durum sayfası, "yenile" uyarısı) | gerekmez |
| E | Firmware ve gerçek seri port | gerekir |
| F | `LORA.md`, iki bilgisayarda kurulum, demo provası | gerekir |

## Bilinen sınırlar

- Telsiz trafiği şifresiz: takma adlar, yorumlar ve oylar havada okunabilir. Paketler imzalı olduğu için başkası sahte
  kayıt gönderemez.
- Aynı satır iki tarafta aynı anda değişirse 2. düğümün değişikliği kaybolur (satır düzeyinde; ör. yazar yorumunu
  düzenlerken öbür taraftaki yönetici aynı yorumu gizlerse).
- Aynı hesapla iki bilgisayardan işlem yapılmamalı (kurucu hesap iki tarafta da var): aynı öneriye iki taraftan verilen
  oy benzersizlik hatasına düşer.
- Aynı takma ad iki tarafta aynı anda alınırsa iki forum o üyeyi farklı adla gösterir (karşıdaki `-<pk>` ekli).
- Bağlantı yokken oylama sonuçlanmaz.
- Üye yalnızca kayıt olduğu bilgisayardan giriş yapabilir.

## Yapana bırakılanlar

Paketlerin bayt düzeni; zaman aşımı ve aralıkların değerleri (hepsi `SYNC` sözlüğünde); numara sayacının biçimi; gelen
ve giden kayıtların günlük modeli; iki veritabanlı test düzeneği; rozetin ve durum sayfasının görünümü; SLIP
gerçeklemesi; PlatformIO'nun USB bayrakları ve yükleme yöntemi (DFU ya da ST-Link); `sync` içindeki dosya bölünmesi.
