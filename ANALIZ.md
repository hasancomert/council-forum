# Analiz: problem çerçeveleme ve gereksinimler

Bu belge, dersin "Problem Çerçeveleme" (Hafta 2) ve "Bir YZ Uygulamasını Planlamak" (Sunum 1) yöntemlerini
projeye uygular. Haftanın sloganı burada da geçerli: **önce doğru problemi bul, sonra problemi doğru çöz.**
Tasarım kararları ve desenler `TASARIM.md`'de, kuralların koddaki yeri `SUNUM.md`'de.

## 1. İsteğin arkasındaki problemler

Başlangıçtaki istek belirsizdi: "Kararları topluluk versin." Slayttaki belediye örneğinde olduğu gibi aynı
cümlenin arkasında birkaç ayrı problem var. Her biri farklı bir çözüm ister ve hiçbiri ilk aşamada YZ gerektirmez.

| Problem | Çözüm türü | Projedeki karşılığı |
| --- | --- | --- |
| Kararları tek kişi veriyor, topluluk dışarıda | Süreç | Her değişiklik öneri + oylama (kural 5, 7, 9) |
| Sahte hesaplarla oy çoğaltılıyor | Kural + insan | E-posta doğrulama, CAPTCHA, 7 günlük hesap, yönetici kapatır (kural 1) |
| Uzman görüşü kalabalıkta kayboluyor | Kural | Ağırlıklı oy: B = 10, B statüsü 2/3 ile (kural 2) |
| Az kişinin katıldığı oylama herkesi bağlıyor | Kural | Yeter sayı: aktiflerin %10'u, en az 5 (kural 3) |
| Trol ve aşırı içerik | İnsan | Şikayet kuyruğu + yönetici, herkese açık kayıt |
| Önemli konular kalabalıkta kayboluyor | Kural | "En popüler" sıralaması: 3 × yorum + 1 × oy, son 7 gün |

## 2. YZ gerekli mi?

Slayttaki karar ağacı (etik ve yasal mı → basit kural yetiyor mu → veri var mı → hatanın bedeli yönetilebilir mi)
her karar noktasına uygulandı:

| Karar noktası | Etik/yasal | Basit kural yetiyor mu | Veri | Sonuç |
| --- | --- | --- | --- | --- |
| Öneri kabul mü ret mi | Evet | **Evet**: kural yönetmelik gibi yazılı (kural 3, 4) | — | **Kural yazın** |
| Oy ağırlığı | Evet | Evet: rol tablosu | — | Kural yazın |
| Sahte hesap tespiti | Evet | Kısmen: doğrulama, CAPTCHA, hesap yaşı | Yok (yeni forum) | Kural + **insan onayı** |
| Trol/aşırı içerik | Evet | Hayır: dil karmaşık | Yok | **Önce veri toplayın**, şimdilik insan |
| Konu sıralaması | Evet | Evet: etkinlik formülü | — | Kural yazın (temel çizgi) |
| Üyenin profilinden "güvenilirlik puanı" çıkarıp oy ağırlığını otomatik ayarlamak | **Hayır** | — | — | **Yapmayın** |

Sonuç: sistemin çekirdeği kural tabanlıdır (Yazılım 1.0). Slayttaki harf notu örneğinde olduğu gibi bu kuralları
bir modele öğretmek, bilinen kuralın bozuk bir kopyasını üretirdi. Ayrıca sonuç açıklanabilir olmalı: üye
"neden reddedildi?" diye sorduğunda cevap "katılım 4, yeter sayı 5"tir, "model öyle dedi" değil.

"Kural yazın" bir yenilgi değildir: bu kurallar, ileride bir ML bileşeninin yenmesi gereken **temel çizgidir**.
Geleceğin en makul ML adayı şikayet kuyruğudur. Slayttaki afet mesajları örneği gibi karma bir düzen kurulabilir:
model şikayetleri aciliyete göre sıralar, karar yine yöneticide kalır. Yöneticinin her kararı (`ModAction`) bir
etiket olur; böylece veri çarkı kendiliğinden oluşur.

## 3. Çerçeveleme hunisi

