"""
Django ayarları. Ortama göre değişen her şey ortam değişkeninden okunur (liste: .env.example);
geliştirmede bunlar proje kökündeki .env dosyasından gelir. Gerçek değerler repoya girmez.
https://docs.djangoproject.com/en/6.1/ref/settings/
"""

import os
from pathlib import Path
from urllib.parse import unquote, urlsplit

from django.core.exceptions import ImproperlyConfigured
from django.utils.csp import CSP

BASE_DIR = Path(__file__).resolve().parent.parent


def load_env(path):
    """.env'deki AD=değer satırlarını ortam değişkenine yazar (python-dotenv'in küçük karşılığı).
    Gerçekten tanımlı ortam değişkeni önceliklidir: sunucuda systemd'nin verdiği değer ezilmez.
    utf-8-sig: Windows'ta Not Defteri'nin eklediği BOM ilk adı bozmasın.
    """
    if not path.exists():
        return
    for line in path.read_text(encoding='utf-8-sig').splitlines():
        key, sep, value = line.strip().partition('=')
        if sep and not key.startswith('#'):
            os.environ.setdefault(key.strip(), value.strip().strip('\'"'))


def env_bool(name):
    return os.environ.get(name, '').lower() in ('1', 'true', 'yes', 'on')


def env_list(name):
    """Virgülle ayrılmış liste: 'a.com, b.com' -> ['a.com', 'b.com']."""
    return [x.strip() for x in os.environ.get(name, '').split(',') if x.strip()]


def database(url):
    """DATABASE_URL -> DATABASES girdisi. Boşsa SQLite (geliştirme). Sunucuda 'postgres:///forum':
    sunucu adı yok = Unix soketi, şifre yok = PostgreSQL işletim sistemi kullanıcısını tanır (peer).
    """
    if not url:
        return {'ENGINE': 'django.db.backends.sqlite3', 'NAME': BASE_DIR / 'db.sqlite3'}
    u = urlsplit(url)
    if u.scheme not in ('postgres', 'postgresql'):
        raise ImproperlyConfigured('DATABASE_URL yalnızca postgres:// olabilir.')
    return {
        'ENGINE': 'django.db.backends.postgresql', 'NAME': u.path.lstrip('/'),
        'USER': unquote(u.username or ''), 'PASSWORD': unquote(u.password or ''),
        'HOST': u.hostname or '', 'PORT': u.port or '',
        'CONN_MAX_AGE': 60, 'CONN_HEALTH_CHECKS': True,  # bağlantı istekler arasında yeniden kullanılır
    }


load_env(BASE_DIR / '.env')
DEBUG = env_bool('DEBUG')  # yoksa False: unutulan ayar yayında hata ayıklama sayfası açmasın


def required(name, dev_default):
    """Yayında zorunlu değer; yalnızca geliştirmede (DEBUG) yoksa dev_default kullanılır."""
    value = os.environ.get(name) or (dev_default if DEBUG else '')
    if not value:
        raise ImproperlyConfigured(f'{name} ortam değişkeni gerekli (.env.example).')
    return value


SECRET_KEY = required('SECRET_KEY', 'django-insecure-yalnizca-gelistirme')
# DEBUG'da boşsa her ad: telefon (mobil uygulama) bilgisayara yerel ağ IP'siyle bağlanır (runserver 0.0.0.0:8000)
ALLOWED_HOSTS = env_list('ALLOWED_HOSTS') or (['*'] if DEBUG else [])
CSRF_TRUSTED_ORIGINS = env_list('CSRF_TRUSTED_ORIGINS')  # yalnızca başka bir alan adından form gelecekse

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'accounts',
    'topics',
    'voting',
    'comments',
    'moderation',
    'api',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',  # statik dosyalar Django'dan, ayrı sunucu gerekmez
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'django.middleware.csp.ContentSecurityPolicyMiddleware',  # SECURE_CSP boşsa başlık eklemez
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
            'builtins': ['config.templatetags'],  # Türkçe capfirst ({% load %} gerekmez)
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

