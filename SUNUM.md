# Sunum notları

Oylamayla yönetilen forum: kararları (konu açma, düzenleme, kapatma, silme, istekler, bilirkişilik) üyeler
oylamayla verir. Aynı forum iki yüzle çalışır: **site** (Django şablonları, PWA) ve **telefon uygulaması**
(Expo / React Native). İkisi aynı sunucuya ve aynı veritabanına bağlıdır.

## Mimari

```
Telefon (Expo Go, React Native) ── JSON /api/, Authorization: Bearer <jeton> ──┐
                                                                               ├── Django ── SQLite
Tarayıcı (site, PWA)            ── HTML sayfalar, oturum çerezi + CSRF ────────┘
```

- Kurallar yalnızca sunucuda. API (`api/views.py`) yeni kural yazmaz, sitenin görünümlerinin kullandığı aynı
  fonksiyonları çağırır: `topics.views.listing/page_data`, `voting.views.page_data/new_form`,
  `comments.views.section/create`, `moderation.views.file_report` ve model metotları (`Vote.cast`, `clean()`).
- Jeton: `django.core.signing` ile imzalı [kullanıcı, şifre özeti]; veritabanında tutulmaz, şifre değişince
  geçersiz. Çerez kullanılmadığı için CSRF gerekmez.
- Yeni öneri formu sunucudan gelir (alanlar, etiketler, başlangıç değerleri), hatalar alan bazında döner:
  uygulamada her öneri tipi için tek form ekranı var.
- Kural sayıları koda gömülü değil: `config/settings.py` → `FORUM`.

## Kurallar kodda nerede

| Kural | Kod |
| --- | --- |
| 1. Sahte hesap: e-posta doğrulama, CAPTCHA, 7 günlük hesap | `accounts/views.py` (signup, activate), `accounts/forms.py` (Turnstile), `User.can_vote` |
| 2. B statüsü: 2/3 evet, bu oylamada herkes 1 | `ExpertProposal` (`_accepted`, `WEIGHTED = False`), `User.vote_weight` |
| 3. Yeter sayı: son 30 günde aktiflerin %10'u, en az 5 | `voting.models.required_quorum()`, `active_member_count()` |
| 4. Kabul: ağırlıklı çoğunluk, eşitlikte ret | `BaseProposal._accepted()`, `finalize()` |
| 5. Süreler: 2 gün; istekte 3 + 3 gün | `BaseProposal.save()`, `RequestProposal.save()` |
| 6. Gizlilik: sürerken yalnızca katılım, oy değiştirilebilir | `results_visible`, `Vote.cast()` (upsert); API'de `turnout` / `result` |
| 7. Kapatma/silme: kapalı görünür, silinen gizlenir | `Topic.is_open`, `TopicQuerySet.visible()`, `apply()` metotları → `Topic.change()` |
| 8. Kişi başı 3 açık öneri, reddedilen 30 gün açılamaz | `BaseProposal.clean()`, `open_proposal_count()` (`running()`), `is_duplicate()` |
| 9. İlk konuları kurucu açar | `FORUM['FOUNDING']`, admin |

## Yazılım mühendisliği (12. adım)

- **Analiz** (`ANALIZ.md`): problem çerçeveleme hunisi, "YZ gerekli mi?" karar ağacı (kararlar kural, YZ değil),
  başarı metrikleri, temel çizgi merdiveni, ön-otopsi, paydaşlar, izlenebilir gereksinimler (her biri kod + test).
- **Tasarım** (`TASARIM.md`): SOLID tablosu, desen haritası, bilerek uygulanmayan desenler, anti-desen denetimi.
  Gösterilecek üç örnek:
  - **Template Method:** `BaseProposal.finalize()`. Akış sabit, `apply()` gibi adımlar tipe göre.
  - **Registry:** öneri tipleri kendini kaydeder. Yeni tip yalnızca bir alt sınıftır; URL, form, admin, panel, API
    ve konu sayfasındaki bağlantı kendiliğinden gelir (açık/kapalı ilkesi).
  - **Command:** öneri, kuyrukta bekleyen bir işlemdir. Sonra `apply()` ile uygulanır; geri alma da bir öneridir.
- **İnceleme:** 12 alt ajan her ilkeyi ayrı inceledi. Bulgular testle doğrulandı, 28 gerçek hata düzeltildi.
  Örnekler:
  - Admin'de üye silme sayfası oyları gösteriyordu (kural 6).
  - Taze kurulumda ana sayfa 500 veriyordu (erken optimizasyon olan önbellek kaldırıldı).
  - Yerelde süresi dolan öneri sonuçlanmıyordu.
