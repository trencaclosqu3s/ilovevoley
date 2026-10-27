/*
 * Caché offline de páginas privadas (#610). El SW guarda «Este finde» y las fichas de partido;
 * aquí se avisa de la antigüedad cuando se sirven desde caché y se vacía al cerrar sesión o
 * al llegar a una pantalla de acceso (sesión caducada o cambio de cuenta), para no dejar HTML de otra persona.
 */
(function () {
    "use strict";

    var PAGES_CACHE = "ilovevoley-pwa-pages-v1";
    var label = document.currentScript && document.currentScript.dataset.label;

    function clearPages() {
        return window.caches ? caches.delete(PAGES_CACHE).catch(function () {}) : Promise.resolve();
    }

    // Cualquier pantalla de acceso (login, registro, social), salvo la confirmación de logout, que se puede cancelar
    if (location.pathname.indexOf("/accounts/") === 0 && location.pathname.indexOf("/accounts/logout/") !== 0) {
        clearPages();
    }

    document.addEventListener("submit", function (event) {
        var form = event.target;
        if (!form.matches || !form.matches("form[data-clear-pages-cache]")) {
            return;
        }
        event.preventDefault();
        clearPages().then(function () { form.submit(); });
    });

    document.addEventListener("DOMContentLoaded", function () {
        var meta = document.querySelector('meta[name="sw-cached-at"]');
        var main = document.querySelector("main");
        if (!meta || !main) {
            return;
        }
        var minutes = Math.max(0, Math.round((Date.now() - Number(meta.content)) / 60000));
        var rtf = new Intl.RelativeTimeFormat(document.documentElement.lang || "es", { numeric: "always" });
        var unit = minutes < 60 ? ["minute", minutes] : minutes < 1440 ? ["hour", Math.round(minutes / 60)] : ["day", Math.round(minutes / 1440)];
        var banner = document.createElement("div");
        banner.setAttribute("role", "status");
        banner.className = "mb-4 p-2 rounded-lg bg-tint text-ink text-sm text-center";
        banner.textContent = (label || "") + " " + rtf.format(-unit[1], unit[0]);
        main.insertBefore(banner, main.firstChild);
    });
})();
