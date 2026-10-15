(function () {
    "use strict";

    var PROMPT_NEVER_KEY = "ilovevoley.pwa.install_never";
    var PROMPT_SNOOZE_KEY = "ilovevoley.pwa.install_snooze_until";
    var PROMPT_SNOOZE_MS = 7 * 24 * 60 * 60 * 1000;

    var deferredPrompt = null;

    function isStandalone() {
        return window.matchMedia("(display-mode: standalone)").matches || window.navigator.standalone === true;
    }

    function isIos() {
        return (/iPad|iPhone|iPod/.test(navigator.userAgent) ||
            (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1)) && !window.MSStream;
    }

    function isIosNonStandalone() {
        return isIos() && !isStandalone();
    }

    // El banner de cookies ocupa el mismo hueco inferior: hasta que se responda, no se muestra
    // el de instalación (aparecerá en la siguiente página).
    function cookieBannerPending() {
        return !/(^|;\s*)cookie_consent=(accepted|rejected)(;|$)/.test(document.cookie);
    }

    function promptNever() {
        try {
            return localStorage.getItem(PROMPT_NEVER_KEY) === "1";
        } catch (e) {
            return false;
        }
    }

    function promptSnoozed() {
        try {
            var until = parseInt(localStorage.getItem(PROMPT_SNOOZE_KEY) || "", 10);
            return Boolean(until && Date.now() < until);
        } catch (e) {
            return false;
        }
    }

    function fallbackCopy(textToCopy, message) {
        var textarea = document.createElement("textarea");
        textarea.value = textToCopy;
        textarea.style.position = "fixed";
        textarea.style.opacity = "0";
        document.body.appendChild(textarea);
        textarea.focus();
        textarea.select();
        try {
            document.execCommand("copy");
            if (window.showToast) {
                window.showToast("success", message);
            }
        } catch (e) {}
        document.body.removeChild(textarea);
    }

    function copyToClipboard(url) {
        var msg = (window.PWA_INSTALL_I18N && window.PWA_INSTALL_I18N.linkCopied)
            ? window.PWA_INSTALL_I18N.linkCopied
            : "Enlace copiado al portapapeles";

        if (navigator.clipboard && navigator.clipboard.writeText) {
            navigator.clipboard.writeText(url).then(function () {
                if (window.showToast) {
                    window.showToast("success", msg);
                }
            }).catch(function () {
                fallbackCopy(url, msg);
            });
        } else {
            fallbackCopy(url, msg);
        }
    }

    // Datos de compartición del club activo. Se definen una sola vez en el <body> y los botones
    // (navbar escritorio/móvil y pie) solo llevan data-call="shareClub".
    function sharePayload() {
        var body = document.body;
        var attr = function (name) {
            return body ? body.getAttribute(name) : null;
        };
        return {
            url: attr("data-share-url") || window.location.href,
            title: attr("data-share-title") || document.title,
            text: attr("data-share-text") || ""
        };
    }

    window.PwaInstallManager = {
        isStandalone: isStandalone,
        isIosNonStandalone: isIosNonStandalone,

        init: function () {
            if (isStandalone() || promptNever() || promptSnoozed()) {
                return;
            }

            if (isIosNonStandalone()) {
                this.updateIosUI();
                this.showPrompt();
            }
        },

        updateIosUI: function () {
            var banner = document.getElementById("pwa-install-prompt");
            if (!banner) return;
            var btn = banner.querySelector("[data-pwa-install-btn]");
            if (btn && banner.dataset.installIosLabel) {
                btn.textContent = banner.dataset.installIosLabel;
            }
        },

        showPrompt: function () {
            var banner = document.getElementById("pwa-install-prompt");
            if (banner && !cookieBannerPending()) {
                banner.classList.remove("hidden");
            }
        },

        hidePrompt: function () {
            var banner = document.getElementById("pwa-install-prompt");
            if (banner) {
                banner.classList.add("hidden");
            }
        },

        snoozePrompt: function () {
            try {
                localStorage.setItem(PROMPT_SNOOZE_KEY, String(Date.now() + PROMPT_SNOOZE_MS));
            } catch (e) {}
            this.hidePrompt();
        },

        declinePromptForever: function () {
            try {
                localStorage.setItem(PROMPT_NEVER_KEY, "1");
                localStorage.removeItem(PROMPT_SNOOZE_KEY);
            } catch (e) {}
            this.hidePrompt();
        },

        acceptPrompt: function () {
            var self = this;
            if (deferredPrompt) {
                deferredPrompt.prompt();
                deferredPrompt.userChoice.then(function (choice) {
                    deferredPrompt = null;
                    // Chrome vuelve a lanzar beforeinstallprompt en cada página: si se cierra el
                    // diálogo nativo sin instalar, se pospone como «Ahora no».
                    if (choice && choice.outcome === "accepted") {
                        self.hidePrompt();
                    } else {
                        self.snoozePrompt();
                    }
                }).catch(function () {
                    self.hidePrompt();
                });
            } else if (isIosNonStandalone()) {
                this.openIosInstructions();
            } else {
                // Guarda defensiva: sin evento de instalación y sin ser iOS, las instrucciones de
                // Safari no aplican; se oculta el banner en vez de mostrar la rama equivocada.
                this.hidePrompt();
            }
        },

        openIosInstructions: function () {
            var modal = document.getElementById("pwa-ios-modal");
            if (modal && typeof modal.showModal === "function" && !modal.open) {
                modal.showModal();
            }
        },

        closeIosInstructions: function () {
            var modal = document.getElementById("pwa-ios-modal");
            if (modal && typeof modal.close === "function" && modal.open) {
                modal.close();
            }
        },

        shareClub: function () {
            var data = sharePayload();

            if (navigator.share) {
                navigator.share({
                    title: data.title,
                    text: data.text,
                    url: data.url
                }).catch(function (err) {
                    // Si el usuario cancela la hoja de compartir (AbortError), no hacemos fallback
                    if (err && err.name !== "AbortError") {
                        copyToClipboard(data.url);
                    }
                });
            } else {
                copyToClipboard(data.url);
            }
        }
    };

    window.acceptPwaInstallPrompt = function () { window.PwaInstallManager.acceptPrompt(); };
    window.dismissPwaInstallPrompt = function () { window.PwaInstallManager.snoozePrompt(); };
    window.declinePwaInstallPrompt = function () { window.PwaInstallManager.declinePromptForever(); };
    window.closePwaIosModal = function () { window.PwaInstallManager.closeIosInstructions(); };
    window.shareClub = function () { window.PwaInstallManager.shareClub(); };

    // Captura del evento de instalación en Android / Chromium. En escritorio (puntero fino) no
    // se intercepta: Chrome ya ofrece el icono de instalar en la barra de direcciones.
    window.addEventListener("beforeinstallprompt", function (event) {
        if (!window.matchMedia("(pointer: coarse)").matches) return;
        event.preventDefault();
        deferredPrompt = event;
        if (!isStandalone() && !promptNever() && !promptSnoozed()) {
            window.PwaInstallManager.showPrompt();
        }
    });

    // Sin marca permanente: con la app instalada Chrome deja de lanzar beforeinstallprompt, y si se
    // desinstala se vuelve a ofrecer.
    window.addEventListener("appinstalled", function () {
        deferredPrompt = null;
        window.PwaInstallManager.hidePrompt();
        window.PwaInstallManager.closeIosInstructions();
    });

    if (document.readyState !== "loading") {
        window.PwaInstallManager.init();
    } else {
        document.addEventListener("DOMContentLoaded", function () {
            window.PwaInstallManager.init();
        });
    }
})();
