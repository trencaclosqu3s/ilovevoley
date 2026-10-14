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
            if (banner) {
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
                    if (choice && choice.outcome === "accepted") {
                        try {
                            localStorage.setItem(PROMPT_NEVER_KEY, "1");
                        } catch (e) {}
                    }
                    deferredPrompt = null;
                    self.hidePrompt();
                }).catch(function () {
                    self.hidePrompt();
                });
            } else {
                this.openIosInstructions();
            }
        },

        openIosInstructions: function () {
            var modal = document.getElementById("pwa-ios-modal");
            if (!modal) return;
            if (typeof modal.showModal === "function") {
                modal.showModal();
            } else {
                modal.classList.remove("hidden");
            }
        },

        closeIosInstructions: function () {
            var modal = document.getElementById("pwa-ios-modal");
            if (!modal) return;
            if (typeof modal.close === "function") {
                modal.close();
            } else {
                modal.classList.add("hidden");
            }
        },

        shareClub: function (el) {
            var btn = el || this;
            var url = (btn && (btn.getAttribute("data-share-url") || btn.dataset.shareUrl)) || window.location.href;
            var title = (btn && (btn.getAttribute("data-share-title") || btn.dataset.shareTitle)) || document.title;
            var text = (btn && (btn.getAttribute("data-share-text") || btn.dataset.shareText)) || "";

            if (navigator.share) {
                navigator.share({
                    title: title,
                    text: text,
                    url: url
                }).catch(function (err) {
                    // Si el usuario cancela la hoja de compartir (AbortError), no hacemos fallback
                    if (err && err.name !== "AbortError") {
                        copyToClipboard(url);
                    }
                });
            } else {
                copyToClipboard(url);
            }
        }
    };

    window.acceptPwaInstallPrompt = function () { window.PwaInstallManager.acceptPrompt(); };
    window.dismissPwaInstallPrompt = function () { window.PwaInstallManager.snoozePrompt(); };
    window.declinePwaInstallPrompt = function () { window.PwaInstallManager.declinePromptForever(); };
    window.closePwaIosModal = function () { window.PwaInstallManager.closeIosInstructions(); };
    window.shareClub = function (el) { window.PwaInstallManager.shareClub(el); };

    // Captura del evento de instalación en Android / Chromium
    window.addEventListener("beforeinstallprompt", function (event) {
        event.preventDefault();
        deferredPrompt = event;
        if (!isStandalone() && !promptNever() && !promptSnoozed()) {
            window.PwaInstallManager.showPrompt();
        }
    });

    // Notificación tras completarse la instalación
    window.addEventListener("appinstalled", function () {
        deferredPrompt = null;
        try {
            localStorage.setItem(PROMPT_NEVER_KEY, "1");
        } catch (e) {}
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
