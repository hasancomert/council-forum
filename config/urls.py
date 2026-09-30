from django.conf import settings
from django.contrib import admin
from django.shortcuts import redirect
from django.templatetags.static import static
from django.urls import include, path
from django.views.generic import TemplateView


def page(template, **kwargs):
    """Görünüm kodu gerekmeyen sayfa: şablon olduğu gibi render edilir (Django'nun hazır TemplateView'ı)."""
    return TemplateView.as_view(template_name=template, **kwargs)


# Hukuki metinler: adres -> (ad, başlık). Sayılar metne FORUM'dan, künye SITE'tan gelir.
LEGAL = {
    'kullanim-sartlari': ('terms', 'Kullanım şartları'),
    'kvkk': ('privacy', 'KVKK aydınlatma metni'),
    'cerezler': ('cookies', 'Çerez bilgisi'),
    'iletisim': ('contact', 'İletişim ve künye'),
}


urlpatterns = [
    path('', include('topics.urls')),
    path('', include('voting.urls')),
    path('', include('comments.urls')),
    path('', include('moderation.urls')),
    path('accounts/', include('accounts.urls')),
    path('api/', include('api.urls')),  # mobil uygulama (JSON)
    path('admin/', admin.site.urls),
    # PWA: service worker kökten sunulur ki kapsamı bütün site olsun (/static/ altından yalnızca /static/'i kapsardı)
    path('sw.js', page('pwa/sw.js', content_type='text/javascript'), name='sw'),
    path('manifest.webmanifest', page('pwa/manifest.webmanifest', content_type='application/manifest+json'),
         name='manifest'),
    path('offline/', page('pwa/offline.html'), name='offline'),
    path('favicon.ico', lambda request: redirect(static('img/icon-192.png'))),  # <link rel=icon> okumayan istemciler
] + [
    path(f'{slug}/', page(f'legal/{name}.html', extra_context={'title': title, 'site': settings.SITE,
                                                              'forum': settings.FORUM}), name=name)
    for slug, (name, title) in LEGAL.items()
]