DATABASES = {'default': database(os.environ.get('DATABASE_URL'))}

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'tr'
TIME_ZONE = 'Europe/Istanbul'
USE_I18N = True
USE_TZ = True

# Statik dosyalar: yayında collectstatic STATIC_ROOT'a toplar; WhiteNoise sıkıştırır ve adlara içerik
# hash'i ekler (site.4f2a….css), böylece tarayıcı dosyayı süresiz önbellekleyebilir.
STATIC_URL = 'static/'
STATIC_ROOT = None if DEBUG else BASE_DIR / 'staticfiles'  # geliştirmede dosyalar doğrudan static/'ten
STATICFILES_DIRS = [BASE_DIR / 'static']
STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage' if DEBUG
                    else 'whitenoise.storage.CompressedManifestStaticFilesStorage'},
}

# HTTPS: sertifikayı önündeki Caddy çözer, Django'ya X-Forwarded-Proto başlığıyla bildirir. gunicorn
# yalnızca yerelden dinlediği için bu başlığı dışarıdan kimse sahteleyemez.
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = int(os.environ.get('HSTS_SECONDS') or 31536000)  # 1 yıl; ilk yayında küçük başla
    SECURE_HSTS_INCLUDE_SUBDOMAINS = SECURE_HSTS_PRELOAD = True
    # CSP: yalnızca kendi dosyalarımız (satır içi script/stil yok) ve Turnstile. Geliştirmede kapalı:
    # Django'nun hata ayıklama sayfası satır içi stil kullanır.
    SECURE_CSP = {
        'default-src': [CSP.SELF], 'script-src': [CSP.SELF, 'https://challenges.cloudflare.com'],
        'frame-src': ['https://challenges.cloudflare.com'], 'object-src': [CSP.NONE], 'base-uri': [CSP.NONE],
        'form-action': [CSP.SELF], 'frame-ancestors': [CSP.NONE],
    }

# E-posta (Django 6.1 MAILERS). EMAIL_HOST yoksa konsola yazar; yayında check --deploy bunu hata sayar.
MAILERS = {'default': {
    'BACKEND': 'django.core.mail.backends.smtp.EmailBackend',
    'OPTIONS': {
        'host': os.environ['EMAIL_HOST'], 'port': int(os.environ.get('EMAIL_PORT') or 587),
        'username': os.environ.get('EMAIL_USER', ''), 'password': os.environ.get('EMAIL_PASSWORD', ''),
        'use_tls': True,  # 587 + STARTTLS
    },
} if os.environ.get('EMAIL_HOST') else {'BACKEND': 'django.core.mail.backends.console.EmailBackend'}}
DEFAULT_FROM_EMAIL = SERVER_EMAIL = os.environ.get('DEFAULT_FROM_EMAIL') or 'webmaster@localhost'
EMAIL_SUBJECT_PREFIX = '[Forum] '

# Hata kaydı: 500 hataları ADMINS'e e-postayla gider (Django'nun hazır mail_admins'i, DEBUG kapalıyken);
# uyarı ve hatalar ayrıca konsola yazılır, sunucuda journald toplar (journalctl -u forum).
ADMINS = env_list('ADMINS')
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'filters': {'require_debug_false': {'()': 'django.utils.log.RequireDebugFalse'}},
    'handlers': {'console': {'class': 'logging.StreamHandler', 'filters': ['require_debug_false']}},
    'root': {'handlers': ['console'], 'level': 'WARNING'},
}

# Kullanıcılar
AUTH_USER_MODEL = 'accounts.User'
LOGIN_REDIRECT_URL = LOGOUT_REDIRECT_URL = 'home'

# Cloudflare Turnstile (CAPTCHA). Geliştirmede Cloudflare'in her zaman geçen test anahtarları;
# yayında gerçekleri zorunlu (unutulursa test anahtarı sessizce herkesi geçirmesin).
TURNSTILE_SITE_KEY = required('TURNSTILE_SITE_KEY', '1x00000000000000000000AA')
TURNSTILE_SECRET_KEY = required('TURNSTILE_SECRET_KEY', '1x0000000000000000000000000000000AA')

