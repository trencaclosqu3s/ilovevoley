/*
 * Retroceso in-app para la PWA instalada. En display-mode standalone el
 * navegador no pinta sus flechas y en iOS no existe gesto de swipe, así que
 * la navbar expone su propio botón "atrás". Se oculta en la portada del club
 * y cuando no hay historial interno (acceso directo desde un push, por
 * ejemplo) retrocede a la portada.
 */
(function () {
    "use strict";

    var standalone = window.matchMedia("(display-mode: standalone)").matches
        || window.navigator.standalone === true;
    if (!standalone) {
        return;
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
            if (window.history.length > 1) {
                window.history.back();
            } else {
                window.location.href = homeUrl;
            }
        });

        window.addEventListener("pageshow", sync);
        window.addEventListener("popstate", sync);
        sync();
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
