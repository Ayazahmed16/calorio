// Calorio service worker: caches the app shell and the pages you have visited, so the last
// state of your day opens offline. Everything is network-first so data is never stale online.
const VERSION = 'calorio-v1';
const SHELL = ['/offline/', '/static/tracker/icons/icon-192.png'];

self.addEventListener('install', (event) => {
    event.waitUntil(caches.open(VERSION).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', (event) => {
    event.waitUntil(
        caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== VERSION).map((k) => caches.delete(k))))
            .then(() => self.clients.claim())
    );
});

// On logout the page asks us to forget everything, so private pages never linger on a shared device.
self.addEventListener('message', (event) => {
    if (event.data === 'clear') event.waitUntil(caches.delete(VERSION).then(() => caches.open(VERSION)).then((c) => c.addAll(SHELL)));
});

self.addEventListener('fetch', (event) => {
    const req = event.request;
    const url = new URL(req.url);
    if (req.method !== 'GET' || url.origin !== location.origin) return;
    if (url.pathname.startsWith('/api/') || url.pathname.startsWith('/admin/') || url.pathname === '/sw.js') return;

    const isPage = req.mode === 'navigate';
    event.respondWith(
        fetch(req).then((res) => {
            if (res.ok && res.type === 'basic' && !res.redirected) {
                const copy = res.clone();
                caches.open(VERSION).then((c) => c.put(req, copy));
            }
            return res;
        }).catch(() =>
            caches.match(req).then((hit) => hit || (isPage ? caches.match('/offline/') : Response.error()))
        )
    );
});
