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
                if (!sub) banner.classList.remove('hidden');
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
            var target = document.getElementById('webpush-prompt').getAttribute('data-target-url');
            self.closePrompt();
            navigator.serviceWorker.ready.then(function (reg) {
                return self.subscribe(reg);
            }).catch(function () {}).finally(function () {
                window.location.href = target;
            });
        },

        updateUI: function () {
            var statusBadge = document.getElementById('webpush-status-badge');
            var toggleBtn = document.getElementById('webpush-toggle-btn');
            var iosHint = document.getElementById('webpush-ios-hint');

            if (!statusBadge || !toggleBtn) return;

            if (!this.isSupported()) {
                statusBadge.textContent = 'No soportado en este navegador';
                statusBadge.className = 'px-3 py-1 rounded-full text-sm font-medium bg-gray-100 text-gray-700';
                toggleBtn.disabled = true;
                return;
            }

            if (this.isIosNonStandalone()) {
                if (iosHint) iosHint.classList.remove('hidden');
            }

            if (Notification.permission === 'denied') {
                statusBadge.textContent = 'Permiso Bloqueado en el Navegador';
                statusBadge.className = 'px-3 py-1 rounded-full text-sm font-medium bg-red-100 text-red-800';
                toggleBtn.textContent = 'Permiso denegado';
                toggleBtn.disabled = true;
                return;
            }

            navigator.serviceWorker.ready.then(function (reg) {
                return reg.pushManager.getSubscription();
            }).then(function (sub) {
                toggleBtn.disabled = false;
                if (sub) {
                    statusBadge.textContent = 'Notificaciones Activas';
                    statusBadge.className = 'px-3 py-1 rounded-full text-sm font-medium bg-green-100 text-green-800';
                    toggleBtn.textContent = 'Desactivar notificaciones';
                    toggleBtn.className = 'px-4 py-2 bg-red-600 hover:bg-red-700 text-white text-sm font-medium rounded transition';
                } else {
                    statusBadge.textContent = 'Desactivadas';
                    statusBadge.className = 'px-3 py-1 rounded-full text-sm font-medium bg-gray-100 text-gray-700';
                    toggleBtn.textContent = 'Activar notificaciones';
                    toggleBtn.className = 'px-4 py-2 bg-csj-purple hover:bg-purple-700 text-white text-sm font-medium rounded transition';
                }
            });
        },

        toggle: function () {
            var self = this;
            if (!this.isSupported()) return;

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
                if (window.showToast) window.showToast('error', 'Error al modificar notificaciones: ' + err.message);
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
                .then(function (res) {
                    if (window.showToast) window.showToast('success', '¡Notificaciones activadas con éxito!');
                });
        },

        unsubscribe: function (sub) {
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
                if (window.showToast) window.showToast('info', 'Notificaciones desactivadas en este dispositivo');
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
