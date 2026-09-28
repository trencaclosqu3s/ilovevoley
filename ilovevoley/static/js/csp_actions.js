/*
 * Sustituto de los antiguos atributos inline (onclick/onchange/onerror) para
 * que la CSP estricta pueda prohibir 'unsafe-inline'. Se activa por
 * delegación de eventos sobre atributos data-*, de modo que también cubre el
 * HTML generado dinámicamente por otros scripts.
 *
 *   data-call="fn"                -> window.fn(...args)
 *   data-call-args='[1,"a"]'      -> argumentos JSON (opcional)
 *   data-call-this                -> añade el propio elemento como último arg
 *   data-call-prevent             -> event.preventDefault() antes de llamar
 *   data-href="/ruta"             -> navega al hacer clic
 *   data-action="back|reload|dismiss-closest"
 *   data-dismiss-selector=".sel"  -> selector para dismiss-closest
 *   data-submit-on-change         -> envía el formulario al cambiar
 *   data-hide-on-error            -> oculta la imagen si falla la carga
 */
(function () {
    "use strict";

    function parseArgs(raw) {
        if (!raw) {
            return [];
        }
        try {
            var parsed = JSON.parse(raw);
            return Array.isArray(parsed) ? parsed : [parsed];
        } catch (error) {
            return [];
        }
    }

    function invoke(el, name, args, withThis) {
        var fn = window[name];
        if (typeof fn !== "function") {
            return;
        }
        var callArgs = args || [];
        if (withThis) {
            callArgs = callArgs.concat([el]);
        }
        fn.apply(el, callArgs);
    }

    document.addEventListener("click", function (event) {
        var target = event.target;
        if (!target || typeof target.closest !== "function") {
            return;
        }
        var el = target.closest("[data-call], [data-href], [data-action]");
        if (!el) {
            return;
        }

        if (el.hasAttribute("data-href")) {
            event.preventDefault();
            window.location.href = el.getAttribute("data-href");
            return;
        }

        var action = el.getAttribute("data-action");
        if (action === "back") {
            event.preventDefault();
            window.history.back();
            return;
        }
        if (action === "reload") {
            event.preventDefault();
            window.location.reload();
            return;
        }
        if (action === "dismiss-closest") {
            event.preventDefault();
            var target = el.closest(el.getAttribute("data-dismiss-selector") || "div");
            if (target) {
                target.style.display = "none";
            }
            return;
        }

        var name = el.getAttribute("data-call");
        if (name) {
            if (el.hasAttribute("data-call-prevent")) {
                event.preventDefault();
            }
            invoke(el, name, parseArgs(el.getAttribute("data-call-args")), el.hasAttribute("data-call-this"));
        }
    }, false);

    document.addEventListener("change", function (event) {
        var target = event.target;
        if (!target || typeof target.closest !== "function") {
            return;
        }
        var el = target.closest("[data-submit-on-change]");
        if (el && el.form) {
            el.form.submit();
        }
    }, false);

    // `error` no burbujea; se escucha en fase de captura desde window.
    window.addEventListener("error", function (event) {
        var el = event.target;
        if (el && el.nodeType === 1 && el.hasAttribute && el.hasAttribute("data-hide-on-error")) {
            el.style.display = "none";
        }
    }, true);
})();
