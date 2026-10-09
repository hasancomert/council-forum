# Yayına alma (Türkiye'de VPS, Ubuntu 26.04)

Windows'tan adım adım. Komutların başındaki işaret nerede çalışacağını söyler:
`PS>` Windows PowerShell, `#` sunucuda root. Hiçbir adım bir şey satın almaz; alımlar senin kararın.

Düzen:

```
İnternet ──443──> Caddy (HTTPS, trafik kaydı) ──> gunicorn 127.0.0.1:8000 (Django) ──> PostgreSQL (yerel soket)
                                                     systemd timer: finalize_proposals (15 dk), yedek (günlük)
```

| Ne | Nerede |
|---|---|
| Kod | `/srv/forum` (git deposu), sanal ortam `/srv/forum/.venv` |
| Ayarlar | `/srv/forum/.env` (repoda yok, yalnızca forum kullanıcısı okur) |
| Uygulama kullanıcısı | `forum` (giriş yapamayan sistem kullanıcısı) |
| Yedekler | `/var/backups/forum` (30 gün) |
| Trafik kaydı (5651) | `/var/log/caddy/forum-access.log` (400 gün) |
| Hata kayıtları | `journalctl -u forum` (30 gün) |

## 1. Sunucuyu seç

Türkiye lokasyonlu bir VPS (KVM). Aranacaklar:

- Ubuntu 26.04 LTS imajı: Python 3.14 hazır gelir. Yalnızca 24.04 varsa 3.14'ü `uv python install 3.14` ile kur.
- En az 2 GB RAM, 20 GB disk, sabit IPv4 (varsa IPv6).
- SSH anahtarıyla kurulum.
- Sağlayıcıyla KVKK veri işleme sözleşmesi: sağlayıcı veri işleyen sayılır.
- İsteğe bağlı: sağlayıcının anlık görüntü (snapshot) hizmeti.

## 2. SSH anahtarı (Windows)

```powershell
PS> ssh-keygen -t ed25519            # Enter, Enter; anahtar: $env:USERPROFILE\.ssh\id_ed25519
PS> Get-Content $env:USERPROFILE\.ssh\id_ed25519.pub   # bu satırı sağlayıcının paneline yapıştır
PS> ssh root@SUNUCU_IP
```

## 3. Sunucunun temeli

```sh
# apt update && apt full-upgrade -y
# apt install -y python3-venv postgresql caddy git unattended-upgrades ufw
# ufw allow OpenSSH && ufw allow 80 && ufw allow 443 && ufw enable
# echo 'PasswordAuthentication no' > /etc/ssh/sshd_config.d/00-yalnizca-anahtar.conf && systemctl reload ssh
# timedatectl set-timezone Europe/Istanbul
```

Şifreyle SSH girişini kapatmadan önce anahtarla girebildiğini ikinci bir pencerede dene. Güvenlik güncellemeleri
`unattended-upgrades` ile kendiliğinden kurulur.

## 4. Veritabanı ve uygulama kullanıcısı

```sh
# adduser --system --group --home /home/forum --shell /bin/bash forum
# sudo -u postgres createuser forum
# sudo -u postgres createdb --owner forum forum
# install -d -o forum -g forum -m 700 /srv/forum /var/backups/forum
```

Parola yok: `forum` kullanıcısı PostgreSQL'e yerel soketten kendi adıyla (peer) bağlanır, dışarıdan bağlantı kapalı.

## 5. Kodu indir

Depo private olduğu için sunucuya yalnızca okuma izinli bir "deploy key" verilir:

```sh
# sudo -u forum mkdir -p -m 700 /home/forum/.ssh
# sudo -u forum ssh-keygen -t ed25519 -N '' -f /home/forum/.ssh/id_ed25519
# cat /home/forum/.ssh/id_ed25519.pub
```

GitHub'da: depo → Settings → Deploy keys → Add deploy key. Yukarıdaki satırı yapıştır; "Allow write access" işaretsiz kalsın.
İlk bağlantıda GitHub'ın parmak izi sorulur, `yes` yaz.

```sh
# sudo -u forum git clone git@github.com:hasancomert/forum.git /srv/forum
# sudo -u forum python3 -m venv /srv/forum/.venv
# sudo -u forum /srv/forum/.venv/bin/python -m pip install -r /srv/forum/requirements.txt
```

## 6. Ayarlar (`.env`)

```sh
# cd /srv/forum
# sudo -u forum cp .env.example .env && chmod 600 .env
# sudo -u forum .venv/bin/python -c "from django.core.management.utils import get_random_secret_key as k; print(k())"
# sudo -u forum nano .env
```