# 5651 md. 3 tanıtıcı bilgiler ve KVKK veri sorumlusu: iletişim sayfasında ve hukuki metinlerde görünür.
SITE = {
    'owner': required('SITE_OWNER', 'Ad Soyad (geliştirme)'),  # gerçek kişiyse ad soyad, şirketse unvan
    'address': required('CONTACT_ADDRESS', 'Adres (geliştirme)'),
    'email': required('CONTACT_EMAIL', 'iletisim@example.com'),  # hukuki bildirim ve KVKK başvurusu
}

# Forum kuralları (CLAUDE.md > Kurallar). Kural sayıları yalnızca burada tutulur; açılışta denetlenir
# (voting/checks.py: yanlış girilen değer runserver ve check --deploy'da hata verir, sayfada 500 değil).
FORUM = {
    'VOTE_WEIGHT': {'A': 1, 'B': 10},  # kural 2: rol -> karar oylamasındaki ağırlık
    'MIN_ACCOUNT_AGE_DAYS': 7,  # kural 1: oy hakkı için hesap yaşı
    'ACTIVE_DAYS': 30,  # kural 3: aktif üye penceresi
    'QUORUM_PERCENT': 10,  # kural 3: son 30 günde aktif üyelerin %10'u
    'QUORUM_MIN': 5,  # kural 3: en az 5 kişi
    'EXPERT_APPROVAL_NUM': 2,  # kural 2: B statüsü başvurusu 2/3 evet gerekir
    'EXPERT_APPROVAL_DEN': 3,
    'PROPOSAL_VOTING_DAYS': 2,  # kural 5: açma/düzenleme/kapatma/silme/geri alma önerileri
    'REQUEST_DISCUSSION_DAYS': 3,  # kural 5: istekler için tartışma süresi
    'REQUEST_VOTING_DAYS': 3,  # kural 5: istekler için oylama süresi
    'MAX_OPEN_PROPOSALS': 3,  # kural 8: kişi başı en fazla açık öneri
    'REJECTED_COOLDOWN_DAYS': 30,  # kural 8: reddedilen öneri bu kadar gün yeniden açılamaz
    'COMMENT_MAX_LENGTH': 5000,  # yorum uzunluk sınırı; değişirse makemigrations (yalnızca form denetimi değişir)
    'POPULAR_DAYS': 7,  # "en popüler": son kaç günün etkinliği
    'POPULAR_WEIGHTS': {'comment': 3, 'vote': 1},  # yorum ve oy (yorum oyu + konu oyu) katsayıları
    'TOPICS_PER_PAGE': 20,  # konu listeleri
    'COMMENTS_PER_PAGE': 20,  # ana yorum; yanıtlar ana yorumlarıyla aynı sayfada
    'PANEL_VOTING': 10,  # ana sayfa panelinde en fazla oylamadaki öneri
    'PANEL_DISCUSSION': 5,  # panelde en fazla tartışmadaki istek
    'COMMENT_RATE': (5, 10),  # hız sınırı: 10 dakikada en fazla 5 yorum
    'MOD_NOTE_MAX_LENGTH': 200,  # moderasyon işleminin herkese açık notu; değişirse makemigrations
    'BAN_DAYS': (1, 7, 30, 365),  # seçilebilen engel süreleri (gün); kalıcı engel yok, sahte hesap kapatılır
    'MOD_PER_PAGE': 50,  # moderasyon kaydı ve şikayet kuyruğu
    'REPORT_RATE': (10, 60),  # hız sınırı: 60 dakikada en fazla 10 şikayet
    'API_TOKEN_DAYS': 30,  # mobil uygulamanın giriş jetonu bu kadar gün geçerli (şifre değişince hemen biter)
    'FOUNDING': True,  # kural 9: kuruluş sürüyor; False olunca admin'den konu eklenemez, rol ve yönetici salt okunur
}