| Basamak | Bu projede |
| --- | --- |
| İş hedefi | Topluluğun kendi kurallarını adil, şeffaf ve tek kişiye bağımlı olmadan koyması |
| İş sorusu | Kararlar neden tartışmalı? Tek kişi karar veriyor, sahte hesaplar oy çoğaltıyor, uzman görüşü kayboluyor |
| Karar | Bu öneri (konu aç, düzenle, kapat, sil, geri al, istek, B statüsü) kabul edilsin mi? |
| "Tahmin" yerine hesap | Katılım ≥ max(5, ⌈aktif × %10⌉) ve ağırlıklı evet > hayır mı? (B statüsünde evet ≥ 2/3) |
| Görev türü | Belirlenimci (deterministik) ikili karar fonksiyonu; ML görevi değil |
| Veri | `Vote` kayıtları (ağırlık oy anında sabitlenir); aktif üye = son 30 günde karar oyu veren, konu açan ya da yorum yazan |

Slayttaki zincir burada şöyle işler: **oy → sonuç → eylem → değer.** Oylar ağırlıklı toplanır. Kabul edilen
öneri `apply()` ile kimse dokunmadan uygulanır. Değer, kararlara katılımın ve topluluğun güveninin artmasıdır.

## 4. Başarı metrikleri

Slayttaki üç katmanlı yapı, model metriği yerine **kural ve sistem metriğiyle** kuruldu:

| Katman | Metrik | Nasıl ölçülür |
| --- | --- | --- |
| İş | Son 30 günde aktif üye sayısı; yeter sayıya ulaşan önerilerin oranı | `active_member_count()`; sonuçlanan önerilerde `quorum` alanı |
| Ürün / kullanıcı | Öneri başına katılım (turnout); "Oy ver" rozeti gösterilen üyelerden oy verenlerin oranı; şikayetin işlenme süresi | Panel ve öneri sayfası; `Report` ile `ModAction` tarihleri |
| Sistem | Kuralların doğruluğu: 133 testin hepsi geçiyor; sayfa başına veritabanı sorgu sayısı sabit | `python manage.py test`; sorgu sayan testler |
| Koruyucu (guardrail) | Moderasyonla gizlenen içerik oranı (sansür artmasın); iptal edilen ve "Uygulanamadı" öneri oranı; B statüsündeki üye oranı | Moderasyon kaydı, öneri durumları, `User.role` |

**Goodhart yasası** burada da geçerli. "Katılımı artırın" tek hedef olursa, tartışmayı okumadan tek tıkla oy veren
üyeler artar. Bu yüzden katılımla birlikte yorum ve tartışma oranı da izlenir.

**Eşik bir iş kararıdır** (slayt 29). Yeter sayının %10 / en az 5 olması, B statüsü için 2/3 ve eşitlikte ret,
model parametresi değil topluluk kararıdır. Bu yüzden koda gömülü değil, `config/settings.py` → `FORUM` içindedir.
Hata maliyeti de bu eşikleri belirler:

- **Yanlış kabul:** Az katılımla bir değişikliğin geçmesi. Bedeli yüksektir; yeter sayı bunu sınırlar.
- **Yanlış ret:** Eşitlikte ret. Bedeli düşüktür: mevcut durum korunur, öneri 30 gün sonra yeniden açılabilir.

## 5. Temel çizgi (baseline)

Slayttaki temel çizgi merdiveni, oylama kurallarına uyarlandı. Her basamak, bir üstündeki kuralın neden gerekli
olduğunu gösterir:

| Basamak | Çözüm | Neden yetmez |
| --- | --- | --- |
| 1. Hep ret ("çoğunluk sınıfı") | Hiçbir değişiklik yapılmaz | Topluluk hiçbir şeyi değiştiremez |
| 2. Mevcut çözüm | Klasik forum: yönetici karar verir | Tek kişiye bağımlı, şeffaf değil |
| 3. Basit kural | Anket: kişi başı bir oy, salt çoğunluk | 2 kişinin oyu herkesi bağlar; sahte hesapla çoğaltılır; uzman görüşü kaybolur |
| 4. Bizim sistem | Ağırlıklı oy, yeter sayı, süre, hesap yaşı, öneri sınırı, ret yasağı | Her ek kural, 3. basamaktaki bir açığı kapatır |

Her kural, kaldırıldığında açılan zaafla birlikte test edilir (`voting/tests.py`): yeter sayı yoksa
`test_quorum_not_met_rejects`, eşitlikte `test_tie_rejects`, B statüsünde `test_expert_two_thirds_unweighted`,
öneri sınırında `test_open_proposal_limit`, ret yasağında `test_rejection_cooldown_counts_from_voting_end`.

