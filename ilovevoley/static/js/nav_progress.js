/*
 * Barra de progreso fina arriba al navegar. En la PWA instalada no hay
 * indicador de carga del navegador y una página lenta parece un toque
 * ignorado; en navegador y desktop pasa lo mismo, solo que menos.
 *
 * Solo se pinta si la navegación tarda más de SHOW_DELAY_MS (sin parpadeo en
 * páginas rápidas). Se apaga al cargar la página nueva (el documento se
 * descarta), en `pageshow` (bfcache) y, para descargas que no descargan la
 * página, con un timeout de seguridad.
 */
(function () {
    "use strict";

    var SHOW_DELAY_MS = 150;
    var SAFETY_MS = 15000;
    var bar = null;
    var showTimer = null;
    var safetyTimer = null;

    function stop() {
        clearTimeout(showTimer);
        clearTimeout(safetyTimer);
        showTimer = safetyTimer = null;
        if (bar) {
            bar.classList.remove("is-active");
        }
    }

    function start() {
        bar = bar || document.getElementById("nav-progress");
        if (!bar || showTimer) {
            return;
        }
        showTimer = setTimeout(function () {
            bar.classList.add("is-active");
        }, SHOW_DELAY_MS);
        safetyTimer = setTimeout(stop, SAFETY_MS);
    }

    // Misma origen http(s) y no solo un cambio de ancla en la página actual.
    function navigatesAway(href) {
        var url;
        try {
            url = new URL(href, window.location.href);
        } catch (e) {
            return false;
        }
        if (url.protocol !== "http:" && url.protocol !== "https:") {
            return false;
        }
        if (url.origin !== window.location.origin) {
            return false;
        }
        var here = window.location;
        return !(url.hash && url.pathname === here.pathname && url.search === here.search);
    }

    document.addEventListener("click", function (event) {
        if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) {
            return;
        }
        var target = event.target;
        if (!target || typeof target.closest !== "function") {
            return;
        }
        // csp_actions.js hace preventDefault() y navega él mismo con data-href.
        var dataHref = target.closest("[data-href]");
        if (dataHref) {
            if (navigatesAway(dataHref.getAttribute("data-href"))) {
                start();
            }
            return;
        }
        if (event.defaultPrevented) {
            return;
        }
        var link = target.closest("a[href]");
        if (!link || link.hasAttribute("download")) {
            return;
        }
        var linkTarget = link.getAttribute("target");
        if (linkTarget && linkTarget !== "_self") {
            return;
        }
        if (navigatesAway(link.href)) {
            start();
        }
    }, false);

    document.addEventListener("submit", function (event) {
        if (event.defaultPrevented) {
            return;
        }
        var form = event.target;
        var submitter = event.submitter;
        var formTarget = (submitter && submitter.getAttribute("formtarget")) || form.getAttribute("target");
        if (formTarget && formTarget !== "_self") {
            return;
        }
        start();
    }, false);

    // form.submit() no dispara `submit`.
    document.addEventListener("change", function (event) {
        var target = event.target;
        if (target && typeof target.closest === "function" && target.closest("[data-submit-on-change]")) {
            start();
        }
    }, false);

    window.addEventListener("pageshow", stop);
})();
