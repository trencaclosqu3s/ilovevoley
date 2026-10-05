(function () {
    'use strict';

    const form = document.querySelector('[data-results-filters]');
    if (!form) return;

    const FILTER_PARAMS = ['period', 'season', 'category', 'teams', 'all_teams'];
    const STORAGE_KEY = 'ilovevoley.results.filters';

    function currentFilterString() {
        const params = new URLSearchParams(window.location.search);
        const selected = new URLSearchParams();
        FILTER_PARAMS.forEach(function (key) {
            params.getAll(key).forEach(function (value) { selected.append(key, value); });
        });
        return selected.toString();
    }

    // Recuerda los filtros activos en la sesión y, si se entra a Resultados sin
    // parámetros (por ejemplo desde el menú), reaplica los últimos usados.
    (function rememberFilters() {
        const active = currentFilterString();
        if (active) {
            try { sessionStorage.setItem(STORAGE_KEY, active); } catch (e) { /* almacenamiento no disponible */ }
            return;
        }
        let saved = null;
        try { saved = sessionStorage.getItem(STORAGE_KEY); } catch (e) { saved = null; }
        if (saved) {
            window.location.replace(window.location.pathname + '?' + saved);
        }
    })();

    const input = document.getElementById('results-team-search');
    const suggestions = document.getElementById('results-team-suggestions');
    const chips = document.getElementById('results-team-chips');
    const searchUrl = form.dataset.searchUrl;
    if (!input || !suggestions || !chips || !searchUrl) return;

    const DEBOUNCE_MS = 250;
    let timer = null;

    function selectedIds() {
        return Array.from(chips.querySelectorAll('input[name="teams"]')).map(function (el) { return el.value; });
    }

    function addChip(team) {
        if (selectedIds().indexOf(String(team.id)) !== -1) return;
        const chip = document.createElement('span');
        chip.className = 'inline-flex items-center gap-1 px-2 py-1 rounded-full bg-csj-purple text-white text-xs';
        chip.textContent = team.name;
        const hidden = document.createElement('input');
        hidden.type = 'hidden';
        hidden.name = 'teams';
        hidden.value = team.id;
        const remove = document.createElement('button');
        remove.type = 'button';
        remove.textContent = '×';
        remove.setAttribute('aria-label', form.dataset.removeLabel + ' ' + team.name);
        remove.addEventListener('click', function () { chip.remove(); });
        chip.append(hidden, remove);
        chips.appendChild(chip);
    }

    function clearSuggestions() {
        suggestions.replaceChildren();
        suggestions.classList.add('hidden');
    }

    function renderSuggestions(teams) {
        suggestions.replaceChildren();
        teams.forEach(function (team) {
            const item = document.createElement('button');
            item.type = 'button';
            item.className = 'block w-full text-left px-3 py-2 text-sm hover:bg-gray-100 dark:hover:bg-gray-700';
            item.textContent = team.category ? team.name + ' (' + team.category + ')' : team.name;
            item.addEventListener('click', function () {
                addChip(team);
                input.value = '';
                clearSuggestions();
            });
            suggestions.appendChild(item);
        });
        suggestions.classList.toggle('hidden', teams.length === 0);
    }

    input.addEventListener('input', function () {
        clearTimeout(timer);
        const query = input.value.trim();
        if (query.length < 2) {
            clearSuggestions();
            return;
        }
        timer = setTimeout(function () {
            fetch(searchUrl + '?q=' + encodeURIComponent(query), { headers: { 'Accept': 'application/json' } })
                .then(function (response) { return response.ok ? response.json() : { teams: [] }; })
                .then(function (data) {
                    // Descarta respuestas de un texto que ya no es el actual.
                    if (input.value.trim() === query) renderSuggestions(data.teams);
                })
                .catch(clearSuggestions);
        }, DEBOUNCE_MS);
    });

    chips.querySelectorAll('button').forEach(function (btn) {
        btn.addEventListener('click', function () { btn.closest('span').remove(); });
    });

    // Enter en el buscador no debe enviar el formulario con el texto a medias.
    input.addEventListener('keydown', function (event) {
        if (event.key === 'Enter') event.preventDefault();
    });
})();