## 6. Kısıtlar

| Kısıt | Bu projede |
| --- | --- |
| Zaman | Ödev teslimi 3 Ekim 2026; yayına alma ödevin kapsamı dışında |
| Bütçe | Yerelde 0 TL; yayında tek küçük VPS (`DEPLOY.md`); GPU yok, ücretli API yok |
| Gecikme | Sayfa başına sorgu sayısı konu ve yorum sayısından bağımsız; hedef p95 < 200 ms (ortalama değil, yüzdelik) |
| Gizlilik ve KVKK | Kimin ne oy verdiği hiçbir yerde görünmez; hesap silinince kişisel veri anonimleşir |
| Donanım / ortam | Windows dizüstü + telefonda Expo Go; ikisi aynı yerel ağda |
| Yasal ve etik | 5651 (yer sağlayıcı), KVKK, kullanım şartları; metinler taslak, uzman kontrolü bekliyor |
| Teknik | Ek paket yok: Django'nun hazır araçları; Python bağımlılıkları yalnızca Django, gunicorn, psycopg, WhiteNoise |

## 7. Paydaşlar

Slayttaki restoran örneğinde olduğu gibi her paydaş başka bir şey istiyor. Ödünleşimler yazılı karara bağlandı:
her biri `CLAUDE.md` → "Kararlar ve notlar" bölümünde.

| Paydaş | İstediği | Çatışma | Yazılı karar |
| --- | --- | --- | --- |
| A üyesi | Sesinin eşit duyulması | B'nin 10 kat ağırlığı | Ağırlık yalnızca karar oylarında; yorum oyları herkes için 1 |
| B (bilirkişi) | Görüşünün ağırlığı | Uzmanlık ölçülemez, kalıcı ayrıcalık | B statüsü 2/3 evetle verilir, aynı yolla geri alınır |
| Yönetici | Trol ve sahte hesaptan korunma | Yetkinin kötüye kullanılması | Yalnızca moderasyon; gerekçe ve not zorunlu; kayıt herkese açık ve değiştirilemez |
| Kurucu | Forumu kurmak, ilk konuları açmak | Kalıcı süper yetki | `FOUNDING = False` olunca admin salt okunur; oylar admin'de yok |
| Değerlendirici (hoca) | Yazılım mühendisliği ilkeleri, çalışan site + mobil | — | `TASARIM.md`, testler, `SUNUM.md` |
| Hukuk (KVKK, 5651) | Veri en aza indirme, iletişim bilgisi | Kayıt verisinin saklanması | Anonimleştirme, hukuki metin taslakları (`templates/legal/`) |
| İşletim | Düşük maliyet, kolay bakım | Yeni özellik istekleri | Tek sunucu, ek paket yok, kural sayıları ayarda |

## 8. Ön-otopsi (pre-mortem)

"Aradan 6 ay geçti ve forum başarısız oldu. Neden?" sorusuna verilen cevaplar, olasılık ve etkiye göre sıralandı.
Sağ üst köşedekilere bugünden önlem yazıldı.

| Risk | Olasılık | Etki | Önlem | Durum |
| --- | --- | --- | --- | --- |
| A. Katılım düşük, öneriler yeter sayıya ulaşmıyor | Yüksek | Yüksek | Yeter sayı orana bağlı ama en az 5; aktif oylamalar paneli; "Oy ver" rozeti; mobil uygulama | Önlem var; oran izlenmeli |
| B. Sahte hesaplarla oy çoğaltma | Orta | Yüksek | E-posta, CAPTCHA, 7 gün; kapatılan hesabın süren oyları silinir | Önlem var |
| C. B statüsü birkaç kişide toplanıp kararları domine eder | Orta | Yüksek | 2/3 eşiği, geri alınabilirlik | Kısmi: B ağırlıklarının toplamına sınır yok (açık) |
| D. Yönetici yetkisini kötüye kullanır | Düşük | Yüksek | Herkese açık, değiştirilemez kayıt; gerekçe zorunlu | Önlem var |
| E. Kurucu admin'den kuralları deler | Düşük | Yüksek | `FOUNDING = False` ile admin salt okunur | Önlem var |
| F. Oy gizliliği sızar | Düşük | Yüksek | Oy tabloları admin'de yok; sonuç yalnızca bitince; testler | Önlem var |
| G. Aynı öneri iki kez uygulanır | Düşük | Orta | Koşullu UPDATE; `apply()` uygun değilse "Uygulanamadı" | Önlem var |
| H. Hukuki sorun (KVKK, 5651) | Orta | Yüksek | Taslak metinler, `DEPLOY.md` 15. bölüm | Açık: uzman kontrolü |

