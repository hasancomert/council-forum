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
- Ayarlar ortam değişkeninden; geliştirmede kökteki `.env` (`Copy-Item .env.example .env`, içinde `DEBUG=1` yeter).
  Önbellek tablosu bir kez: `python manage.py createcachetable`.
- Git: GitHub'da private `forum` deposu, dal `main`.
  `.gitignore`: `.venv/`, `__pycache__/`, `db.sqlite3`, `.env`, `.vscode/`, `staticfiles/`. `.gitattributes`: `deploy/` LF.
- Yayın: `DEPLOY.md` (Türkiye'de VPS, Ubuntu 26.04, Caddy + gunicorn + PostgreSQL + systemd), sunucu dosyaları `deploy/`.

## Kararlar ve notlar
- Kod adları İngilizce, arayüz Türkçe.
- Kural sayıları `config/settings.py` içindeki `FORUM` sözlüğünde. Yeni bir kural sayısı gerekince oraya eklenir.
- Kullanıcı modeli `accounts.User` (`AbstractUser`'dan türer). Takma ad = `username`. Ad, soyad ve e-posta zorunlu. E-posta küçük harfe çevrilir ve benzersizdir; takma ad büyük/küçük harf farkı gözetmeden benzersizdir. Rol `role` alanında (A/B). Yönetici = `is_moderator`: moderasyonu sitedeki sayfalardan yapar, admin'e girmez; admin kurucunun (`is_staff`/`is_superuser`). `vote_weight`, `is_banned` (`banned_until` geçmediyse; süre dolunca kendiliğinden kalkar), `can_post` (aktif + engelsiz: yorum) ve `can_vote` (`can_post` + hesap yaşı: her türlü oy, öneri, şikayet) modelde. `terms_accepted_at` kayıtta şart onayının anı (kurucuda boş).
- E-posta doğrulama: hesap `is_active=False` açılır. Django'nun `default_token_generator`'ıyla tek kullanımlık bağlantı gider, süresi `PASSWORD_RESET_TIMEOUT` (3 gün). Süresi dolan doğrulanmamış hesaplar yeni bir kayıt denemesinde silinir.
- CAPTCHA: Cloudflare Turnstile, ek paket yok (`urllib`). Anahtarlar `.env`'de; geliştirmede boşsa her zaman geçen test anahtarları.
- E-posta Django 6.1'in `MAILERS` ayarıyla: `EMAIL_HOST` varsa SMTP (587, STARTTLS), yoksa konsol. Eski `EMAIL_BACKEND`/`EMAIL_HOST_*` ayarları kullanılmaz.
- Şifre değiştirme/sıfırlama sayfaları kendi şablonlarımız (`templates/registration/`); sıfırlama e-postasının metni Django'nun.
- Hesabım (`accounts/`) ve hesap silme (`accounts/delete/`, şifreyle): `User.anonymize()` ad, soyad, e-posta, takma ad ve şifreyi siler, satır kalır (gerçek silme karar oylarını CASCADE'le siler, `ModAction` `PROTECT`). `deleted_at` dolunca `User.__str__` "silinmiş üye" döner, içerik tablolarına dokunulmaz. Süren oylamadaki oylar ve açık öneriler `withdraw_running()` ile geri çekilir; bitmiş oylamalar ve ▲/▼ puanları kalır. Yorum metinleri yalnızca üye kutuyu işaretlerse silinir (`is_deleted` + boş metin). Admin (`is_staff`) hesabı buradan silinmez; doğrulanmamış hesap temizliği silinmiş hesaba dokunmaz.
- Konular: `topics` uygulaması, tek model `Topic`. Alt konu = `parent`'ı dolu konu (ters adı `children`). İki seviye var: `parent`'taki `limit_choices_to={"parent": None}` hem admin listesini süzer hem `full_clean()`'de denetler. Üst konu sonradan değişmez, admin'de yalnızca eklerken seçilir.
- `is_closed`, `is_deleted` ve `is_hidden` (moderasyon) ayrı alanlar. Ana konudan miras hesaplanır, alt konulara yazılmaz. `Topic.objects.existing()` sayfası açılan konular (silinmemiş, üst konusu silinmemiş; tek nesnede `has_page`). `visible()` listelenen ve etkileşim alan konular: ayrıca gizli ve üst konusu gizli olmayan (tek nesnede `is_visible`); görünürlüğün tek yeri. `is_open` = görünür ve kapalı değil (`is_locked` değil); öneri, yorum ve oy buna bakar (kural 7). `objects` hepsini getirir.
- Gerçek silme yok (kural 7): `parent` için `PROTECT`, admin'de silme kapalı. `author` `SET_NULL` ve formlarda düzenlenemez (`editable=False`); admin'de ekleyen kullanıcı olur.
- Sayfalar: konu sayfasında ▲ puan ▼, öneri bağlantıları (konu açıksa düzenleme/kapatma/silme/istek, ana konuda alt konu; kapalıysa yeniden açma) ve ana konuda açık alt konular. `topics/<pk>/` gizli konuda 404 döner, kapalı konu açılır. Silinmiş konular `topics/archive/`'de ("Silinen konular", yalnızca başlık ve tarih), geri getirme önerisi oradan açılır. `base.html` `messages`'ı gösterir.
- Oylama: `voting` uygulaması, ortak alanlar `BaseProposal`'da (abstract), tip başına ayrı model (`TopicOpenProposal/EditProposal/CloseProposal/DeleteProposal/UndoProposal`, `ExpertProposal`, `RequestProposal`). `SLUG` ve `PROPOSALS` sözlüğü URL'deki tipten modeli bulur (`proposals/<tip>/<pk>/`). Tek `Vote` modeli `GenericForeignKey` ile hepsine bağlanır; `Vote.cast()` ile verilir/değiştirilir (upsert), ağırlık oy anında sabitlenir.
- `BaseProposal.finalize()` öneri sayfası ziyaretinde ve `python manage.py finalize_proposals` komutuyla (sunucuda 15 dakikada bir systemd timer: `deploy/forum-finalize.timer`) çağrılır. Kural 3'ü (yeter sayı: `required_quorum()`) ve kural 4'ü (`tally()` ile ağırlıklı çoğunluk, eşitlikte ret) hesaplar, o anki yeter sayıyı `quorum` alanına yazar. Koşullu UPDATE sayesinde iki çağrı aynı anda çalışsa da öneri bir kez sonuçlanır ve uygulanır. Kabul edilen öneri hedefin güncel durumu denetlenip uygulanır (`apply()`); uygun değilse `accepted` durumunda kalır ve her çağrıda yeniden dener.
- Öneri denetimleri `BaseProposal.clean()`'de (ModelForm ve admin kendiliğinden çağırır): oy hakkı (`can_vote`), kişi başı açık öneri sınırı (`open_proposal_count()`), tipe göre `check_target()` (kapalı konu öneri almaz; geri alma yalnızca kapalı/silinmiş konuya; B statüsü başvurusu yalnızca kendi adına), `is_duplicate()` (aynı tip+hedef+içerik oylamada ya da reddedilmesinin, yani `voting_ends_at`'in üzerinden bekleme süresi geçmemiş). Formun alanları `FORM_FIELDS`, URL'deki konunun yazıldığı alan `TARGET`, başlangıç değerleri `prefill()`; hepsi modelde.
- Yorumlar: `comments` uygulaması. Yorum alabilen modeller (`Topic`, `BaseProposal`) soyut `Commentable`'dan türer (`GenericRelation` + `is_open`); `Comment` hedefe `GenericForeignKey` ile bağlanır. `comments`, `topics` ve `voting`'i import etmez. Tek seviye yanıt: yanıta yanıt ana yoruma bağlanır. İçerik düz metin (`urlize` + `linebreaksbr`), en fazla `COMMENT_MAX_LENGTH`.
- Yorum hedef açıkken yazılır: konuda `Topic.is_open`, öneride oylama bitene kadar (istekte tartışma + oylama; istenirse `RequestProposal.is_open` ile yalnızca tartışmaya daraltılır). Hedef kapanınca ya da yorum gizlenince yeni yorum, yanıt, düzenleme ve yorum oyu durur; silme serbest. Düzenleme ve silme yalnızca yazarın ("düzenlendi" = `edited_at`); silme yumuşak ve geri alınmaz, yerinde "Bu yorum silindi" yazar, yanıtlar kalır. Yorum için `can_post` (engelsiz, hesap yaşı gerekmez) ve hız sınırı (`COMMENT_RATE`, silinenler de sayılır); öneri açmak, şikayet ve her türlü oy için `can_vote` gerekir.
- ▲/▼ oyları (yorum: `CommentVote`, konu: `TopicVote`; karar oyu `Vote` değil): +1 / −1, ağırlık herkes için 1, `can_vote` gerekir. Kendi yorumuna/konusuna, silinmiş ya da kapalı hedefe oy verilmez; aynı tuşa ikinci basış oyu geri alır. Ortak mantık soyut `UpDownVote`'ta (`comments/models.py`): alt sınıf hedef FK'nin adını `TARGET`'a yazar, hedef `score` alanını ve `can_be_voted_by(user)`'ı sağlar. `score` yalnızca `UpDownVote.cast()` ile `F()` üzerinden değişir (hedef satırı kilitlenir). `voted_at` (`auto_now`) yön değişince de güncellenir. Puan herkese açık, kimin ne verdiği gizli: iki oy modeli de admin'de yok, `CommentAdmin` salt okunur. Düğmeler `_vote.html` (`aria-pressed`, puan `<output>`); konu oyu yalnızca konu sayfasında, listelerde yalnızca puan. Görünüm ortak `comments.views.updown()`: `Accept: application/json` gelirse `{score, mine}` ya da 400 `{error}`, yoksa mesaj + yönlendirme.
- Yorum bölümü `{% load comments %}{% comment_section hedef %}` inclusion tag'i. Ana yorumlar veritabanında sıralanıp sayfalanır: puana göre (eşitse eski önde) ya da `?sort=new`. Yanıtlar kronolojik ve ana yorumlarıyla aynı sayfada. Yorum sayısından bağımsız 4 sorgu: sayımlar, sayfa, yanıtlar ve kullanıcının oyları. "Yorumlar (n)" sayımı Paginator'ın sayım sorgusuyla birleşik (`paginator.count` atanır). Her işlem POST formu; JS yalnızca ▲/▼'yi sayfa yenilemeden gönderir, JS kapalıysa formlar aynen çalışır.
- Geri dönüş: formlar bulunduğu sayfanın adresini gizli `next` alanında taşır (düzenlemede `?next=`). `config/utils.back()` yalnızca bu sitenin yolunu (`/…`) kabul eder, open redirect yok. Yeni ana yorum `?sort=new#c<pk>`'ya, yanıt/oy/düzenleme/silme `next#c<pk>`'ya döner.
- Ana sayfa sekmeleri (`TABS`, `topics/views.py`): Ana konular | Alt konular (tüm açık alt konular, "Üst › Alt") | Kapalı. Süzgeçler `is_locked`'ın sorgu karşılığı: üst konusu kapalı alt konu da "Kapalı"da (yorum, oy, öneri almaz). "Kapalı"da kendisi kapalı konunun satırında, oy hakkı olana "yeniden açmayı öner" çıkar. Silinmiş ve üst konusu silinmiş konular hiçbir sekmede yok (`visible()`). `?parent=<pk>` yalnızca o konunun alt konularını listeler (konu sayfasındaki "tüm alt konular" ve "kapalı alt konular" bağlantıları). Konu satırı `topics/_row.html`.
- Sıralama (`SORTS`, `topics/models.py`): en popüler (varsayılan), en çok oy (`score`), en yeni. Eşitlikte yeni önde. "Kapalı" sekmesinde en popüler yok, varsayılan en yeni. Adresteki `tab`/`sort` yalnızca sözlükte aranır, tanınmayan değer varsayılana döner.
- En popüler (`heat`, `TopicQuerySet.ranked()`): son `POPULAR_DAYS` günde `POPULAR_WEIGHTS` ile 3 × yorum + 1 × (yorum oyu + konu oyu). Oyun yönü önemsiz. Silinmiş yorum ve öneri oyları sayılmaz. Yalnızca konunun kendi etkinliği sayılır. Sayımlar `count_of()` alt sorgularıyla (satır başına `COUNT`, JOIN çoğaltması yok), ana sayfanın sorgu sayısı konu sayısından bağımsız.
- Sayfalama: `Paginator.get_page()` (geçersiz sayfa → ilk/son). Bağlantılar `_pages.html` ve `{% querystring %}` ile, diğer parametreler korunur. Konu listeleri `TOPICS_PER_PAGE`, yorumlar `COMMENTS_PER_PAGE` ana yorum. Konu sayfası ilk `TOPICS_PER_PAGE` açık alt konuyu gösterir, gerisi `?parent=` ile ana sayfada. `page` parametresi yalnızca yorumlara ait.
- Aktif oylamalar paneli: `{% load voting %}{% active_panel %}`, ana sayfa ve konu sayfasında `base.html`'nin `aside` bloğunda (CSS grid, dar ekranda içeriğin altında). Oylamada: bitişi yakın önce, en fazla `PANEL_VOTING`. Tartışmada: istekler, en fazla `PANEL_DISCUSSION`. Taşarsa "tümü (n)" → `proposals/`. Kaynak `active_proposals()` (açık öneriler sayfası da kullanır), evre bitişi `deadline`. Ortak kısım `PANEL_CACHE_SECONDS` saniye önbellekte (`DatabaseCache`: gunicorn'un bütün süreçleri aynı önbelleği görür, moderasyonun `cache.delete()`'i hepsine işler). Oy hakkı olan kullanıcının oy vermediği önerideki ● kişiye özel, her istekte tek sorgu.
- Aktif üye (kural 3): son `ACTIVE_DAYS` günde karar oyu veren, konu açan ya da yorum yazan. Yorum oyu sayılmaz, yeter sayıyı şişirmesin. Kapatılan hesap sayılmaz.
- Moderasyon: `moderation` uygulaması. Soyut `Hideable` (`is_hidden`, `OWNER` = sahibi olan alan, öneride `proposer`; `hidden_from(user)`, `set_hidden()`, `can_be_reported_by()`): `Comment`, `Topic`, `BaseProposal` türer; modellerde başka uygulamayı import etmez. Gizleme silmeden ayrı, veritabanından bir şey silinmez. Gizli içerik donar, sekme, panel, arşiv ve sayımlardan çıkar; metnini yalnızca sahibi ve yöneticiler görür, başkaları "moderasyonla gizlendi" görür. Gizli konu/öneri sayfası açılır. Gizli ana konunun alt konuları da listelerden çıkar ve donar. Gizli konunun adı başka yerlerde "gizlenmiş konu" (`Topic.__str__`); gizli konu öneri almaz, o konudaki süren öneriler sürer.
- İptal: süren öneri gizlenince (önce `finalize()`) ya da önereni kapatılınca `Status.CANCELLED`. `finalize()` atlar; açık öneri sayısına ve ret yasağına girmez (ikisi yalnızca VOTING/REJECTED'e bakar); ara sonucu açıklanmaz (kural 6). Gizleme kaldırılınca iptal kalır.
- Yönetici işlemleri (`moderator_required`): `mod/<ct>/<pk>/` gizle / gizlemeyi kaldır ya da şikayetleri gizlemeden kapat; `mod/user/<pk>/` engelle (`BAN_DAYS`) / engeli kaldır, hesabı kapat / yeniden aç. Gerekçe (trollük / aşırı içerik / sahte hesap, "diğer" yok) ve herkese açık not (`MOD_NOTE_MAX_LENGTH`) zorunlu. Kendine, başka yöneticiye ve süper kullanıcıya işlem yok. Geri alma yalnızca yöneticiyle, o da kayda düşer; oylamayla geri alma yok. Her işlem panel önbelleğini (`PANEL_CACHE_KEY`) temizler.
- Hesap kapatma yalnızca açık hesapta ve "sahte hesap" gerekçesiyle: `is_active=False`, süren oylamalardaki karar oyları (`withdraw_running()`) ve bütün ▲/▼ oyları (`UpDownVote.withdraw_all()`, puanlar tek UPDATE ile düzelir) silinir, süren önerileri iptal olur; bitmiş oylamalara dokunulmaz. Yeniden açma yalnızca moderasyonla kapatılan hesapta (son kapat/aç kaydı), silinenleri geri getirmez. Doğrulanmamış hesap zaten kapalıdır ve moderasyonla açılmaz: kapatılan hesabı doğrulama bağlantısının açması sorunu böylece yok.
- Kayıt: `ModAction` yalnızca eklenir (`save()`/`delete()` değişikliği reddeder; üyeler `PROTECT`). `mod/log/` herkese açık, sayfalı (`MOD_PER_PAGE`), işlem/gerekçe/kişiye (yönetici ya da üye) göre süzülür. İçeriğin metni tutulmaz, türü ve `r/<ct>/<pk>/` bağlantısı (Django'nun `shortcut` görünümü) görünür.
- Şikayet: `Report`, oy hakkı gerekir; kendi, gizli ya da silinmiş içerik şikayet edilmez; içerik başına bir şikayet, hız sınırı `REPORT_RATE`. İçerik kendiliğinden gizlenmez: `mod/` kuyruğu içerik başına toplar, en çok şikayet alan önce. Şikayet edenin kimliği hiçbir sayfada ve admin'de görünmez. Gizleme açık şikayetleri kapatır; "gizlemeden kapat" kayda düşmez. İçeriğin yanındaki bağlantılar `{% load moderation %}{% mod_links nesne %}`.
- Engelli üye okur, kendi yorumunu silebilir; yazamaz, düzenleyemez, oy veremez, öneri açamaz, şikayet edemez. `base.html` engeli bitiş tarihiyle gösterir.
- Admin: `FORUM['FOUNDING']` False olunca admin'den konu eklenemez, `role` (B statüsü yalnızca oylamayla) ve `is_moderator` salt okunur. İlk yöneticileri kurucu kuruluşta admin'den işaretler; aktif yöneticiler `mod/log/`'da herkese açık listelenir. `is_hidden`, `banned_until`, `is_active`, `terms_accepted_at` ve `deleted_at` admin'de salt okunur (kayda düşsün diye yalnızca moderasyon sayfaları). `Report`, `TopicVote`, `CommentVote` admin'de yok.
- Testler: `topics/tests.py`, `voting/tests.py`, `comments/tests.py`, `moderation/tests.py`, `accounts/tests.py`, `config/tests.py` (ortam değişkenleri, `check --deploy`, hata sayfaları, satır içi stil/script yok, PWA); `python manage.py test`. SQLite ve PostgreSQL 16'da geçiyor. Test kullanıcıları şifresiz (`make_user`), giriş `force_login` ile. Paneli okuyan ya da sorgu sayan testler `setUp`'ta `cache.clear()` çağırır.
- Yayın ayarları (`config/settings.py`): ortama göre değişen her şey ortam değişkeninden (`.env.example`); `load_env()` `.env`'i okur (python-dotenv yerine), gerçek ortam değişkeni önceliklidir. `required(ad, geliştirme_değeri)`: yayında (DEBUG kapalı) eksikse site açılmaz (`SECRET_KEY`, Turnstile, künye). `DATABASE_URL` yoksa SQLite; sunucuda `postgres:///forum` (yerel soket, peer). DEBUG kapalıyken: WhiteNoise hash'li ve sıkıştırılmış statik, HTTPS yönlendirme, güvenli çerezler, HSTS (`HSTS_SECONDS`), `SECURE_PROXY_SSL_HEADER` (önde Caddy), Django 6 CSP (yalnızca kendi dosyalarımız + Turnstile). `check --deploy` yayın ortamında uyarısız. 500 hataları `ADMINS`'e e-posta, uyarılar konsola (journald).
- Tasarım: tek `static/css/site.css`, renk/boşluk/yazı `:root` değişkenlerinde, koyu tema `prefers-color-scheme` ile yalnızca renkleri değiştirir; sistem fontu; renk çiftleri en az 6:1; `:focus-visible` halkası; düğme, menü, sekme, sayfalama, `summary` en az 44px. Şablonlarda satır içi stil ve script yok (CSP; `config/tests.py` denetler). Ortak sınıflar: `.top/.menu` (üst menü), `.topics` (konu satırı), `.badge` (+ `.hidden`, `.cancelled`), `.vote`, `.panel`, `.meta`/`.actions` (içerik bilgi satırı), `.opts` (sıralama), `.links`, `.list`, `.notice`, `.messages`, `.pages`, `.filters`, `.primary`. Panelsiz sayfa tek sütun (`aside:empty`). 360px'te yatay kaydırma yok. Evet/Hayır düğmeleri aynı görünümde (oylama yönlendirilmesin).
- Hata sayfaları: `403.html`, `404.html` `base.html`'den; `500.html` ve `403_csrf.html` istek bağlamı olmadan render edilir, bağımsız `error.html`'den türer.
- JS: tek `static/js/site.js` (framework yok): service worker kaydı ve ▲/▼ (`fetch` + formun CSRF alanı, `FormData(form, düğme)`; yanıt JSON değilse ya da hata varsa form normal gönderilir, sunucu mesajı gösterir). Sekmeler düz bağlantı.
- PWA: `/manifest.webmanifest`, `/sw.js` (kökten: kapsam bütün site), `/offline/`; üçü de `config/urls.py`'de `TemplateView` (`templates/pwa/`). Service worker yalnızca adında içerik hash'i olan statik dosyaları ve çevrimdışı sayfasını önbelleğe alır; sayfalar hep ağdan, POST'a dokunulmaz. Önbellek adı hash'li dosya adlarından: dosya değişince yeni sürüm kurulur, eski önbellek silinir. Geliştirmede adlar hash'siz, önbelleğe girmez. Çevrimdışı sayfası kullanıcıya bakmayan `error.html`'den. İkonlar `static/img/` (SVG logo; 192, 512, maskable, apple-touch PNG).
- Hukuki metinler: `kullanim-sartlari/`, `kvkk/`, `cerezler/`, `iletisim/` (`templates/legal/`, `config/urls.py`'deki `LEGAL`); kural sayıları `FORUM`'dan, künye (`SITE_OWNER`, `CONTACT_ADDRESS`, `CONTACT_EMAIL`) `settings.SITE`'tan. KVKK sayfası veri/amaç/hukuki sebep/süre listesini içerir (hata kaydı ve yedek 30 gün, trafik kaydı 400 gün). Kayıtta zorunlu kutu yalnızca şartların kabulü; KVKK aydınlatması onaya bağlanmaz, bağlantı olarak verilir. Alt bilgide bağlantılar.
- Sunucu (`deploy/`): Caddy (HTTPS, 5651 trafik kaydı JSON 400 gün), `forum.service` (gunicorn 127.0.0.1:8000, 2 süreç × 2 iş parçacığı), `forum-finalize.timer` (15 dk), `forum-backup.timer` (`backup.sh`, `pg_dump`, 30 gün), `update.sh <etiket>` (yedek → checkout → `check --deploy` → migrate → collectstatic → restart; geri alma aynı betikle), journald 30 gün.
- Açık: kabul edilip uygulanamayan öneri (ör. üst konusu kapanmış alt konu önerisi) süresiz bekliyor; bir son tarih ya da "uygulanamadı" durumu eklenmeli.
- Açık: admin'de konular hâlâ düzenlenebilir (başlık, `is_closed`, `is_deleted`); kuruluş bitince salt okunur olmalı. `role` ve konu ekleme `FOUNDING` ile kapanıyor.
- Açık (9. adımdan):
  - Hukuki metinler taslak (`templates/legal/base.html`'deki not): uzman kontrolü. BTK yer sağlayıcı bildirimi gerekiyor mu; Cloudflare ve yurt dışı e-posta için KVKK md. 9 standart sözleşmesi + 5 iş günü bildirim; trafik kaydının bütünlüğü (zaman damgası); yaş sınırı. Ayrıntı `DEPLOY.md` 15. bölüm.
  - Şartların sürümü yok, yalnızca kabul tarihi: şartlar değişince yeniden onay istemek için bir `TERMS_DATE` ayarı ve karşılaştırma gerekir.
  - Kuruluştan sonra yönetici atama ve görevden alma yöntemi (oylamayla mı, B statüsü gibi mi).
  - Hız sınırları (`over_limit`) veritabanında sayar, süreçler arasında doğru; aynı anda gelen iki istek sınırı bir kez aşabilir (zararsız, kilit yok).
  - Turnstile canlı CSP altında denenmedi (geliştirme ortamında dış ağ kapalıydı); ayar Cloudflare'in belgesiyle aynı.
  - Yedeklerin sunucu dışına kopyası elle (`scp`); otomatik değil.
  - `Report`'taki şikayet eden kimliği süresiz tutuluyor; kapanan şikayetlerde bir süre sonra silinebilir.
  - Dar ekranda menü satır kırarak sığıyor, açılır menü yok. Parola doğrulama mesajları Django'nun ("parola"), arayüz "şifre" diyor.
- Açık (8. adımdan):
  - `ModAction`'ın değişmezliği model düzeyinde; `QuerySet.update()/delete()` bunu atlar, kodda kullanılmamalı.
  - Gizlenen ama kabul edilmiş (henüz uygulanmamış) öneri iptal olmaz, uygulanabilir.
- Açık (7. adımdan):
  - Alt konuların etkinliği ana konunun popülerliğine eklenmiyor. Eklenirse her sayıma `object_id__in=Subquery(alt konu pk'leri)` ile bir alt sorgu daha gerekir.
  - `heat` her istekte hesaplanıyor. Konu sayısı binleri aşarsa `finalize_proposals` ile periyodik hesaplanıp `Topic.heat` alanına yazılabilir.
  - "Kapalı" sekmesinin "en yeni" sıralaması açılış tarihine göre. "En son kapanan önce" istenirse `closed_at` gerekir.
  - Puana göre sıralı yorumlarda oy verilen yorum komşu sayfaya kayabilir. O zaman dönüşte çapa bulunmaz, sayfa en üstte açılır.
- Yanıt bildirimleri şimdilik kapsam dışı.

## Yol haritası
1. Kurallar ✓
2. Kurulum: Python, VS Code, Git/GitHub, boş Django projesi ✓
3. Kullanıcılar: roller, oy ağırlığı, kayıt/giriş ✓
4. Konular ve alt konular ✓
5. Oylama motoru: öneri → tartışma → oylama → sonuç, zamanlayıcı ✓
6. Yorumlar ve upvote/downvote ✓
7. Ana sayfa: panel, sekmeler, sıralama ✓
8. Moderasyon: gizleme, engelleme, herkese açık moderasyon kaydı ✓
9. Yayın hazırlığı: tasarım, mobil uyum, PWA, yayın ayarları, hukuki metinler, `DEPLOY.md` ✓ (sunucuya kurulum ve hukuki kontrol kullanıcıda)

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
1.–9. adım tamamlandı (9. adım `adim-9` dalında). Sıradaki: `DEPLOY.md`'ye göre sunucuya kurulum, hukuki metinlerin uzman kontrolü, kuruluş (ilk konular, yöneticiler, `FOUNDING=False`).
