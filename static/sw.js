const CACHE_NAME = 'aura-v1';
const ASSETS = [
    '/static/play.html',
    '/static/app.js',
    '/static/friend-room-client.js'
];

self.addEventListener('install', (event) => {
    event.waitUntil(
        caches.open(CACHE_NAME).then((cache) => {
            return cache.addAll(ASSETS);
        })
    );
});

self.addEventListener('fetch', (event) => {
    // Simple network-first strategy
    event.respondWith(
        fetch(event.request).catch(() => {
            return caches.match(event.request);
        })
    );
});

// Media Session API handlers can be added here if needed for more complex background logic,
// but usually, they are handled in the main thread.