Doldurulacaklar (açıklamaları `.env.example`'da):

| Ad | Değer |
|---|---|
| `DEBUG` | boş |
| `SECRET_KEY` | yukarıdaki komutun çıktısı |
| `ALLOWED_HOSTS` | `forum.com.tr,www.forum.com.tr` |
| `DATABASE_URL` | `postgres:///forum` |
| `HSTS_SECONDS` | ilk hafta `3600`; HTTPS sorunsuzsa satırı boşalt (1 yıl) |
| `EMAIL_*`, `DEFAULT_FROM_EMAIL` | 8. bölüm |
| `ADMINS` | 500 hatalarının gideceği adres |
| `TURNSTILE_*` | 9. bölüm |
| `SITE_OWNER`, `CONTACT_ADDRESS`, `CONTACT_EMAIL` | 5651 künye bilgileri (iletişim sayfası) |

## 7. İlk kurulum ve servisler

```sh
# cp /srv/forum/deploy/forum*.service /srv/forum/deploy/forum*.timer /etc/systemd/system/
# mkdir -p /etc/systemd/journald.conf.d && cp /srv/forum/deploy/journald-forum.conf /etc/systemd/journald.conf.d/forum.conf
# systemctl restart systemd-journald && systemctl daemon-reload
# /srv/forum/deploy/update.sh origin/main   # yedek, denetim, migrate, statik dosyalar, yeniden başlatma
# systemctl enable --now forum forum-finalize.timer forum-backup.timer
# sudo -u forum /srv/forum/.venv/bin/python /srv/forum/manage.py createsuperuser
```

Denetim: `systemctl status forum`, `systemctl list-timers 'forum*'`, `curl -I http://127.0.0.1:8000/` (301, HTTPS'e yönlendirir).

## 8. E-posta

Kayıt doğrulama ve şifre sıfırlama için bir SMTP hesabı gerekir (587, STARTTLS). Kodu etkilemez, yalnızca `.env` değişir:

- **Brevo** (ücretsiz, günde 300 e-posta, AB): `EMAIL_HOST=smtp-relay.brevo.com`, kullanıcı ve anahtar panelden. Veri yurt dışına çıkar: KVKK md. 9 standart sözleşmesi gerekir (10. bölüm).
- **Yurt içi:** alan adını aldığın firmanın kurumsal e-postası. Aktarım sorunu yok; teslim oranını dene.

Her iki durumda alan adının DNS'ine sağlayıcının verdiği SPF, DKIM ve DMARC kayıtlarını ekle; eklemezsen e-postalar gereksiz klasörüne düşer.

Deneme: `sudo -u forum /srv/forum/.venv/bin/python /srv/forum/manage.py sendtestemail senin@adresin`

## 9. CAPTCHA (Cloudflare Turnstile)

Cloudflare panelinde: Turnstile → Add widget → alan adını ekle, "Managed" türünü seç. Verilen site key ve secret key `.env`'deki `TURNSTILE_SITE_KEY` ve `TURNSTILE_SECRET_KEY`'e yazılır. Yayında boş bırakılırsa site açılmaz; bu bilerek böyle, test anahtarı herkesi geçirirdi.

## 10. Alan adı, DNS ve HTTPS

1. Bir alan adı al. `.com.tr` belgesiz alınabiliyor, `.com` da olur.
2. Firmanın DNS panelinde kayıtları ekle (ilk gün TTL 300):

   | Tür | Ad | Değer |
   |---|---|---|
   | A | `@` | SUNUCU_IPv4 |
   | AAAA | `@` | SUNUCU_IPv6 (varsa) |
   | CNAME | `www` | `forum.com.tr.` |

3. Caddy'yi ayarla:

   ```sh
   # sed 's/forum\.example/forum.com.tr/g' /srv/forum/deploy/Caddyfile > /etc/caddy/Caddyfile
   # install -d -o caddy -g caddy /var/log/caddy
   # systemctl reload caddy
   ```

4. DNS yayılınca (`PS> Resolve-DnsName forum.com.tr`) Caddy Let's Encrypt sertifikasını kendisi alır ve yeniler. Deneme: `PS> curl.exe -I https://forum.com.tr`
5. Bir hafta sorun çıkmazsa `.env`'de `HSTS_SECONDS`'u boşalt (1 yıl) ve `systemctl restart forum`. HSTS preload listesine başvuru (hstspreload.org) isteğe bağlı ve geri alması aylar sürer.

## 11. Güncelleme

Windows'ta:

```powershell
PS> python manage.py test
PS> git checkout main
PS> git merge --ff-only adim-11      # yayınlanacak dal; ya da GitHub'da pull request
PS> git tag v2026.09.25              # her yayın bir etiket: geri dönülecek nokta
PS> git push origin main --tags
PS> ssh root@SUNUCU_IP /srv/forum/deploy/update.sh v2026.09.25
```

`update.sh` önce yedek alır, sonra koda geçer, `check --deploy` ile denetler, migrate eder, statik dosyaları toplar ve yeniden başlatır. Denetim başarısız olursa durur ve eski sürüm çalışmaya devam eder.

## 12. Geri alma

- **Yeni sürümde migration yoksa:** `PS> ssh root@SUNUCU_IP /srv/forum/deploy/update.sh v2026.09.20`
- **Migration varsa:** önce veritabanını, güncellemeden hemen önce alınan yedeğe döndür, sonra eski sürüme geç:

  ```sh
  # ls -t /var/backups/forum | head -3            # en yenisi update.sh'nin aldığı yedek
  # systemctl stop forum
  # sudo -u forum pg_restore --clean --if-exists --dbname forum /var/backups/forum/forum-YYYYMMDD-HHMMSS.dump
  # /srv/forum/deploy/update.sh v2026.09.20
  ```

  Yedekten sonraki yorum ve oylar kaybolur. Kısa bir bakım duyurusuyla yap.

## 13. Yedekler

- Her gece 03:30'da ve her güncellemeden önce `pg_dump` alınır; 30 günden eskiler silinir.
- Sunucu dışında da kopya tut. Haftada bir Windows'a indir, eski kopyaları da 30 günde sil:

  ```powershell
  PS> scp "root@SUNUCU_IP:/var/backups/forum/forum-*.dump" D:\forum-yedek\
  ```

- Yedeği geri yüklemeyi ayda bir dene; denenmemiş yedek yedek sayılmaz:

  ```sh
  # sudo -u postgres createdb --owner forum forum_deneme
  # sudo -u forum pg_restore --dbname forum_deneme /var/backups/forum/forum-YYYYMMDD-HHMMSS.dump
  # sudo -u postgres dropdb forum_deneme
  ```

## 14. İzleme

```sh
# journalctl -u forum -f                          # uygulama hataları (500'ler ayrıca ADMINS'e e-postayla gelir)
# journalctl -u forum-finalize --since today      # zamanlayıcı
# tail -f /var/log/caddy/forum-access.log         # trafik kaydı
```

## 15. Yayından önce hukuki işler (uzman kontrolü gerekir)

- Hukuki metinlerdeki "taslak" notunu (`templates/legal/base.html`) ancak uzman kontrolünden sonra kaldır.
- **5651 yer sağlayıcı:**
  - İletişim sayfasındaki künye bilgileri doğru olmalı.
  - BTK'ya yer sağlayıcı bildirimi: ticari olmayan gerçek kişiye uygulanıp uygulanmadığı net değil, uzmana sor.
  - Trafik kaydı Caddy'de. Hedef IP sunucunun sabit IP'sidir, kayıtta ayrıca yazmaz.
  - Kaydın bütünlüğü için zaman damgası gerekip gerekmediğini uzmana sor.
- **KVKK md. 9 (yurt dışına aktarım):**
  - Cloudflare Turnstile (ABD) ve yurt dışı e-posta sağlayıcısı için Kurul'un standart sözleşmesini imzala.
  - İmzadan sonra 5 iş günü içinde Kurum'a bildir.
  - Sağlayıcı imzalamıyorsa yurt içi bir alternatife geç.
- **VERBİS:** çalışan sayısı 50'den az ve yıllık bilanço 100 milyon TL'den azsa kayıt gerekmez. Kontrol et.
- **Kuruluş:**
  1. Kurucu, admin'den ilk ana konuları açar ve yöneticileri işaretler. Trol ya da suç durumunda kendisi de
     müdahale edecekse kendi hesabını da yönetici işaretler: müdahale moderasyon sayfalarından yapılır ve
     herkese açık kayda düşer.
  2. Sonra `config/settings.py`'de `FORUM['FOUNDING'] = False` yapılıp güncellenir.
  3. Bundan sonra konu açma ve düzenleme yalnızca oylamayla olur; admin'de konular, rol ve yönetici alanları
     salt okunurdur. Öneriler admin'de hep salt okunur, oylar hiç görünmez (kural 6).
