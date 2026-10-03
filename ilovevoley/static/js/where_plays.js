(function () {
    'use strict';

    const form = document.querySelector('[data-where-plays]');
    if (!form) return;

    const input = form.querySelector('input[name="q"]');
    const resultsEl = document.getElementById('where-plays-results');
    const hintEl = document.getElementById('where-plays-hint');
    const searchUrl = form.dataset.searchUrl;
    const minLength = parseInt(form.dataset.minLength || '3', 10);
    if (!input || !resultsEl || !searchUrl) return;

    const DEBOUNCE_MS = 300;

    function escapeHtml(value) {
        if (value == null) return '';
        return String(value).replace(/[&<>"']/g, function (ch) {
            return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch];
        });
    }

    function venueLink(url) {
        if (!url) return '';
        return '<a href="' + escapeHtml(url) + '" target="_blank" rel="noopener" ' +
            'class="inline-flex items-center text-sm font-semibold text-csj-purple dark:text-csj-yellow hover:underline">' +
            'Cómo llegar</a>';
    }

    function renderMatches(matches) {
        return matches.map(function (match) {
            const when = escapeHtml(match.date) + (match.has_time ? ' · ' + escapeHtml(match.time) : ' · hora por confirmar');
            const side = (match.is_home === undefined) ? '' :
                '<span class="text-xs text-gray-500 dark:text-gray-400">' + (match.is_home ? 'Local' : 'Visitante') + '</span>';
            return '<li class="border-t border-gray-200 dark:border-gray-700 pt-3">' +
                '<div class="flex items-center justify-between gap-2">' +
                    '<span class="text-sm font-semibold text-csj-purple dark:text-csj-yellow">' + when + '</span>' +
                    side +
                '</div>' +
                '<p class="text-gray-800 dark:text-gray-200">' + escapeHtml(match.home_name) + ' vs ' + escapeHtml(match.away_name) + '</p>' +
                '<p class="text-sm text-gray-500 dark:text-gray-400">' + escapeHtml(match.location_text) + '</p>' +
                venueLink(match.maps_url) +
            '</li>';
        }).join('');
    }

    function renderVenueMatches(matches) {
        return matches.map(function (match) {
            const when = escapeHtml(match.date) + (match.has_time ? ' · ' + escapeHtml(match.time) : ' · hora por confirmar');
            return '<li class="border-t border-gray-200 dark:border-gray-700 pt-3">' +
                '<span class="text-sm font-semibold text-csj-purple dark:text-csj-yellow">' + when + '</span>' +
                '<p class="text-gray-800 dark:text-gray-200">' + escapeHtml(match.home_name) + ' vs ' + escapeHtml(match.away_name) + '</p>' +
            '</li>';
        }).join('');
    }

    function renderDefaultVenue(venue) {
        return '<div class="mt-3 border-t border-gray-200 dark:border-gray-700 pt-3">' +
            '<span class="text-xs uppercase tracking-wide text-gray-500 dark:text-gray-400">Sede habitual</span>' +
            '<p class="text-gray-800 dark:text-gray-200 mt-1">' + escapeHtml(venue.name) + '</p>' +
            '<p class="text-sm text-gray-500 dark:text-gray-400">' + escapeHtml(venue.address) + '</p>' +
            venueLink(venue.maps_url) +
        '</div>';
    }

    function renderVenueCard(venue) {
        const address = venue.street || venue.address;
        let body = '';
        if (venue.matches && venue.matches.length) {
            body = '<ul class="mt-3 space-y-3">' + renderVenueMatches(venue.matches) + '</ul>';
        }
        return '<article class="bg-white dark:bg-gray-800 rounded-xl shadow border-l-4 border-csj-yellow p-4">' +
            '<div class="flex items-center justify-between gap-2">' +
                '<h2 class="text-lg font-bold text-gray-800 dark:text-gray-200">' + escapeHtml(venue.name) + '</h2>' +
                '<span class="text-xs uppercase tracking-wide text-gray-500 dark:text-gray-400">Sede</span>' +
            '</div>' +
            (venue.city ? '<p class="text-sm text-gray-500 dark:text-gray-400">' + escapeHtml(venue.city) + '</p>' : '') +
            (address ? '<p class="text-sm text-gray-500 dark:text-gray-400 mt-1">' + escapeHtml(address) + '</p>' : '') +
            venueLink(venue.maps_url) +
            body +
        '</article>';
    }

    function renderCard(result) {
        if (result.type === 'venue') return renderVenueCard(result);
        let body;
        if (result.matches && result.matches.length) {
            body = '<ul class="mt-3 space-y-3">' + renderMatches(result.matches) + '</ul>';
        } else if (result.default_venue) {
            body = renderDefaultVenue(result.default_venue);
        } else {
            body = '<p class="text-sm text-gray-500 dark:text-gray-400 mt-3">Sin próximos partidos ni sede registrada.</p>';
        }
        return '<article class="bg-white dark:bg-gray-800 rounded-xl shadow border-l-4 border-csj-purple p-4">' +
            '<div class="flex items-center justify-between gap-2">' +
                '<h2 class="text-lg font-bold text-gray-800 dark:text-gray-200">' + escapeHtml(result.team_name) + '</h2>' +
                (result.category ? '<span class="text-xs text-gray-500 dark:text-gray-400">' + escapeHtml(result.category) + '</span>' : '') +
            '</div>' +
            (result.club_name ? '<p class="text-sm text-gray-500 dark:text-gray-400">' + escapeHtml(result.club_name) + '</p>' : '') +
            body +
        '</article>';
    }

    const emptyMessage = '<p class="text-center text-gray-500 dark:text-gray-400 py-6">No se han encontrado resultados.</p>';
    const errorMessage = '<p class="text-center text-gray-500 dark:text-gray-400 py-6">No se ha podido buscar. Inténtalo de nuevo.</p>';

    let timer = null;
    let controller = null;

    function runSearch() {
        const query = input.value.trim();
        if (query.length < minLength) {
            if (hintEl) hintEl.classList.toggle('hidden', query.length === 0);
            resultsEl.innerHTML = '';
            return;
        }
        if (hintEl) hintEl.classList.add('hidden');
        if (controller) controller.abort();
        controller = new AbortController();

        fetch(searchUrl + '?q=' + encodeURIComponent(query), { signal: controller.signal })
            .then(function (response) {
                if (!response.ok) return null;
                return response.json();
            })
            .then(function (data) {
                if (data === null) return;
                const results = data.results || [];
                resultsEl.innerHTML = results.length ? results.map(renderCard).join('') : emptyMessage;
            })
            .catch(function (error) {
                // Un abort() de una pulsación nueva no es un fallo: se ignora.
                if (error && error.name === 'AbortError') return;
                resultsEl.innerHTML = errorMessage;
            });
    }

    input.addEventListener('input', function () {
        clearTimeout(timer);
        timer = setTimeout(runSearch, DEBOUNCE_MS);
    });

    form.addEventListener('submit', function (event) {
        event.preventDefault();
        clearTimeout(timer);
        runSearch();
    });
})();
