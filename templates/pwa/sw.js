{% load static %}// Service worker: yalnızca statik dosyaları ve çevrimdışı sayfasını önbelleğe alır. Sayfalar (HTML) ve
// kişiye özel yanıtlar hep ağdan gelir, önbelleğe girmez; POST'lara (oy, yorum) hiç dokunulmaz.
// Yayında statik adlar içerik hash'i taşır (site.4f2a9c1b7e3d.css): bir dosya değişince bu metin ve önbellek
// adı da değişir, tarayıcı yeni service worker'ı kurar, eski önbelleği siler.
const OFFLINE = '{% url "offline" %}';
const PRECACHE = [OFFLINE, '{% static "css/site.css" %}', '{% static "js/site.js" %}', '{% static "img/logo.svg" %}'];
const CACHE = 'forum ' + PRECACHE.join(' ');
const HASHED = /\.[0-9a-f]{12}\.\w+$/;  // değişmeyen dosya; geliştirmedeki hash'siz adlar hep ağdan

self.addEventListener('install', (event) => {
  event.waitUntil(caches.open(CACHE).then((cache) => cache.addAll(PRECACHE)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', (event) => {
  event.waitUntil(caches.keys()
    .then((keys) => Promise.all(keys.filter((key) => key !== CACHE).map((key) => caches.delete(key))))
    .then(() => self.clients.claim()));
});

self.addEventListener('fetch', (event) => {
  const request = event.request;
  const url = new URL(request.url);
  if (request.method !== 'GET' || url.origin !== location.origin) return;
  if (request.mode === 'navigate') {  // sayfa: ağdan; ağ yoksa çevrimdışı sayfası
    event.respondWith(fetch(request).catch(() => caches.match(OFFLINE)));
  } else if (HASHED.test(url.pathname)) {  // hash'li statik dosya: önce önbellek
    event.respondWith(caches.match(request).then((hit) => hit || fetch(request).then((response) => {
      if (response.ok) {
        const copy = response.clone();
        caches.open(CACHE).then((cache) => cache.put(request, copy));
      }
      return response;
    })));
  }
});
