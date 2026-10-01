const CACHE_NAME = 'ilovevoley-pwa-v1';
const PRECACHE_URLS = [
    '/offline/',
    '/static/css/app.css',
    '/static/js/csp_actions.js',
    '/static/images/logo_app.png',
    '/static/images/icons/icon-192.png',
    '/static/images/icons/icon-512.png',
];

self.addEventListener('install', (event) => {
    event.waitUntil(
        caches.open(CACHE_NAME).then((cache) =>
            // Cada asset se precachea por separado: si uno falla (renombrado,
            // ausente tras collectstatic) no aborta el install entero.
            Promise.all(
                PRECACHE_URLS.map((url) =>
                    cache.add(url).catch(() => undefined)
                )
            )
        )
    );
});

self.addEventListener('activate', (event) => {
    event.waitUntil(
        caches.keys().then((keys) =>
            Promise.all(
                keys
                    .filter((key) => key.startsWith('ilovevoley-pwa-') && key !== CACHE_NAME)
                    .map((key) => caches.delete(key))
            )
        )
    );
});

self.addEventListener('fetch', (event) => {
    if (event.request.method !== 'GET') {
        return;
    }

    const url = new URL(event.request.url);
    if (url.origin !== self.location.origin) {
        return;
    }

    const pathname = url.pathname;

    // Rutas dinámicas, datos privados o endpoints de control: siempre red directa
    if (
        pathname.startsWith('/media/') ||
        pathname.startsWith('/protected-media/') ||
        pathname.startsWith('/accounts/') ||
        pathname.startsWith('/admin/') ||
        pathname.startsWith('/api/') ||
        pathname === '/manifest.webmanifest' ||
        pathname === '/sw.js'
    ) {
        return;
    }

    // Peticiones de navegación: network-first con fallback offline exclusivo ante fallo de red
    if (event.request.mode === 'navigate') {
        event.respondWith(
            fetch(event.request).catch(() => caches.match('/offline/'))
        );
        return;
    }

    // Archivos estáticos: Stale-While-Revalidate para respuestas 200 OK del mismo origen
    if (pathname.startsWith('/static/')) {
        event.respondWith(
            caches.match(event.request).then((cachedResponse) => {
                const fetchPromise = fetch(event.request)
                    .then((networkResponse) => {
                        if (networkResponse && networkResponse.status === 200) {
                            const responseClone = networkResponse.clone();
                            caches.open(CACHE_NAME).then((cache) => {
                                cache.put(event.request, responseClone);
                            });
                        }
                        return networkResponse;
                    })
                    .catch(() => cachedResponse);

                return cachedResponse || fetchPromise;
            })
        );
    }
});

// --- Push Notifications & App Badging API ---

self.addEventListener('push', (event) => {
    let data = {};
    if (event.data) {
        try {
            data = event.data.json();
        } catch (e) {
            data = { title: 'I Love Voley', body: event.data.text() };
        }
    }

    const title = data.title || 'I Love Voley';
    const options = {
        body: data.body || '',
        icon: data.icon || '/static/images/icons/icon-192.png',
        badge: data.badge || '/static/images/icons/icon-192.png',
        data: {
            url: data.url || '/',
            badge_count: data.badge_count,
        },
        tag: data.tag || undefined,
        renotify: Boolean(data.renotify),
    };

    const promises = [
        self.registration.showNotification(title, options)
    ];

    if ('setAppBadge' in navigator && typeof data.badge_count === 'number') {
        promises.push(
            (data.badge_count > 0 ? navigator.setAppBadge(data.badge_count) : navigator.clearAppBadge())
                .catch(() => {})
        );
    }

    event.waitUntil(Promise.all(promises));
});

self.addEventListener('notificationclick', (event) => {
    event.notification.close();

    if ('clearAppBadge' in navigator) {
        navigator.clearAppBadge().catch(() => {});
    }

    // Solo URLs del propio origen; cualquier otra cae en la portada
    const requested = new URL((event.notification.data && event.notification.data.url) || '/', self.location.origin);
    const fullTargetUrl = requested.origin === self.location.origin ? requested.href : self.location.origin + '/';

    event.waitUntil(
        clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clientList) => {
            // Reutiliza una ventana abierta de la app en vez de abrir otra
            const client = clientList.find((c) => 'focus' in c);
            if (client) {
                return client.focus().then((focused) => (focused && 'navigate' in focused ? focused.navigate(fullTargetUrl) : null));
            }
            if (clients.openWindow) {
                return clients.openWindow(fullTargetUrl);
            }
        })
    );
});

