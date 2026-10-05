/*
 * Retroceso in-app para la PWA instalada. En display-mode standalone el
 * navegador no pinta sus flechas y en iOS no existe gesto de swipe, así que
 * la navbar expone su propio botón "atrás".
 *
 * `history.length` no sirve para saber si hay historial propio de la app: en
 * standalone suele ser > 1 aunque se haya abierto directamente en esa URL. Se
 * lleva un contador en sessionStorage que sube en cada navegación normal y baja
 * al volver atrás, de modo que el botón solo retrocede si de verdad hay algo a
 * lo que volver; si no, cae a la portada del club.
 */
(function () {
    "use strict";

    var standalone = window.matchMedia("(display-mode: standalone)").matches
        || window.navigator.standalone === true;
    if (!standalone) {
        return;
    }

    var DEPTH_KEY = "ilovevoley.pwa.nav.depth";

    function readDepth() {
        try {
            var raw = sessionStorage.getItem(DEPTH_KEY);
            return raw === null ? null : Math.max(0, parseInt(raw, 10) || 0);
        } catch (e) {
            return null;
        }
    }

    function storeDepth(depth) {
        try { sessionStorage.setItem(DEPTH_KEY, String(depth)); } catch (e) { /* almacenamiento no disponible */ }
    }

    function navigationType() {
        try {
            var entries = performance.getEntriesByType("navigation");
            if (entries && entries.length && entries[0].type) {
                return entries[0].type;
            }
        } catch (e) { /* sin Navigation Timing */ }
        return "navigate";
    }

    function trackDepth() {
        var stored = readDepth();
        var type = navigationType();
        var depth;
        if (stored === null) {
            depth = 0;
        } else if (type === "reload") {
            depth = stored;
        } else if (type === "back_forward") {
            depth = Math.max(0, stored - 1);
        } else {
            depth = stored + 1;
        }
        storeDepth(depth);
        return depth;
    }

    function normalizePath(value) {
        var anchor = document.createElement("a");
        anchor.href = value;
        var path = anchor.pathname;
        return path.length > 1 ? path.replace(/\/+$/, "") : path;
    }

    function init() {
        var button = document.getElementById("pwa-back-button");
        if (!button) {
            return;
        }
        var homeUrl = button.getAttribute("data-home-url") || "/";
        var depth = trackDepth();

        function onHome() {
            return normalizePath(window.location.href) === normalizePath(homeUrl);
        }

        function sync() {
            if (onHome()) {
                button.classList.add("hidden");
                button.classList.remove("inline-flex");
            } else {
                button.classList.remove("hidden");
                button.classList.add("inline-flex");
            }
        }

        button.addEventListener("click", function () {
            if (depth > 0) {
                window.history.back();
            } else {
                window.location.href = homeUrl;
            }
        });

        window.addEventListener("popstate", sync);
        window.addEventListener("pageshow", sync);
        sync();
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
