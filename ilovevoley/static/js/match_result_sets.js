/*
 * Parciales manuales en el modal de resultado.
 *
 * Crea filas de parciales (local-visitante), calcula el marcador de sets a
 * partir de ellas y expone collect() para enviarlas al servidor.
 */
(function () {
    'use strict';

    function createSetScores(opts) {
        opts = opts || {};
        var rowsEl = document.getElementById(opts.rowsEl);
        var addBtn = document.getElementById(opts.addBtn);
        var homeEl = document.getElementById(opts.homeEl);
        var awayEl = document.getElementById(opts.awayEl);
        var maxSets = opts.maxSets || 5;

        if (!rowsEl) {
            return { reset: function () {}, set: function () {}, collect: function () { return []; } };
        }

        function someInputs(node, handler) {
            Array.prototype.forEach.call(node.querySelectorAll('input'), function (input) {
                input.addEventListener('input', handler);
            });
        }

        function update() {
            if (!homeEl || !awayEl) return;
            var scores = collect();
            if (!scores || !scores.length) return;
            var homeWon = 0;
            scores.forEach(function (set) {
                if (set[0] > set[1]) homeWon += 1;
            });
            homeEl.value = homeWon;
            awayEl.value = scores.length - homeWon;
        }

        function addRow(home, away) {
            if (rowsEl.children.length >= maxSets) return;
            var row = document.createElement('div');
            row.className = 'flex items-center justify-center gap-2';
            row.innerHTML =
                '<input type="number" min="0" max="99" inputmode="numeric" ' +
                'class="set-home w-16 px-2 py-1.5 border border-gray-300 dark:border-gray-600 ' +
                'rounded-lg text-center dark:bg-gray-700 dark:text-gray-100 ' +
                'focus:ring-2 focus:ring-csj-purple focus:border-transparent" value="' +
                (home === undefined || home === null ? '' : home) + '">' +
                '<span class="text-gray-500 font-semibold">-</span>' +
                '<input type="number" min="0" max="99" inputmode="numeric" ' +
                'class="set-away w-16 px-2 py-1.5 border border-gray-300 dark:border-gray-600 ' +
                'rounded-lg text-center dark:bg-gray-700 dark:text-gray-100 ' +
                'focus:ring-2 focus:ring-csj-purple focus:border-transparent" value="' +
                (away === undefined || away === null ? '' : away) + '">' +
                '<button type="button" class="set-remove text-gray-400 hover:text-red-500 px-1 text-lg" ' +
                'aria-label="Quitar set">&times;</button>';
            row.querySelector('.set-remove').addEventListener('click', function () {
                row.remove();
                update();
            });
            someInputs(row, update);
            rowsEl.appendChild(row);
            update();
        }

        function collect() {
            var scores = [];
            var rows = rowsEl.children;
            for (var i = 0; i < rows.length; i += 1) {
                var home = rows[i].querySelector('.set-home').value.trim();
                var away = rows[i].querySelector('.set-away').value.trim();
                if (home === '' && away === '') continue;
                if (home === '' || away === '') return null;
                var homeInt = parseInt(home, 10);
                var awayInt = parseInt(away, 10);
                if (isNaN(homeInt) || isNaN(awayInt) || homeInt < 0 || awayInt < 0) return null;
                scores.push([homeInt, awayInt]);
            }
            return scores;
        }

        function reset() {
            rowsEl.innerHTML = '';
        }

        function set(scores) {
            reset();
            (scores || []).forEach(function (score) {
                addRow(score[0], score[1]);
            });
        }

        if (addBtn) {
            addBtn.addEventListener('click', function () { addRow(); });
        }

        return { reset: reset, set: set, collect: collect };
    }

    window.MatchResultSets = { create: createSetScores };
})();
