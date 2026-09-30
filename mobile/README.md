# Forum mobil uygulaması

Expo (React Native, TypeScript, Expo Router, SDK 57). Sitedeki forumun aynısı: aynı Django sunucusuna `/api/`
üzerinden bağlanır, kurallar sunucuda.

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
Uygulama sunucuyu kendisi bulur: Expo'nun bağlandığı bilgisayarın IP'si + `:8000` (giriş ekranının altında yazar).

## Sorun giderme

- **"Sunucuya ulaşılamadı"**: runserver `0.0.0.0:8000` ile mi çalışıyor? Telefonun tarayıcısında
  `http://BILGISAYAR_IP:8000` açılıyor mu? Açılmıyorsa Windows güvenlik duvarı Python'u engelliyor: izin ver
  (hotspot "Ortak ağ" sayılırsa ortak ağa da).
- **Adres yanlış bulunuyorsa** elle ver:
  ```powershell
  $env:EXPO_PUBLIC_SERVER="http://192.168.1.5:8000"; npx expo start
  ```
- **QR okununca Expo Go bağlanamıyorsa**: güvenlik duvarı Node.js'e de izin vermeli (8081 portu).
- **Tip denetimi**: `npx tsc --noEmit` (`npx expo start` bir kez çalıştıktan sonra: ekran adlarının tipleri
  `.expo/types`'a yazılır).
