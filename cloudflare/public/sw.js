// Keeps the app's shell on the phone so it opens instantly and without a
// network. Notes are never stored here: /api and the bot are never touched,
// so nothing private is cached and a revoked device sees nothing.
const CACHE = 'np-shell-v1';
const SHELL = ['/app', '/app.css', '/app.js', '/manifest.webmanifest', '/icon-192.png',
  '/fonts/Vazirmatn-Regular.ttf', '/fonts/Vazirmatn-Medium.ttf', '/fonts/Vazirmatn-SemiBold.ttf', '/fonts/Vazirmatn-Bold.ttf'];

self.addEventListener('install', event => {
  event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', event => {
  event.waitUntil(caches.keys()
    .then(keys => Promise.all(keys.filter(key => key !== CACHE).map(key => caches.delete(key))))
    .then(() => self.clients.claim()));
});

self.addEventListener('fetch', event => {
  const { request } = event;
  const url = new URL(request.url);
  if (request.method !== 'GET' || url.origin !== self.location.origin ||
      url.pathname.startsWith('/api/') || url.pathname.startsWith('/telegram/') || url.pathname === '/health') return;
  // Fonts and icons never change under the same name: cache first.
  // The page, script and style: network first, so a new release shows at once.
  const fixed = /\.(ttf|png)$/.test(url.pathname);
  event.respondWith(fixed ? cacheFirst(request) : networkFirst(request));
});

async function cacheFirst(request) {
  const cached = await caches.match(request);
  if (cached) return cached;
  const response = await fetch(request);
  if (response.ok) (await caches.open(CACHE)).put(request, response.clone());
  return response;
}

async function networkFirst(request) {
  try {
    const response = await fetch(request);
    if (response.ok) (await caches.open(CACHE)).put(request, response.clone());
    return response;
  } catch (error) {
    const cached = await caches.match(request);
    if (cached) return cached;
    throw error;
  }
}
