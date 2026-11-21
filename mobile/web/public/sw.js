const CACHE = 'validat3b-campo-v3';

self.addEventListener('install', (event) => {
  event.waitUntil((async () => {
    const response = await fetch('/', { cache: 'reload' });
    if (!response.ok) throw new Error('No se pudo guardar la app para uso sin conexión.');
    const html = await response.clone().text();
    const assets = [...html.matchAll(/(?:src|href)="(\/assets\/[^"]+)"/g)].map((match) => match[1]);
    const cache = await caches.open(CACHE);
    await cache.addAll(['/manifest.webmanifest', '/icon.svg', ...assets]);
    await cache.put('/', response);
    await self.skipWaiting();
  })());
});

self.addEventListener('activate', (event) => {
  event.waitUntil((async () => {
    const names = await caches.keys();
    await Promise.all(names.filter((name) => name.startsWith('validat3b-campo-') && name !== CACHE)
      .map((name) => caches.delete(name)));
    await self.clients.claim();
  })());
});

self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);
  if (request.method !== 'GET' || url.origin !== self.location.origin) return;
  if (request.mode === 'navigate' && ['/', '/revisar', '/comparar', '/corregidos'].includes(url.pathname)) {
    event.respondWith((async () => {
      try {
        const response = await fetch(request);
        if (response.ok) {
          const cache = await caches.open(CACHE);
          await cache.put('/', response.clone());
        }
        return response;
      } catch {
        return (await caches.match('/')) || Response.error();
      }
    })());
  } else if (url.pathname.startsWith('/assets/')) {
    event.respondWith((async () => {
      const cache = await caches.open(CACHE);
      const cached = await cache.match(request);
      if (cached) return cached;
      const response = await fetch(request);
      if (response.ok) await cache.put(request, response.clone());
      return response;
    })());
  }
});