## 9. Tek sayfalık problem tanım kanvası

| Kutu | İçerik |
| --- | --- |
| 1. İş hedefi ve değer | Topluluk kararlarını şeffaf ve tek kişiye bağımlı olmadan kendisi verir. İş metriği: aktif üye ve yeter sayıya ulaşan öneri oranı. |
| 2. Karar ve eylem | Her öneri için kabul mü ret mi? Oylama süresi dolunca sistem kendisi sonuçlandırır ve uygular (sayfa ziyaretinde ya da 15 dakikada bir). |
| 3. Görev | Girdi: öneriye verilmiş ağırlıklı oylar ve aktif üye sayısı. Çıktı: kabul ya da ret. Görev türü: kural tabanlı ikili karar. |
| 4. Veri | `Vote`, `Topic`, `Comment` kayıtları. Kişisel veri: ad, soyad, e-posta yalnızca hesapta; hesap silinince anonimleşir (KVKK). |
| 5. Metrikler | Sistem: kuralların doğruluğu (testler). Ürün: katılım. Koruyucu: gizlenen içerik ve iptal oranı. |
| 6. Baseline | Klasik forum (yönetici karar verir) ve basit anket (kişi başı oy, salt çoğunluk). |
| 7. Kısıtlar | 3 Ekim 2026; 0 TL; GPU yok; ek paket yok; KVKK; yerel ağ. |
| 8. Riskler ve başarı | Ön-otopsi tablosu. Başarı ölçütü: site ve mobil aynı sunucuda uçtan uca çalışıyor, 9 kuralın hepsi testle doğrulanmış. |

## 10. Ürün planı (Sunum 1)

- **YZ'nin rolü:** Ürün YZ olmadan çalışır. İleride eklenecek bir bileşen tamamlayıcı ve öngörülü olmalı (şikayet
  kuyruğunu önceden sıralamak gibi). Kritik bir rol üstlenmemeli.
- **İnsan döngüde:** Moderasyon tamamen insanda, kararlar toplulukta. YZ eklenirse "emekle" aşamasından başlar:
  model önerir, yönetici onaylar.
- **ML sistemlerinin dört gereksinimi, bu sisteme uyarlanmış:**
  - *Güvenilirlik:* koşullu UPDATE, 133 test.
  - *Ölçeklenebilirlik:* sabit sorgu sayısı, ortak önbellek, PostgreSQL.
  - *Sürdürülebilirlik:* kural sayıları ayarda, `CLAUDE.md`, testler.
  - *Uyarlanabilirlik:* yeni öneri türü yalnızca bir sınıf eklenerek yazılır (`TASARIM.md`).
- **Son kilometre:** Demo hazır. Gerçek ürün için yayına alma, hukuki kontrol ve iki telefonda deneme hâlâ açık.
- **Bakım:** Kurallar değişince yalnızca `FORUM` değişir. Yeni kural türü için `TASARIM.md`'deki genişleme
  noktaları kullanılır.

## 11. Gereksinimler ve izlenebilirlik

İşlevsel gereksinimler, her biri kodu ve onu doğrulayan testle:

