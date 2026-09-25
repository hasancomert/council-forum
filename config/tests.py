import os
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from datetime import timedelta
from unittest.mock import patch

from django.contrib.staticfiles import finders
from django.core.exceptions import ImproperlyConfigured
from django.core.management.utils import get_random_secret_key
from django.template import Context, Template
from django.template.loader import render_to_string
from django.test import Client, SimpleTestCase, TestCase
from django.utils import timezone

from accounts.models import User
from topics.models import Topic

from .settings import BASE_DIR, database, env_list, load_env
from .templatetags import ago, left, span

# Yayın ortamı: .env'deki geliştirme değerleri (DEBUG=1) bunları ezemez, gerçek ortam değişkeni önceliklidir.
PROD = {'DEBUG': '0', 'SECRET_KEY': get_random_secret_key(), 'ALLOWED_HOSTS': 'forum.example',
        'EMAIL_HOST': 'smtp.example', 'TURNSTILE_SITE_KEY': 'site', 'TURNSTILE_SECRET_KEY': 'gizli',
        'DATABASE_URL': '', 'HSTS_SECONDS': '', 'SITE_OWNER': 'Ad Soyad', 'CONTACT_ADDRESS': 'Adres',
        'CONTACT_EMAIL': 'iletisim@forum.example'}


def manage(*args, **env):
    return subprocess.run([sys.executable, 'manage.py', *args], cwd=BASE_DIR, env=os.environ | PROD | env,
                          capture_output=True, text=True)


class EnvTests(SimpleTestCase):
    def test_load_env_keeps_real_variables(self):
        with TemporaryDirectory() as d, patch.dict(os.environ, {'FORUM_T_REAL': 'gerçek'}):
            path = Path(d) / '.env'
            path.write_text('﻿FORUM_T_A=1\n# FORUM_T_B=2\nFORUM_T_REAL=dosya\n FORUM_T_C = "tırnaklı"\n',
                            encoding='utf-8')
            load_env(path)
            got = [os.environ.get(f'FORUM_T_{k}') for k in 'ABC'] + [os.environ['FORUM_T_REAL']]
            for k in 'AC':
                os.environ.pop(f'FORUM_T_{k}', None)
        self.assertEqual(got, ['1', None, 'tırnaklı', 'gerçek'])  # BOM, yorum, tırnak; gerçek değer ezilmez

    def test_lists_and_database_url(self):
        with patch.dict(os.environ, {'FORUM_T': ' a.com, ,b.com '}):
            self.assertEqual(env_list('FORUM_T'), ['a.com', 'b.com'])
        self.assertEqual(database('')['ENGINE'], 'django.db.backends.sqlite3')
        db = database('postgres://ali:%C5%9Fifre@db.local:5433/forum')
        self.assertEqual([db[k] for k in ('NAME', 'USER', 'PASSWORD', 'HOST', 'PORT')],
                         ['forum', 'ali', 'şifre', 'db.local', 5433])
        self.assertEqual(database('postgres:///forum')['HOST'], '')  # Unix soketi
        with self.assertRaises(ImproperlyConfigured):
            database('mysql://x/forum')

    def test_deploy_check_passes(self):
        r = manage('check', '--deploy', '--fail-level', 'WARNING')
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_production_requires_secrets(self):
        r = manage('check', SECRET_KEY='')
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('SECRET_KEY ortam değişkeni gerekli', r.stderr)


class PageTests(TestCase):
    def test_error_pages(self):
        self.assertContains(self.client.get('/yok/'), 'Sayfa bulunamadı', status_code=404)
        r = Client(enforce_csrf_checks=True).post('/accounts/login/')
        self.assertContains(r, 'Form gönderilemedi', status_code=403)
        self.assertIn('Bir şeyler ters gitti', render_to_string('500.html'))  # istek ve veritabanı olmadan

    def test_no_inline_styles_or_scripts(self):
        """Yayındaki CSP yalnızca dosyadan stil ve script'e izin verir: şablonlarda satır içi olan kalmamalı."""
        topic = Topic.objects.create(title='Konu')
        for url in ('/', topic.get_absolute_url(), '/accounts/signup/', '/mod/log/', '/yok/'):
            self.assertNotRegex(self.client.get(url).content.decode(), r'style=|<style|<script>', url)


class TemplateFilterTests(SimpleTestCase):
    def test_turkish_capfirst_overrides_builtin(self):
        self.assertEqual(Template('{{ "istek"|capfirst }} {{ "ılık"|capfirst }}').render(Context()), 'İstek Ilık')

    def test_short_durations(self):
        h, d = 3600, 86400
        cases = {14 * 60: '14 dk', h + 14 * 60: '1 sa 14 dk', 2 * h: '2 sa', 3 * h + 300: '3 sa', 23 * h: '23 sa',
                 d: '1 gün', 30 * h: '1 gün 6 sa', 48 * h: '2 gün', 29 * d: '29 gün', 30 * d: '1 ay',
                 300 * d: '10 ay', 3 * 365 * d + 200 * d: '3 yıl'}
        self.assertEqual({s: span(s) for s in cases}, cases)
        now = timezone.now()
        self.assertEqual((ago(now), ago(now - timedelta(hours=5)), left(now + timedelta(days=1, hours=22, seconds=30))),
                         ('az önce', '5 sa önce', '1 gün 22 sa'))


class PwaTests(TestCase):
    def test_manifest_and_icons(self):
        r = self.client.get('/manifest.webmanifest')
        self.assertEqual(r['Content-Type'], 'application/manifest+json')
        m = r.json()
        self.assertEqual((m['start_url'], m['scope'], m['display']), ('/', '/', 'standalone'))
        self.assertTrue({'192x192', '512x512'} <= {i['sizes'] for i in m['icons']})  # yüklenebilirlik için
        for icon in m['icons']:
            self.assertTrue(finders.find(icon['src'].removeprefix('/static/')), icon['src'])
        page = self.client.get('/')
        self.assertContains(page, 'rel="manifest" href="/manifest.webmanifest"')
        self.assertContains(page, 'name="theme-color"', count=2)  # açık ve koyu tema

    def test_service_worker_from_root_caches_only_static_and_offline(self):
        r = self.client.get('/sw.js')
        self.assertEqual((r.status_code, r['Content-Type']), (200, 'text/javascript'))
        sw = r.content.decode()
        self.assertIn("const OFFLINE = '/offline/';", sw)
        self.assertIn('/static/css/site.css', sw)
        self.assertIn("request.method !== 'GET'", sw)  # POST (oy, yorum) hiç önbelleğe girmez

    def test_offline_page_is_not_personal(self):
        """Service worker bu sayfayı önbelleğe alır: giriş yapmış kullanıcının adı ve oturumu içinde olmamalı."""
        self.client.force_login(User.objects.create_user('gizliad', email='g@example.com'))
        r = self.client.get('/offline/')
        self.assertContains(r, 'Bağlantı yok')
        self.assertNotContains(r, 'gizliad')
        self.assertNotIn('Cookie', r.get('Vary', ''))  # yanıt oturuma göre değişmiyor
