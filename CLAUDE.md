# Proje: Oylamayla yönetilen forum (web sitesi)

## Amaç
- Kararları çoğunluk verir, azınlıkta kalan görüş elenir.
- Konu/alt konu açma, düzenleme, silme, kapatma: hepsi oylamayla.
- Konulardan doğan istekler, tartışma süresinden sonra oylanır.
- Kapatılan konular silinmez. Yorumlarda upvote/downvote var.

## Roller
- A: normal üye, oy ağırlığı 1
- B: bilirkişi, oy ağırlığı 10
- Yönetici: yalnızca moderasyon (troller, aşırı içerik, sahte hesaplar), başka şeye dokunmaz
- Kayıt: ad, soyad, takma ad, e-posta, şifre

## Kurallar
Sayılar koda gömülmez, ayar olarak tutulur.

1. Sahte hesap: e-posta doğrulaması + CAPTCHA. Oy hakkı için hesap en az 7 günlük. Açıkça sahte hesabı Yönetici kapatır.
2. B statüsü: gerekçeli başvuru + topluluk oylaması, 2/3 evet gerekir, bu oylamada herkesin oyu 1. Aynı yolla geri alınabilir. Ağırlık yalnızca karar oylamalarında; yorum oyları herkes için 1.
3. Yeter sayı: kişi sayısıyla ölçülür. Son 30 günde aktif üyelerin %10'u, en az 5 kişi.
4. Kabul: ağırlıklı oyların yarısından fazlası evet. Eşitlikte ret, mevcut durum korunur.
5. Süreler: açma/düzenleme/kapatma/silme önerileri doğrudan 2 gün oylanır, tartışma oylama sırasında öneri sayfasında yapılır. İstekler: 3 gün tartışma + 3 gün oylama.
6. Gizlilik: kim ne oy verdi gizli. Oylama sürerken yalnızca katılım sayısı görünür, sonuç bitince açıklanır. Bitene kadar oy değiştirilebilir.
7. Kapatma/silme: kapatılan konu görünür kalır, yeni yorum/öneri almaz. Silinen içerik veritabanında kalır, gizlenir. İkisi de oylamayla geri alınabilir.
8. Öneri sınırı: kişi başı en fazla 3 açık öneri. Reddedilen öneri 30 gün yeniden açılamaz.
9. Açılış: ilk ana konuları kurucu açar, sonrası tamamen oylamayla.

## Ana sayfa
- Kenarda aktif oylamalar paneli
- Ortada konu / alt konu sekmeleri
- Sıralama: en çok oy, en yeni, en popüler (tanımı 7. adımda)

## Teknoloji
Python 3.14 + Django 6.1, SQLite (geliştirme) / PostgreSQL (yayın), ileride PWA

