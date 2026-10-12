(function () {
    "use strict";

    var PROMPT_KEY = "ilovevoley.webpush.prompt_seen";

    function urlB64ToUint8Array(base64String) {
        var padding = '='.repeat((4 - (base64String.length % 4)) % 4);
        var base64 = (base64String + padding)
            .replace(/\-/g, '+')
            .replace(/_/g, '/');
        var rawData = window.atob(base64);
        var outputArray = new Uint8Array(rawData.length);
        for (var i = 0; i < rawData.length; ++i) {
            outputArray[i] = rawData.charCodeAt(i);
        }
        return outputArray;
    }

    function getCookie(name) {
        var cookieValue = null;
        if (document.cookie && document.cookie !== '') {
            var cookies = document.cookie.split(';');
            for (var i = 0; i < cookies.length; i++) {
                var cookie = cookies[i].trim();
                if (cookie.substring(0, name.length + 1) === (name + '=')) {
                    cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                    // No hacer break: si hay cookies duplicadas (host-only vs .ilovevoley.es),
                    // la última coincide con lo que SimpleCookie de Python procesa en el backend.
                }
            }
        }
        return cookieValue;
    }

    function getCsrfToken() {
        if (typeof window.getCsrfToken === 'function') {
            var token = window.getCsrfToken();
            if (token) return token;
        }
        var meta = document.querySelector('meta[name="csrf-token"]');
        if (meta && meta.content) {
            return meta.content;
        }
        var input = document.querySelector('[name=csrfmiddlewaretoken]');
        if (input && input.value) {
            return input.value;
        }
        return getCookie('csrftoken');
    }

    function cleanupDuplicateCsrfCookies() {
        var matches = document.cookie.match(/(?:^|;\s*)csrftoken=/g);
        if (matches && matches.length > 1) {
            // Eliminar la cookie host-only para resolver colisiones con la de dominio (.ilovevoley.es)
            document.cookie = 'csrftoken=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT';
            document.cookie = 'csrftoken=; path=/; domain=' + window.location.hostname + '; expires=Thu, 01 Jan 1970 00:00:00 GMT';
        }
    }

    function uiLabel(key, fallback) {
        // Las etiquetas se traducen en profile.html (window.WEBPUSH_I18N);
        // fuera de esa pagina o sin catalogo, se mantiene el literal en castellano.
        var labels = window.WEBPUSH_I18N;
        return (labels && labels[key]) || fallback;
    }

    window.WebPushManager = {
        isSupported: function () {
            return ('serviceWorker' in navigator) && ('PushManager' in window) && ('Notification' in window);
        },

        isIosNonStandalone: function () {
            var isIos = /iPad|iPhone|iPod/.test(navigator.userAgent) && !window.MSStream;
            var isStandalone = window.matchMedia('(display-mode: standalone)').matches || window.navigator.standalone;
            return isIos && !isStandalone;
        },

        init: function () {
            cleanupDuplicateCsrfCookies();
            // Limpiar badge al abrir la aplicación
            if ('clearAppBadge' in navigator) {
                navigator.clearAppBadge().catch(function () {});
            }
            this.updateUI();
            this.maybeShowPrompt();
        },

        // Aviso único (#412): solo en la PWA instalada, con sesión y sin suscripción.
        maybeShowPrompt: function () {
            var banner = document.getElementById('webpush-prompt');
            var standalone = window.matchMedia('(display-mode: standalone)').matches || window.navigator.standalone === true;
            if (!banner || !standalone || !this.isSupported() || Notification.permission === 'denied' || this.promptSeen()) return;
            navigator.serviceWorker.ready.then(function (reg) {
                return reg.pushManager.getSubscription();
            }).then(function (sub) {
                if (!sub) {
                    banner.classList.remove('hidden');
                } else {
                    try { localStorage.setItem(PROMPT_KEY, '1'); } catch (e) { /* almacenamiento no disponible */ }
                }
            }).catch(function () {});
        },

        promptSeen: function () {
            try { return localStorage.getItem(PROMPT_KEY) === '1'; } catch (e) { return false; }
        },

        closePrompt: function () {
            try { localStorage.setItem(PROMPT_KEY, '1'); } catch (e) { /* almacenamiento no disponible */ }
            var banner = document.getElementById('webpush-prompt');
            if (banner) banner.classList.add('hidden');
        },

        acceptPrompt: function () {
            var self = this;
            var banner = document.getElementById('webpush-prompt');
            var target = banner.getAttribute('data-target-url');
            navigator.serviceWorker.ready.then(function (reg) {
                return self.subscribe(reg);
            }).then(function () {
                self.closePrompt();
                window.location.href = target;
            }).catch(function () {
                // Fallo transitorio o permiso no concedido: se oculta sin marcarlo como visto ni navegar.
                banner.classList.add('hidden');
            });
        },

        updateUI: function () {
            var statusBadge = document.getElementById('webpush-status-badge');
            var toggleBtn = document.getElementById('webpush-toggle-btn');
            var iosHint = document.getElementById('webpush-ios-hint');
            var blockedHint = document.getElementById('webpush-blocked-hint');
            var subInput = document.getElementById('has-device-push-subscription');
            var box = document.getElementById('este-movil-box');

            if (!statusBadge || !toggleBtn) return;

            if (!this.isSupported()) {
                statusBadge.textContent = uiLabel('unsupportedBadge', 'No soportado en este navegador');
                statusBadge.className = 'px-3 py-1 rounded-full text-xs font-semibold bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300';
                toggleBtn.disabled = true;
                toggleBtn.textContent = uiLabel('unsupportedBtn', 'No soportado');
                toggleBtn.className = 'px-4 py-2 bg-gray-400 text-white text-sm font-semibold rounded-xl cursor-not-allowed';
                if (subInput) subInput.value = '0';
                if (iosHint) iosHint.classList.add('hidden');
                if (blockedHint) blockedHint.classList.add('hidden');
                return;
            }

            if (this.isIosNonStandalone()) {
                if (iosHint) iosHint.classList.remove('hidden');
                if (blockedHint) blockedHint.classList.add('hidden');
                statusBadge.textContent = uiLabel('installBadge', 'Instalación requerida');
                statusBadge.className = 'px-3 py-1 rounded-full text-xs font-semibold bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-200 border border-amber-200 dark:border-amber-700';
                toggleBtn.disabled = true;
                toggleBtn.textContent = uiLabel('installBtn', 'Instala la app para activar');
                toggleBtn.className = 'px-4 py-2 bg-gray-400 text-white text-sm font-semibold rounded-xl cursor-not-allowed';
                if (subInput) subInput.value = '0';
                if (box) {
                    box.classList.remove('border-green-300', 'dark:border-green-800', 'border-red-200');
                    box.classList.add('border-amber-200', 'dark:border-amber-700');
                }
                return;
            }

            if (iosHint) iosHint.classList.add('hidden');

            if (Notification.permission === 'denied') {
                statusBadge.textContent = uiLabel('blockedBadge', 'Permiso bloqueado');
                statusBadge.className = 'px-3 py-1 rounded-full text-xs font-semibold bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-200 border border-red-200 dark:border-red-700';
                if (blockedHint) blockedHint.classList.remove('hidden');
                toggleBtn.textContent = uiLabel('blockedBtn', 'Permiso denegado');
                toggleBtn.className = 'px-4 py-2 bg-gray-400 text-white text-sm font-semibold rounded-xl cursor-not-allowed';
                toggleBtn.disabled = true;
                if (subInput) subInput.value = '0';
                if (box) {
                    box.classList.remove('border-green-300', 'dark:border-green-800', 'border-amber-200');
                    box.classList.add('border-red-200', 'dark:border-red-700');
                }
                return;
            }

            if (blockedHint) blockedHint.classList.add('hidden');

            navigator.serviceWorker.ready.then(function (reg) {
                return reg.pushManager.getSubscription();
            }).then(function (sub) {
                toggleBtn.disabled = false;
                if (sub) {
                    if (subInput) subInput.value = '1';
                    statusBadge.textContent = uiLabel('activeBadge', 'Avisos activos en este móvil');
                    statusBadge.className = 'px-3 py-1 rounded-full text-xs font-semibold bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-200 border border-green-200 dark:border-green-700';
                    toggleBtn.textContent = uiLabel('deactivateBtn', 'Desactivar avisos en este móvil');
                    toggleBtn.className = 'px-4 py-2 bg-red-600 hover:bg-red-700 text-white text-sm font-semibold rounded-xl transition';
                    if (box) {
                        box.classList.remove('border-amber-200', 'border-red-200', 'border-line');
                        box.classList.add('border-green-300', 'dark:border-green-800');
                    }
                } else {
                    if (subInput) subInput.value = '0';
                    statusBadge.textContent = uiLabel('offBadge', 'Avisos desactivados');
                    statusBadge.className = 'px-3 py-1 rounded-full text-xs font-semibold bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-200 border border-amber-200 dark:border-amber-700';
                    toggleBtn.textContent = uiLabel('activateBtn', 'Activar avisos en este móvil');
                    toggleBtn.className = 'px-4 py-2 bg-csj-purple-dark hover:bg-purple-700 text-white text-sm font-semibold rounded-xl transition';
                    if (box) {
                        box.classList.remove('border-green-300', 'dark:border-green-800', 'border-red-200');
                        box.classList.add('border-amber-200', 'dark:border-amber-700');
                    }
                }
            }).catch(function () {
                if (subInput) subInput.value = '0';
                statusBadge.textContent = uiLabel('offBadge', 'Avisos desactivados');
                statusBadge.className = 'px-3 py-1 rounded-full text-xs font-semibold bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-200';
                toggleBtn.disabled = false;
                toggleBtn.textContent = uiLabel('activateBtn', 'Activar avisos en este móvil');
                toggleBtn.className = 'px-4 py-2 bg-csj-purple-dark hover:bg-purple-700 text-white text-sm font-semibold rounded-xl transition';
            });
        },

        toggle: function () {
            var self = this;
            if (!this.isSupported() || this.isIosNonStandalone()) return;

            var toggleBtn = document.getElementById('webpush-toggle-btn');
            if (toggleBtn) toggleBtn.disabled = true;

            navigator.serviceWorker.ready.then(function (reg) {
                return reg.pushManager.getSubscription().then(function (sub) {
                    if (sub) {
                        return self.unsubscribe(sub);
                    } else {
                        return self.subscribe(reg);
                    }
                });
            }).catch(function (err) {
                if (window.showToast) window.showToast('error', uiLabel('toggleError', 'Error al modificar avisos') + ': ' + err.message);
            }).finally(function () {
                if (toggleBtn) toggleBtn.disabled = false;
                self.updateUI();
            });
        },

        subscribe: function (reg) {
            var self = this;
            return fetch('/api/webpush/vapid-key/')
                .then(function (res) {
                    if (!res.ok) throw new Error('HTTP error ' + res.status);
                    return res.json();
                })
                .then(function (data) {
                    if (!data.public_key) throw new Error('Clave pública VAPID no disponible');
                    var keyArray = urlB64ToUint8Array(data.public_key);
                    return reg.pushManager.subscribe({
                        userVisibleOnly: true,
                        applicationServerKey: keyArray
                    });
                })
                .then(function (sub) {
                    if (!sub) throw new Error(uiLabel('subFail', 'No se pudo registrar la suscripción'));
                    var subJson = sub.toJSON();
                    return fetch('/api/webpush/subscribe/', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-CSRFToken': getCsrfToken()
                        },
                        body: JSON.stringify({
                            endpoint: sub.endpoint,
                            keys: subJson.keys,
                            user_agent: navigator.userAgent
                        })
                    }).then(function (res) {
                        if (!res.ok) {
                            return sub.unsubscribe().finally(function () {
                                throw new Error('HTTP error ' + res.status);
                            });
                        }
                        return res;
                    });
                })
                .then(function () {
                    if (window.showToast) window.showToast('success', uiLabel('toastOn', '¡Avisos activados con éxito en este móvil!'));
                    self.updateUI();
                });
        },

        unsubscribe: function (sub) {
            var self = this;
            var endpoint = sub.endpoint;
            return sub.unsubscribe().then(function () {
                return fetch('/api/webpush/unsubscribe/', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': getCsrfToken()
                    },
                    body: JSON.stringify({ endpoint: endpoint })
                });
            }).then(function (res) {
                if (!res.ok) throw new Error('HTTP error ' + res.status);
                if (window.showToast) window.showToast('info', uiLabel('toastOff', 'Avisos desactivados en este móvil'));
                self.updateUI();
            });
        }
    };

    window.acceptWebPushPrompt = function () { window.WebPushManager.acceptPrompt(); };
    window.dismissWebPushPrompt = function () { window.WebPushManager.closePrompt(); };

    window.toggleWebPush = function () {
        window.WebPushManager.toggle();
    };

    if (document.readyState !== 'loading') {
        window.WebPushManager.init();
    } else {
        document.addEventListener('DOMContentLoaded', function () {
            window.WebPushManager.init();
        });
    }
})();
