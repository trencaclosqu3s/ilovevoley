/**
 * Toggle de fotos favoritas.
 *
 * Se enlaza a cada botón en el DOM (las fotos se renderizan en servidor) y el
 * clic corta la propagación para que no abra el lightbox ni el detalle de la
 * tarjeta cuando el botón va dentro de un elemento con data-call.
 */
(function () {
    'use strict';

    function setState(button, favorited, count) {
        button.setAttribute('aria-pressed', favorited ? 'true' : 'false');
        button.classList.toggle('text-red-400', favorited);
        button.classList.toggle('text-white', !favorited);
        var svg = button.querySelector('svg');
        if (svg) svg.classList.toggle('fill-current', favorited);
        var counter = button.querySelector('.image-favorite-count');
        if (counter) counter.textContent = count;
    }

    function toggle(button) {
        if (button.disabled) return;
        button.disabled = true;

        var token = typeof window.getCsrfToken === 'function' ? window.getCsrfToken() : '';
        fetch(button.dataset.favoriteUrl, {
            method: 'POST',
            headers: {
                'X-CSRFToken': token,
                'X-Requested-With': 'XMLHttpRequest',
            },
            credentials: 'same-origin',
        })
            .then(function (response) {
                return response.json().then(function (data) {
                    return { ok: response.ok, data: data };
                });
            })
            .then(function (result) {
                if (!result.ok || !result.data.success) {
                    throw new Error((result.data && result.data.error) || 'Error');
                }
                setState(button, result.data.favorited, result.data.count);
            })
            .catch(function () {
                if (window.showToast) {
                    window.showToast('error', button.dataset.favoriteError || 'Error');
                }
            })
            .finally(function () {
                button.disabled = false;
            });
    }

    document.addEventListener('DOMContentLoaded', function () {
        document.querySelectorAll('.image-favorite-btn').forEach(function (button) {
            button.addEventListener('click', function (event) {
                event.preventDefault();
                event.stopPropagation();
                toggle(button);
            });
        });
    });
})();