- **Testler:** 191 test. Her bileşene sahte nesneyle birim testi var (ör. sahte `urlopen`, sahte kullanıcı).
  Mutasyon testi, testlerin bilerek bozulmuş kodu ne oranda yakaladığını ölçüyor (`TASARIM.md` 6).
- **UML** (`diyagramlar/`, PlantUML): kullanım durumu (`ANALIZ.md` 11), 3 sınıf ve 4 sıralama diyagramı
  (`TASARIM.md` 9). Sunumda gösterilecek ikisi: sınıf diyagramı 2 (öneriler: şablon metot ve kancalar) ve sıralama
  diyagramı 1 (telefondan oy: site ile aynı `Vote.cast()`).

## Demo hazırlığı

- Sunucu: `python manage.py runserver 0.0.0.0:8000`; uygulama: `cd mobile`, `npx expo start` (ayrıntı
  `mobile/README.md`). Bilgisayar telefonun hotspot'una bağlı olsun.
- En az iki hesap, **7 günden eski** (kural 1): admin → Kullanıcılar → hesap → "Önemli tarihler" → katılma
  tarihini geri al. Yeni kayıtta doğrulama bağlantısı e-posta yerine runserver terminaline yazılır.
- Ağırlığı göstermek için bir hesabı admin'den B yap (kuruluş sürerken, `FOUNDING=True`).
- Sunumda `.env`'e rastgele bir `SECRET_KEY` yaz (hotspot'taki herkes sunucuya erişebilir; depodaki geliştirme
  anahtarı herkesçe bilinir):
  `python -c "from django.core.management.utils import get_random_secret_key as k; print(k())"`
- Sonuç çubuğunu göstermek için önceden bitmiş bir öneri olsun. Yalnızca demo veritabanında, bir öneriyi hemen
  bitirmek için (ana sayfa ya da öneri sayfası açılınca sonuçlanır, zamanlayıcı gerekmez):
  ```powershell
  python manage.py shell -c "from django.utils import timezone; from voting.models import TopicCloseProposal as P; P.objects.filter(pk=1).update(voting_ends_at=timezone.now())"
  ```

## Demo senaryosu (5 dakika)

1. Telefonda giriş. Ana sayfa: sekmeler, sıralama, aşağı çekip yenileme; koyu tema telefonun ayarıyla.
2. Telefondan bir konuya ▲ → bilgisayarda sitede aynı konuyu yenile: puan değişti (aynı veritabanı).
3. Sitede başka hesapla yorum yaz → telefonda aşağı çek, yorum geldi; telefondan yanıtla, sitede görünsün.
4. Kendi yorumuna ▲ dene: "Kendi yorumuna oy verilmez" (kural sunucuda, uygulama yalnızca gösterir).
5. Telefondan "Kapatma öner" → Öneriler sekmesinde ve sitedeki "Aktif oylamalar" panelinde görünür, konuda
   "Kapatma oylamasında" rozeti. Evet ver: yalnızca katılım görünür (1/5), sonuç gizli (kural 6).
6. Bitmiş öneriyi aç: yeşil/kırmızı sonuç çubuğu, B üyesinin oyu 10 sayılır.
7. 7 günlük olmayan hesapla giriş → Hesabım: "Oy hakkın … tarihinde başlar".

## Olası sorular

- **Kurallar iki kez mi yazıldı?** Hayır: site ve API aynı fonksiyonları çağırır; API'nin testleri
  (`api/tests.py`) sitedeki kuralların API'den de geçtiğini denetler.
- **Kimin ne oy verdiği görünür mü?** Hayır: API yalnızca kendi oyunu ve (bitince) toplamları döndürür; admin'de
  de oy tablosu yok.
- **Neden Expo?** Tek TypeScript koduyla Android ve iPhone; Expo Go ile derleme yapmadan telefonda çalışır.
- **Güvenlik?** Jeton imzalı ve süreli (30 gün), şifre değişince geçersiz; gizli içerik ve oy gizliliği sitedekiyle
  aynı fonksiyonlardan geçer.
- **Hangi tasarım desenleri, neden?** Bkz. `TASARIM.md` 3. Desen ihtiyaç olunca kondu. State, Observer sinyalleri
  ve servis katmanı bilerek yok (bölüm 4). Python'da Strategy, Singleton ve Iterator'ın ayrı sınıfa gerek duymadığı da
  orada.
- **Testler gerçekten hata yakalıyor mu?** Mutasyon testi: kod bilerek bozuldu (ör. "eşitlikte kabul",
  "silme uygulanmıyor"); bozulanların çoğunu testler yakaladı (`TASARIM.md` 6).
- **Diyagramlar kodla uyumlu mu?** Koddan çıkarıldı, adlar aynı. PlantUML metin olduğu için kodla birlikte
  sürümlenir; model değişince `.puml` da değişir (`TASARIM.md` 9).