## Ortam
- Windows, VS Code, PowerShell. Kod: Claude Code (Claude masaüstü uygulaması, Code sekmesi, Local).
- Proje klasörü: `C:\projeler\forum`
- Sanal ortam: `.venv`, etkinleştirme: `.venv\Scripts\Activate.ps1`
- Django ayar paketi: `config` (`config/settings.py`, `config/urls.py`)
- Geliştirme sunucusu: `python manage.py runserver` (http://127.0.0.1:8000)
- Paket kurma: `python -m pip install <paket>`, ardından
  `python -m pip freeze | Out-File -Encoding utf8 requirements.txt`
  (`>` kullanılmaz: Windows PowerShell dosyayı UTF-16 yazar, Git ikili dosya sanar.)
- Git: GitHub'da private `forum` deposu, dal `main`.
  `.gitignore`: `.venv/`, `__pycache__/`, `db.sqlite3`, `.env`, `.vscode/`

## Kararlar ve notlar
- Kod adları İngilizce, arayüz Türkçe.
- Kural sayıları `config/settings.py` içindeki `FORUM` sözlüğünde. Yeni bir kural sayısı gerekince oraya eklenir.
- Kullanıcı modeli `accounts.User` (`AbstractUser`'dan türer). Takma ad = `username`. Ad, soyad ve e-posta zorunlu. E-posta küçük harfe çevrilir ve benzersizdir; takma ad büyük/küçük harf farkı gözetmeden benzersizdir. Rol `role` alanında (A/B), Yönetici = `is_staff`. `vote_weight` ve `can_vote` (aktif + hesap yaşı) modelde.
- E-posta doğrulama: hesap `is_active=False` açılır. Django'nun `default_token_generator`'ıyla tek kullanımlık bağlantı gider, süresi `PASSWORD_RESET_TIMEOUT` (3 gün). Süresi dolan doğrulanmamış hesaplar yeni bir kayıt denemesinde silinir.
- CAPTCHA: Cloudflare Turnstile, ek paket yok (`urllib`). Şimdilik test anahtarları var; gerçekleri 9. adımda `.env`'e. Cloudflare'e giden veri KVKK metninde belirtilecek.
- E-posta ayarı Django 6.1'in `MAILERS` ayarıyla yapılıyor, şimdilik konsola yazıyor. `EMAIL_BACKEND` gibi eski `EMAIL_*` ayarları artık kullanılmıyor, SMTP 9. adımda `MAILERS`'a eklenecek.
- Şifre sıfırlama/değiştirme sayfaları şimdilik admin şablonlarını kullanıyor. Arayüz yapılırken kendi şablonlarımız yazılacak.
- Konular: `topics` uygulaması, tek model `Topic`. Alt konu = `parent`'ı dolu konu (ters adı `children`). İki seviye var: `parent`'taki `limit_choices_to={"parent": None}` hem admin listesini süzer hem `full_clean()`'de denetler. Üst konu sonradan değişmez, admin'de yalnızca eklerken seçilir.
- `is_closed` ve `is_deleted` ayrı alanlar. Ana konudan miras hesaplanır, alt konulara yazılmaz. Görünürlüğün tek yeri `Topic.objects.visible()`, tek nesnedeki karşılığı `is_visible` (8. adımdaki moderasyon gizlemesi ikisine birlikte eklenecek). `is_open` = görünür ve kapalı değil (`is_locked` değil); öneri ve yorum buna bakar (kural 7). `objects` hepsini getirir.
- Gerçek silme yok (kural 7): `parent` için `PROTECT`, admin'de silme kapalı. `author` `SET_NULL` ve formlarda düzenlenemez (`editable=False`); admin'de ekleyen kullanıcı olur.
- Sayfalar: konu sayfasında öneri bağlantıları (konu açıksa düzenleme/kapatma/silme/istek, ana konuda alt konu; kapalıysa yeniden açma). Ana sayfa (7. adıma kadar geçici) görünür ana konuları, yeni ana konu önerisi, açık öneriler (`proposals/`) ve arşiv bağlantılarını gösterir. `topics/<pk>/` gizli konuda 404 döner; kapalı ve silinmiş konular `topics/archive/`'de (silinmişin yalnızca başlığı ve tarihi), geri alma önerisi oradan açılır. `base.html` `messages`'ı gösterir.
- Oylama: `voting` uygulaması, ortak alanlar `BaseProposal`'da (abstract), tip başına ayrı model (`TopicOpenProposal/EditProposal/CloseProposal/DeleteProposal/UndoProposal`, `ExpertProposal`, `RequestProposal`). `SLUG` ve `PROPOSALS` sözlüğü URL'deki tipten modeli bulur (`proposals/<tip>/<pk>/`). Tek `Vote` modeli `GenericForeignKey` ile hepsine bağlanır; `Vote.cast()` ile verilir/değiştirilir (upsert), ağırlık oy anında sabitlenir.
- `BaseProposal.finalize()` öneri sayfası ziyaretinde ve `python manage.py finalize_proposals` komutuyla (9. adımda Windows Görev Zamanlayıcısı'na eklenecek) çağrılır. Kural 3'ü (yeter sayı: `required_quorum()`) ve kural 4'ü (`tally()` ile ağırlıklı çoğunluk, eşitlikte ret) hesaplar, o anki yeter sayıyı `quorum` alanına yazar. Koşullu UPDATE sayesinde iki çağrı aynı anda çalışsa da öneri bir kez sonuçlanır ve uygulanır. Kabul edilen öneri hedefin güncel durumu denetlenip uygulanır (`apply()`); uygun değilse `accepted` durumunda kalır ve her çağrıda yeniden dener.
- Öneri denetimleri `BaseProposal.clean()`'de (ModelForm ve admin kendiliğinden çağırır): oy hakkı (`can_vote`), kişi başı açık öneri sınırı (`open_proposal_count()`), tipe göre `check_target()` (kapalı konu öneri almaz; geri alma yalnızca kapalı/silinmiş konuya; B statüsü başvurusu yalnızca kendi adına), `is_duplicate()` (aynı tip+hedef+içerik oylamada ya da reddedilmesinin, yani `voting_ends_at`'in üzerinden bekleme süresi geçmemiş). Formun alanları `FORM_FIELDS`, URL'deki konunun yazıldığı alan `TARGET`, başlangıç değerleri `prefill()`; hepsi modelde.
- Yorumlar: `comments` uygulaması. Yorum alabilen modeller (`Topic`, `BaseProposal`) soyut `Commentable`'dan türer (`GenericRelation` + `is_open`); `Comment` hedefe `GenericForeignKey` ile bağlanır. `comments`, `topics` ve `voting`'i import etmez. Tek seviye yanıt: yanıta yanıt ana yoruma bağlanır. İçerik düz metin (`urlize` + `linebreaksbr`), en fazla `COMMENT_MAX_LENGTH`.
- Yorum hedef açıkken yazılır: konuda `Topic.is_open`, öneride oylama bitene kadar (istekte tartışma + oylama; istenirse `RequestProposal.is_open` ile yalnızca tartışmaya daraltılır). Hedef kapanınca yeni yorum, yanıt, düzenleme ve yorum oyu durur; silme serbest. Düzenleme ve silme yalnızca yazarın ("düzenlendi" = `edited_at`); silme yumuşak ve geri alınmaz, yerinde "Bu yorum silindi" yazar, yanıtlar kalır. Yorum için hesap yaşı şartı yok; öneri açmak ve her türlü oy için `can_vote` gerekir.
- Yorum oyu: ayrı `CommentVote` modeli (`Vote` değil), ▲ +1 / ▼ −1, ağırlık herkes için 1. Kendi, silinmiş ya da kapalı hedefteki yoruma oy verilmez; aynı tuşa ikinci basış oyu geri alır. `Comment.score` tabloda tutulur, yalnızca `CommentVote.cast()` `F()` ile değiştirir (yorum satırı kilitlenir). Puan herkese açık, kimin ne verdiği gizli: `CommentVote` admin'de yok, `CommentAdmin` salt okunur.
- Yorum bölümü `{% load comments %}{% comment_section hedef %}` inclusion tag'i, yorum sayısından bağımsız 2 sorgu. Ana yorumlar puana göre (eşitse eski önde) ya da `?sort=new`; yanıtlar kronolojik. JavaScript yok: her işlem POST formu, ardından `#c<pk>` çapasına dönülür (sayfa yenilemeden oy 9. adımda).
- Aktif üye (kural 3): son `ACTIVE_DAYS` günde karar oyu veren, konu açan ya da yorum yazan. Yorum oyu sayılmaz, yeter sayıyı şişirmesin.
- Testler: `voting/tests.py`, `comments/tests.py`; `python manage.py test`. Test kullanıcıları şifresiz (`make_user`), giriş `force_login` ile.
- Açık: kabul edilip uygulanamayan öneri (ör. üst konusu kapanmış alt konu önerisi) süresiz bekliyor; bir son tarih ya da "uygulanamadı" durumu eklenmeli.
- Açık: B statüsü artık oylamayla değişiyor (`ExpertProposal`); admin'deki `role` alanı salt okunur yapılacak (şimdilik test için açık). Admin'de konular salt okunur olacak; kuruluş bitince admin'den konu eklemek de kapanacak (kural 9).
- 7. adım: çok yorumlu sayfalar için sayfalama (ana yorumlar üzerinden `Paginator`).
- 8. adım: yorum hız sınırı (spam) ve moderasyonla gizleme (`is_hidden`, sayfada "moderasyonla gizlendi"). Yanıt bildirimleri şimdilik kapsam dışı.
- 8. adım: Hesap kapatma `is_active=False` ile yapılırsa, hiç doğrulanmamış bir hesabın doğrulama bağlantısı onu yeniden açabilir. Kapatma için ayrı bir işaret düşünülecek.
- `SECRET_KEY` şu an geliştirme anahtarı (`django-insecure`). Yayından önce (9. adım) yenisi üretilip `.env` dosyasına taşınacak.

## Yol haritası
1. Kurallar ✓
2. Kurulum: Python, VS Code, Git/GitHub, boş Django projesi ✓
3. Kullanıcılar: roller, oy ağırlığı, kayıt/giriş ✓
4. Konular ve alt konular ✓
5. Oylama motoru: öneri → tartışma → oylama → sonuç, zamanlayıcı ✓
6. Yorumlar ve upvote/downvote ✓
7. Ana sayfa: panel, sekmeler, sıralama
8. Moderasyon: gizleme, engelleme, herkese açık moderasyon kaydı
9. Yayın: mobil uyum, PWA, sunucu, alan adı, kullanım şartları, KVKK

## Çalışma
- Adım adım, Türkçe, kısa açıklamalı (kullanıcı uzun anlatım istemiyor). Her adım yeni sohbette; adım bitince bu dosya güncellenir.
- Tasarım ve kavramlar claude.ai'deki Forum projesinde konuşulur, kod Claude Code'da yazılır.
- Kullanıcı: C, C++, Java ve Git/GitHub temel seviyede. Python'u Java'yla karşılaştırarak anlat.

## Claude Code için
- Türkçe yaz. Yeni bir Python/Django kavramı çıkınca kısaca Java'daki karşılığıyla açıkla.
- Kaynaklar sınırlı: kod kısa, zekice ve verimli olsun. Gereksiz soyutlama, tekrar ve ek paketten kaçın; Django'nun hazır araçlarını kullan. Kullanıcı öğrense de kodu sadeleştirme; zekice kısımları kodu şişirmeden, mesajda kısaca açıkla.
- Kod yazmadan önce kısa bir plan sun ve onay bekle. Değişiklikleri küçük parçalar hâlinde yap; her parçada neyi neden değiştirdiğini söyle.
- Komutları PowerShell için ver. Python komutlarını `.venv` etkinken çalıştır, pip'i `python -m pip` ile çağır.
- Kural sayılarını koda sabit yazma; ayarın nerede tutulacağı belli değilse sor.
- Yeni paket eklersen `requirements.txt` dosyasını güncelle.
- Commit ve push'u kullanıcıya sormadan yapma.

## Durum
1.–6. adım tamamlandı. Sıradaki: 7. adım (ana sayfa: aktif oylamalar paneli, konu/alt konu sekmeleri, sıralama); tasarımı claude.ai'de konuşulacak.