| No | Gereksinim | Kod | Test |
| --- | --- | --- | --- |
| İG-1 | Kayıt e-posta doğrulaması ve CAPTCHA ister | `accounts/views.py`, `accounts/forms.py` | `test_signup_then_activate`, `test_captcha_required` |
| İG-2 | Oy ve öneri için hesap en az 7 günlük olmalı | `User.can_vote` | `test_weight_and_min_age`, `test_new_account_cannot_propose` |
| İG-3 | Öneri, yeter sayı ve ağırlıklı çoğunlukla sonuçlanır; eşitlikte ret | `BaseProposal.finalize()` | `test_weighted_majority_accepts_and_applies`, `test_tie_rejects`, `test_quorum_not_met_rejects` |
| İG-4 | B statüsü 2/3 evet ister, bu oylamada herkesin oyu 1 | `ExpertProposal` | `test_expert_two_thirds_unweighted` |
| İG-5 | İstek 3 gün tartışılır, sonra 3 gün oylanır | `RequestProposal` | `test_request_discussion_then_voting` |
| İG-6 | Oylama sürerken yalnızca katılım görünür | `results_visible` | `test_detail_hides_result_until_voting_ends`, `test_list_and_detail_keep_results_secret_until_the_end` |
| İG-7 | Kapalı konu yorum ve öneri almaz; geri alma oylamayla | `Topic.is_open`, `TopicUndoProposal` | `test_closed_topic_takes_undo_but_not_edit`, `test_undo_reopen` |
| İG-8 | Kişi başı en fazla 3 açık öneri; reddedilen 30 gün açılamaz | `BaseProposal.clean()` | `test_open_proposal_limit`, `test_rejection_cooldown_counts_from_voting_end` |
| İG-9 | Yönetici yalnızca moderasyon yapar; her işlem herkese açık kayda düşer | `moderation/views.py`, `ModAction` | `test_hide_needs_reason_and_note_and_is_logged`, `test_log_is_append_only_public_and_filterable` |
| İG-10 | Mobil uygulama sitenin kurallarını aynen uygular | `api/views.py` | `test_vote_uses_site_rules`, `test_vote_needs_account_age` |

İşlevsel olmayan gereksinimler:

| No | Gereksinim | Nasıl sağlanır |
| --- | --- | --- |
| İOG-1 Performans | Sayfa başına sorgu sayısı veri miktarından bağımsız | Alt sorgular, `count_of()`; sorgu sayan testler |
| İOG-2 Güvenlik | CSRF, CSP, HTTPS, imzalı jeton, açık yönlendirme yok | `config/settings.py`, `config/utils.back()`, `api/views.py` |
| İOG-3 Gizlilik | Kimin ne oy verdiği gizli; KVKK | Oy tabloları admin'de yok; `User.anonymize()` |
| İOG-4 Erişilebilirlik | Dokunma hedefi ≥ 44 px, kontrast ≥ 5,6:1, 360 px'te yatay kaydırma yok | `static/css/site.css`, `config/tests.py` |
| İOG-5 Taşınabilirlik | SQLite (geliştirme) ve PostgreSQL (yayın) | `DATABASE_URL`; testler iki veritabanında |
| İOG-6 Sürdürülebilirlik | Kural sayıları tek yerde; ek paket yok; testler | `FORUM`, `requirements.txt` |
| İOG-7 Kullanılabilirlik | Site PWA; Android ve iPhone'da uygulama | `templates/pwa/`, `mobile/` |

## 12. YZ kullanım beyanı

Dersin teslim kuralı gereği ("YZ kullandıysanız her teslimde YZ kullanım beyanı"):

- **Kullanılan araçlar:** Claude Code (kodun, testlerin ve belgelerin yazımı); claude.ai (kuralların ve tasarımın
  tartışılması); Claude Sonnet alt-ajanları (bu revizyonda projenin her ilke için ayrı ayrı incelenmesi).
- **İnsanın yaptıkları:** Problem ve kurallar (9 kural, roller); her adımın planını onaylamak; tasarım kararları;
  telefonda deneme; teslim.
- **YZ'nin yaptıkları:** Kod, testler, belgeler, inceleme raporları. Her adım önce plan olarak sunuldu, onaydan sonra
  yazıldı.
- **Doğrulama (Sunum 2'deki kontrol listesi):**
  - Değişiklikler `python manage.py test` geçtikten sonra commit'lendi.
  - Mobil kod `tsc` ile tip denetiminden geçti.
  - Bağımlılıklar sürümüyle sabitlendi (`requirements.txt`, `package-lock.json`).
  - Uydurma paket adı (slopsquatting) riskine karşı paket sayısı en az tutuldu. Python'da Django dışında yalnızca
    gunicorn, psycopg ve WhiteNoise var. Mobilde Expo şablonunun paketleri ve `expo-secure-store` kullanılıyor;
    sürümler SDK'nın uyumlu sürüm listesinden alındı.
  - YZ'nin yazdığı testler de gözden geçirildi.
