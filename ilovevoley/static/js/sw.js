importScripts('/static/js/upload_queue_blob.js');

// Subir la versión cuando cambie /offline/: el navegador solo reinstala el SW (y refresca el precaché) si sw.js cambia.
// Fuentes y logo no se precachean: en producción se piden con hash y el SWR de /static/ los guarda al usarlos.
const CACHE_NAME = 'ilovevoley-pwa-v3';
// Páginas HTML privadas (requieren sesión) servidas sin red. Se vacía en logout/login (offline_pages.js)
// y al subir PAGES_CACHE_NAME. Lista blanca explícita: nada fuera de PAGE_CACHE_PATHS se guarda.
const PAGES_CACHE_NAME = 'ilovevoley-pwa-pages-v1';
const PAGE_CACHE_PATHS = [/^\/finde\/$/, /^\/partidos\/\d+\/$/];
const PAGES_MAX_ENTRIES = 30;
const PREFETCH_MAX_MATCHES = 10;
const PAGES_MAX_AGE_MS = 7 * 24 * 60 * 60 * 1000;
const PRECACHE_URLS = [
    '/offline/',
    '/static/css/app.css',
    '/static/js/csp_actions.js',
    '/static/js/pwa_nav.js',
    '/static/js/pwa_install.js',
    '/static/js/upload_queue_blob.js',
    '/static/js/upload_queue.js',
    '/static/js/offline_pages.js',
    '/static/images/logo_app.png',
    '/static/images/icons/icon-192.png',
    '/static/images/icons/icon-512.png',
    '/static/images/icons/shortcut-matches.png',
    '/static/images/icons/shortcut-photos.png',
    '/static/images/icons/shortcut-notifications.png',
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
                    .filter((key) => key.startsWith('ilovevoley-pwa-') && key !== CACHE_NAME && key !== PAGES_CACHE_NAME)
                    .map((key) => caches.delete(key))
            )
        )
    );
});

async function trimPagesCache(cache) {
    const keys = await cache.keys();
    // keys() devuelve el orden de inserción: se descartan las más antiguas
    await Promise.all(keys.slice(0, Math.max(0, keys.length - PAGES_MAX_ENTRIES)).map((k) => cache.delete(k)));
}

// Un login caducado redirige (200 final en /accounts/login/): solo se guardan respuestas directas
async function storePage(cache, request, response) {
    if (!response.ok || response.redirected || response.type !== 'basic') {
        return false;
    }
    const stored = new Response(await response.clone().blob(), {
        headers: { 'Content-Type': response.headers.get('Content-Type') || 'text/html; charset=utf-8', 'X-SW-Cached-At': String(Date.now()) },
    });
    await cache.put(request, stored);
    return true;
}

// Al abrir «Este finde» con red se guardan también las fichas de partido que enlaza,
// que es lo que se consulta en el pabellón sin cobertura.
async function prefetchMatchPages(cache, html) {
    const paths = [...new Set(html.match(/\/partidos\/\d+\//g) || [])].slice(0, PREFETCH_MAX_MATCHES);
    await Promise.all(paths.map((path) =>
        fetch(path).then((response) => storePage(cache, new Request(path), response)).catch(() => undefined)
    ));
    await trimPagesCache(cache);
}

// Red primero (datos frescos con cobertura) y, sin red, la última copia con su fecha en un <meta>
// que offline_pages.js convierte en el aviso «datos de hace X».
async function pageNetworkFirst(event) {
    const pathname = new URL(event.request.url).pathname;
    // Clave sin query string: /finde/?x se reutiliza al abrir /finde/ (las fichas con query ni llegan aquí)
    const key = new Request(self.location.origin + pathname);
    const cache = await caches.open(PAGES_CACHE_NAME);
    try {
        const response = await fetch(event.request);
        if (await storePage(cache, key, response)) {
            if (pathname === '/finde/') {
                event.waitUntil(response.clone().text().then((html) => prefetchMatchPages(cache, html)));
            } else {
                await trimPagesCache(cache);
            }
        }
        return response;
    } catch (err) {
        const cached = await cache.match(key);
        const cachedAt = cached ? Number(cached.headers.get('X-SW-Cached-At')) : 0;
        if (!cachedAt || Date.now() - cachedAt > PAGES_MAX_AGE_MS) {
            if (cached) await cache.delete(key);
            return caches.match('/offline/');
        }
        const html = (await cached.text()).replace('</head>', '<meta name="sw-cached-at" content="' + cachedAt + '"></head>');
        return new Response(html, { headers: { 'Content-Type': 'text/html; charset=utf-8' } });
    }
}

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

    // /finde/ ignora la query; las fichas con query (?story=…) cambian de contenido y van directas a red
    if (
        event.request.mode === 'navigate'
        && PAGE_CACHE_PATHS.some((re) => re.test(pathname))
        && (pathname === '/finde/' || !url.search)
    ) {
        event.respondWith(pageNetworkFirst(event));
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

    // Solo el propio origen o subdominios del mismo dominio base (push de otro club); lo demás cae en la portada
    const baseDomain = self.location.hostname.split('.').slice(-2).join('.');
    const requested = new URL((event.notification.data && event.notification.data.url) || '/', self.location.origin);
    const sameSite = requested.protocol === self.location.protocol
        && (requested.hostname === baseDomain || requested.hostname.endsWith('.' + baseDomain));
    const fullTargetUrl = sameSite ? requested.href : self.location.origin + '/';

    event.waitUntil(
        clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clientList) => {
            // Reutiliza una ventana abierta de la app en vez de abrir otra
            // WindowClient.navigate() no cruza orígenes: si el destino es otro club, se abre ventana nueva
            const client = clientList.find((c) => 'focus' in c && new URL(c.url).origin === requested.origin);
            if (client) {
                return client.focus().then((focused) => (focused && 'navigate' in focused ? focused.navigate(fullTargetUrl) : null));
            }
            if (clients.openWindow) {
                return clients.openWindow(fullTargetUrl);
            }
        })
    );
});

