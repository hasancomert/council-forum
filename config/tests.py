import os
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.core.exceptions import ImproperlyConfigured
from django.core.management.utils import get_random_secret_key
from django.template.loader import render_to_string
from django.test import Client, SimpleTestCase, TestCase

from topics.models import Topic

from .settings import BASE_DIR, database, env_list, load_env

# Yayın ortamı: .env'deki geliştirme değerleri (DEBUG=1) bunları ezemez, gerçek ortam değişkeni önceliklidir.
PROD = {'DEBUG': '0', 'SECRET_KEY': get_random_secret_key(), 'ALLOWED_HOSTS': 'forum.example',
        'EMAIL_HOST': 'smtp.example', 'TURNSTILE_SITE_KEY': 'site', 'TURNSTILE_SECRET_KEY': 'gizli',
        'DATABASE_URL': '', 'HSTS_SECONDS': ''}


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
