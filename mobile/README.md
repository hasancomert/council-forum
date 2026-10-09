# Forum mobil uygulaması

Expo (React Native, TypeScript, Expo Router, SDK 57). Sitedeki forumun aynısı: aynı Django sunucusuna `/api/`
üzerinden bağlanır. Kurallar yalnızca sunucuda; uygulama gösterir ve gönderir, hata mesajları da sunucudan gelir.

## Çalıştırma

1. Bilgisayarda Node.js LTS (bir kez): `winget install OpenJS.NodeJS.LTS`, sonra terminali kapatıp aç.
2. Telefonlara **Expo Go** (App Store / Google Play, güncel sürüm SDK 57'yi açar).
3. Birinci terminal, proje kökünde (`.venv` etkin):
   ```powershell
   python manage.py runserver 0.0.0.0:8000
   ```
4. İkinci terminal:
   ```powershell
   cd mobile
   npm install        # yalnızca ilk sefer ve package.json değişince
   npx expo start
   ```
5. Çıkan QR kodu okut: Android'de Expo Go'nun içinden, iPhone'da kamerayla.

Telefon ve bilgisayar aynı ağda olmalı (sunumda en güvenlisi bilgisayarı telefonun hotspot'una bağlamak).
Uygulama sunucuyu kendisi bulur: Expo'nun bağlandığı bilgisayarın IP'si + `:8000` (giriş ekranının altında ve
Hesabım'da yazar). Kayıt, e-posta doğrulaması, şifre işlemleri, hesap silme ve moderasyon sitede açılır.

## Ekranlar

| Ekran | Dosya | API |
| --- | --- | --- |
| Konular (sekmeler, sıralama, kaydırdıkça yükleme) | `src/app/(tabs)/index.tsx`, `components/TopicList.tsx` | `topics/` |
| Öneriler (oylamada / tartışmada, "Oy ver") | `src/app/(tabs)/proposals.tsx` | `proposals/` |
| Hesabım (rol, oy hakkı, çıkış) | `src/app/(tabs)/account.tsx` | `me/` |
| Giriş | `src/app/login.tsx` | `login/` |
| Konu (▲/▼, alt konular, öneri bağlantıları, yorumlar) | `src/app/topic/[pk].tsx`, `components/Comments.tsx` | `topics/<pk>/`, `comments/<ct>/<pk>/` |
| Alt konular | `src/app/subtopics/[pk].tsx` | `topics/?parent=` |
| Öneri (Evet/Hayır, katılım, sonuç, yorumlar) | `src/app/proposal/[slug]/[pk].tsx` | `proposals/<tip>/<pk>/` |
| Yeni öneri (her tip için tek form) | `src/app/new/[slug].tsx` | `proposals/new/<tip>/[<konu>/]` |

`src/app/` altındaki her dosya bir ekran (Expo Router; Java'daki bir Activity/sayfa gibi, adresi dosya yolu).
`src/lib/`: `api.ts` (sunucu adresi, jeton, `api()` ve yanıt tipleri), `auth.tsx` (oturum), `paged.ts` (sayfalı
liste), `theme.ts` (`site.css`'teki renkler, koyu tema). `src/components/`: ortak parçalar (`ui.tsx`: düğme, rozet,
uyarı kutusu).

## Sorun giderme

- **"Sunucuya ulaşılamadı"**: runserver `0.0.0.0:8000` ile mi çalışıyor? Telefonun tarayıcısında
  `http://BILGISAYAR_IP:8000` açılıyor mu? Açılmıyorsa Windows güvenlik duvarı Python'u engelliyor: izin ver
  (hotspot "Ortak ağ" sayılırsa ortak ağa da).
- **Adres yanlış bulunuyorsa** elle ver:
  ```powershell
  $env:EXPO_PUBLIC_SERVER="http://192.168.1.5:8000"; npx expo start
  ```
- **QR okununca Expo Go bağlanamıyorsa**: güvenlik duvarı Node.js'e de izin vermeli (8081 portu).
- **"Oturumun sona erdi"**: jeton 30 gün geçerli (`FORUM['API_TOKEN_DAYS']`), şifre değişince hemen biter.
  Yeniden giriş yap.
- **Oy veremiyorum**: hesap en az 7 günlük olmalı (kural 1); Hesabım oy hakkının başlayacağı tarihi yazar.

## Denetim

```powershell
npx tsc --noEmit        # tip denetimi (npx expo start bir kez çalıştıktan sonra: ekran adlarının tipleri .expo/types'ta)
npx expo start --web    # tarayıcıda önizleme: http://localhost:8081, sunucu http://localhost:8000
```