// --- Background Sync para la cola de subida de fotos ---

const UPLOAD_DB_NAME = 'ilovevoley_upload_queue';
const UPLOAD_STORE_NAME = 'uploads';
const UPLOAD_ENDPOINT = '/content/api/imagenes/subir/';

function openUploadDb() {
    return new Promise((resolve, reject) => {
        const req = indexedDB.open(UPLOAD_DB_NAME, 1);
        req.onupgradeneeded = (event) => {
            const db = event.target.result;
            if (!db.objectStoreNames.contains(UPLOAD_STORE_NAME)) {
                const store = db.createObjectStore(UPLOAD_STORE_NAME, { keyPath: 'client_upload_id' });
                store.createIndex('tenant_origin', 'tenant_origin', { unique: false });
                store.createIndex('status', 'status', { unique: false });
            }
        };
        req.onsuccess = () => resolve(req.result);
        req.onerror = () => reject(req.error);
    });
}

async function swGetPendingUploads() {
    const db = await openUploadDb();
    return new Promise((resolve, reject) => {
        const tx = db.transaction(UPLOAD_STORE_NAME, 'readonly');
        const store = tx.objectStore(UPLOAD_STORE_NAME);
        const req = store.getAll();
        req.onsuccess = () => {
            const all = req.result || [];
            resolve(
                all
                    .filter((item) => item.status === 'pending' && (!item.tenant_origin || item.tenant_origin === self.location.origin))
                    .sort((a, b) => (a.created_at || 0) - (b.created_at || 0))
            );
        };
        req.onerror = () => reject(req.error);
    });
}

async function swPutUpload(item) {
    const db = await openUploadDb();
    return new Promise((resolve, reject) => {
        const tx = db.transaction(UPLOAD_STORE_NAME, 'readwrite');
        item.updated_at = Date.now();
        tx.objectStore(UPLOAD_STORE_NAME).put(item);
        tx.oncomplete = () => resolve(item);
        tx.onerror = () => reject(tx.error);
    });
}

async function processQueueInServiceWorker() {
    const clientList = await clients.matchAll({ type: 'window', includeUncontrolled: true });
    const activeWindow = clientList.find((c) => new URL(c.url).origin === self.location.origin);
    if (activeWindow) {
        activeWindow.postMessage({ type: 'PROCESS_UPLOAD_QUEUE' });
        return;
    }

    const pending = await swGetPendingUploads();
    for (const item of pending) {
        try {
            const uploadBlob = await UploadQueueBlob.materializeFromRecord(item);
            if (!uploadBlob || !uploadBlob.size) {
                item.status = 'error';
                item.error_message = UploadQueueBlob.BLOB_READ_ERROR;
                await swPutUpload(item);
                continue;
            }

            const formData = new FormData();
            formData.append('client_upload_id', item.client_upload_id);
            formData.append('batch_id', item.batch_id || item.client_upload_id);
            formData.append('image', uploadBlob, item.file_name || 'photo.jpg');
            const meta = item.metadata || {};
            if (meta.title) formData.append('title', meta.title);
            if (meta.description) formData.append('description', meta.description);
            if (meta.image_type) formData.append('image_type', meta.image_type);
            if (meta.tags) formData.append('tags', meta.tags);
            if (meta.shared_title) formData.append('shared_title', meta.shared_title);
            if (meta.match) formData.append('match', meta.match);
            if (meta.set_number) formData.append('set_number', meta.set_number);
            if (meta.season) formData.append('season', meta.season);
            if (meta.create_album) formData.append('create_album', 'true');
            if (meta.album_group_id) formData.append('album_group_id', meta.album_group_id);
            if (meta.album_name) formData.append('album_name', meta.album_name);
            if (Array.isArray(meta.categories)) {
                meta.categories.forEach((catId) => formData.append('categories', catId));
            }

            const headers = { 'X-Requested-With': 'XMLHttpRequest' };
            if (item.csrf_token) {
                headers['X-CSRFToken'] = item.csrf_token;
            }

            const resp = await fetch(item.endpoint || UPLOAD_ENDPOINT, {
                method: 'POST',
                headers: headers,
                credentials: 'same-origin',
                body: formData,
            });
            const data = await resp.json().catch(() => ({}));
            if (resp.ok && data && data.ok) {
                item.status = 'uploaded';
                item.error_message = '';
                await swPutUpload(item);
            } else if (resp.status >= 400 && resp.status < 500 && resp.status !== 408 && resp.status !== 429) {
                item.status = 'error';
                item.error_message = (data && data.error) || ('Error (' + resp.status + ')');
                await swPutUpload(item);
            } else {
                throw new Error('Transient error in SW upload');
            }
        } catch (err) {
            throw err;
        }
    }

    const updatedClients = await clients.matchAll({ type: 'window', includeUncontrolled: true });
    updatedClients.forEach((c) => c.postMessage({ type: 'UPLOAD_QUEUE_UPDATED' }));
}

self.addEventListener('sync', (event) => {
    if (event.tag === 'sync-photo-uploads') {
        event.waitUntil(processQueueInServiceWorker());
    }
});


