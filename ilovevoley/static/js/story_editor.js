// Editor táctil de la story personalizada (modo "Personalizar" de la tarjeta de resultado).
// El navegador solo edita un layout JSON normalizado (0-1); el servidor renderiza las capas
// del preview (fondo y marcador) y la imagen final.
(function () {
    'use strict';

    const modal = document.getElementById('story-editor');
    const openButton = document.getElementById('story-editor-open');
    if (!modal || !openButton || typeof interact === 'undefined') return;

    const msg = modal.dataset;
    const stage = document.getElementById('se-stage');
    const wrap = document.getElementById('se-stage-wrap');
    const preview = document.getElementById('se-preview');
    const scoreBox = document.getElementById('se-score-box');
    const scoreLayer = document.getElementById('se-score-layer');
    const zoomInput = document.getElementById('se-zoom');
    const photosBox = document.getElementById('se-photos');
    const MAX_ZOOM = 4;

    const state = {
        photoId: null,
        format: 'story',
        compositionId: null,
        layout: {
            photo: { zoom: 1, cx: 0.5, cy: 0.5 },
            score: { x: 0.5, y: null, scale: 1 },
            gradients: { top: {}, bottom: {} },
        },
        info: null,
    };

    const clamp = (value, low, high) => Math.min(high, Math.max(low, value));
    const toast = (type, text) => { if (window.showToast) window.showToast(type, text); };

    function csrfToken() {
        const match = document.cookie.match(/(?:^|; )csrftoken=([^;]+)/);
        return match ? decodeURIComponent(match[1]) : '';
    }

    // ---- Vista previa: dos capas del servidor (fondo y bloque del marcador) ----
    // El marcador es una imagen dentro de su caja: moverlo no pide nada al servidor y
    // escalarlo solo repide su capa (una imagen pequeña) al soltar. Foto, zoom y degradados
    // repiden el fondo. Cada capa tiene una sola petición en vuelo.

    const timers = {};
    let objectUrl = null;
    let scoreUrl = null;
    let scoreBusy = false;

    // Los sliders esperan 250 ms; los gestos piden el render nada más soltar (delay 0).
    function schedule(delay, layers) {
        (layers || ['background']).forEach(function (name) {
            clearTimeout(timers[name]);
            timers[name] = setTimeout(loaders[name], delay === undefined ? 250 : delay);
        });
    }

    function cardParams(extra) {
        return new URLSearchParams(Object.assign({
            format: state.format,
            style: 'personalizada',
            photo_id: state.photoId,
            layout: JSON.stringify(state.layout),
        }, extra));
    }

    function sizeStage() {
        const ratio = state.format === 'story' ? 9 / 16 : 1;
        const width = Math.min(wrap.clientWidth || 320, window.innerHeight * 0.55 * ratio);
        stage.style.width = `${Math.max(160, width)}px`;
        stage.style.aspectRatio = state.format === 'story' ? '9 / 16' : '1 / 1';
    }

    // Abortar en el cliente no cancela el render del servidor: los cambios que llegan con una
    // petición en vuelo se juntan en un único render posterior.
    function layerLoader(layer, apply) {
        let inflight = false;
        let stale = false;

        async function load() {
            if (!state.photoId) {
                toast('error', msg.msgNoPhoto);
                return;
            }
            if (inflight) {
                stale = true;
                return;
            }
            inflight = true;
            stale = false;
            try {
                await fetchLayer(layer, apply);
            } finally {
                inflight = false;
                if (stale) load();
            }
        }
        return load;
    }

    async function fetchLayer(layer, apply) {
        const dim = layer === 'background';
        if (dim) {
            sizeStage();
            stage.classList.add('opacity-80');
        }
        let response;
        try {
            response = await fetch(`${msg.cardUrl}?${cardParams({ preview: '1', layer })}`);
        } catch (error) {
            toast('error', msg.msgError);
            return;
        } finally {
            if (dim) stage.classList.remove('opacity-80');
        }
        if (!response.ok) {
            let text = msg.msgError;
            try { text = (await response.json()).error || text; } catch (_) { /* mensaje genérico */ }
            toast('error', text);
            return;
        }
        apply(JSON.parse(response.headers.get('X-Layout-Info') || '{}'), await response.blob());
    }

    function applyBackground(info, blob) {
        // El tamaño del marcador lo manda su propia capa; del fondo solo vale si aún no hay.
        const box = state.info && state.info.score_box;
        state.info = Object.assign({}, state.info, info);
        if (box) state.info.score_box = box;
        if (objectUrl) URL.revokeObjectURL(objectUrl);
        objectUrl = URL.createObjectURL(blob);
        preview.onload = function () {
            preview.style.transform = '';
            preview.style.objectFit = '';
        };
        preview.src = objectUrl;
        syncControls();
    }

    function applyScore(info, blob) {
        state.info = Object.assign({}, state.info, { score_box: info.score_box });
        if (scoreUrl) URL.revokeObjectURL(scoreUrl);
        scoreUrl = URL.createObjectURL(blob);
        scoreLayer.src = scoreUrl;
        scoreBox.classList.remove('hidden');
        // Si el usuario está moviendo o escalando la caja, no se la pisa con un tamaño antiguo.
        if (!scoreBusy) placeScoreBox();
    }

    const loaders = {
        background: layerLoader('background', applyBackground),
        score: layerLoader('score', applyScore),
    };

    // Caja del marcador (0-1): el tamaño viene de su capa y la posición del layout del cliente,
    // que es la que manda mientras no se pida otra capa. Misma regla de límites que el servidor.
    function scoreRect() {
        const base = state.info && state.info.score_box;
        if (!base) return null;
        const score = state.layout.score;
        const width = base[2];
        const height = base[3];
        return [
            clamp(score.x - width / 2, 0, 1 - width),
            score.y === null ? base[1] : clamp(score.y - height / 2, 0, 1 - height),
            width,
            height,
        ];
    }

    function placeScoreBox() {
        const box = scoreRect();
        if (!box) return;
        scoreBox.style.transform = '';
        scoreBox.style.left = `${box[0] * 100}%`;
        scoreBox.style.top = `${box[1] * 100}%`;
        scoreBox.style.width = `${box[2] * 100}%`;
        scoreBox.style.height = `${box[3] * 100}%`;
    }

    // ---- Controles (zoom y degradados) ----

    function syncControls() {
        const info = state.info || {};
        if (info.photo) {
            zoomInput.min = info.photo.min_zoom.toFixed(2);
            zoomInput.max = MAX_ZOOM;
            zoomInput.value = clamp(state.layout.photo.zoom, info.photo.min_zoom, MAX_ZOOM);
        }
        ['top', 'bottom'].forEach(function (edge) {
            const server = (info.layout && info.layout.gradients[edge]) || {};
            const mine = state.layout.gradients[edge];
            const fieldset = modal.querySelector(`[data-se-gradient="${edge}"]`);
            fieldset.querySelector('[data-se-prop="color"]').value = mine.color || msg.primary;
            fieldset.querySelector('[data-se-prop="alpha"]').value = mine.alpha !== undefined ? mine.alpha : server.alpha;
            fieldset.querySelector('[data-se-prop="height"]').value = mine.height !== undefined ? mine.height : server.height;
        });
    }

    zoomInput.addEventListener('input', function () {
        state.layout.photo.zoom = parseFloat(zoomInput.value);
        schedule();
    });

    modal.querySelectorAll('[data-se-gradient]').forEach(function (fieldset) {
        const edge = fieldset.dataset.seGradient;
        fieldset.querySelectorAll('[data-se-prop]').forEach(function (input) {
            input.addEventListener('input', function () {
                const prop = input.dataset.seProp;
                state.layout.gradients[edge][prop] = prop === 'color' ? input.value : parseFloat(input.value);
                schedule();
            });
        });
    });

    function syncFormatButtons() {
        modal.querySelectorAll('.se-format').forEach(function (button) {
            const active = button.dataset.seFormat === state.format;
            button.classList.toggle('bg-csj-purple-dark', active);
            button.classList.toggle('text-white', active);
            button.classList.toggle('text-muted', !active);
        });
    }

    modal.querySelectorAll('.se-format').forEach(function (button) {
        button.addEventListener('click', function () {
            state.format = button.dataset.seFormat;
            syncFormatButtons();
            state.info = null;
            // La caja del marcador depende del formato: se vuelve al anclaje por defecto.
            state.layout.score.y = null;
            scoreBox.classList.add('hidden');
            scoreLayer.removeAttribute('src');
            schedule(0, ['background', 'score']);
        });
    });

    // ---- Fotos: se reutilizan las miniaturas que ya pinta la página ----

    function selectPhoto(photoId, keepFocus) {
        state.photoId = photoId;
        if (!keepFocus) {
            state.layout.photo.cx = 0.5;
            state.layout.photo.cy = 0.5;
        }
        photosBox.querySelectorAll('button').forEach(function (button) {
            const selected = button.dataset.photoId === photoId;
            const thumb = selected && button.querySelector('img');
            // Hasta que llega el primer render se enseña la miniatura (ya cargada) en vez de gris.
            if (thumb && !state.info) {
                preview.style.objectFit = 'cover';
                preview.src = thumb.currentSrc || thumb.src;
            }
            button.classList.toggle('border-csj-purple', selected);
            button.classList.toggle('border-transparent', !selected);
            button.setAttribute('aria-pressed', selected ? 'true' : 'false');
        });
        // La capa del marcador no depende de la foto: solo se pide la primera vez.
        schedule(0, state.info && state.info.score_box ? ['background'] : ['background', 'score']);
    }

    function buildPhotoStrip() {
        photosBox.textContent = '';
        const source = document.querySelectorAll('#result-card-photo-modal .result-card-photo-option');
        const options = source.length ? source : document.querySelectorAll('#result-card-photo-picker .result-card-photo-option');
        options.forEach(function (option) {
            const button = option.cloneNode(true);
            button.className = 'relative w-12 h-12 rounded-lg overflow-hidden border-2 border-transparent focus:outline-none';
            button.querySelectorAll('.result-card-photo-check').forEach(function (check) { check.remove(); });
            button.addEventListener('click', function () { selectPhoto(button.dataset.photoId); });
            photosBox.appendChild(button);
        });
    }

    // ---- Gestos con interact.js ----

    // Arrastrar la foto (fondo del escenario) y pellizcar para el zoom.
    let pan = { x: 0, y: 0 };
    let pinch = { zoom: 1, scale: 1 };

    function photoTransform() {
        preview.style.transform = `translate(${pan.x}px, ${pan.y}px) scale(${pinch.scale})`;
    }

    interact(stage)
        .draggable({
            ignoreFrom: '#se-score-box',
            listeners: {
                start() { pan = { x: 0, y: 0 }; },
                move(event) {
                    pan.x += event.dx;
                    pan.y += event.dy;
                    photoTransform();
                },
                end() {
                    const photo = state.info && state.info.photo;
                    if (photo) {
                        const photoState = state.layout.photo;
                        const stageW = stage.clientWidth;
                        const stageH = stage.clientHeight;
                        // El foco (cx, cy) es el punto de la foto que queda en el centro; fuera de
                        // [0.5/w, 1-0.5/w] la foto ya toca el borde del lienzo y no se movería.
                        if (photo.w > 1) {
                            photoState.cx = clamp(photoState.cx - pan.x / stageW / photo.w, 0.5 / photo.w, 1 - 0.5 / photo.w);
                        }
                        if (photo.h > 1) {
                            photoState.cy = clamp(photoState.cy - pan.y / stageH / photo.h, 0.5 / photo.h, 1 - 0.5 / photo.h);
                        }
                    }
                    pan = { x: 0, y: 0 };
                    schedule(0);
                },
            },
        })
        .gesturable({
            listeners: {
                start() { pinch = { zoom: state.layout.photo.zoom, scale: 1 }; },
                move(event) {
                    const min = state.info && state.info.photo ? state.info.photo.min_zoom : 0.1;
                    const zoom = clamp(pinch.zoom * event.scale, min, MAX_ZOOM);
                    pinch.scale = zoom / pinch.zoom;
                    photoTransform();
                },
                end() {
                    state.layout.photo.zoom = clamp(pinch.zoom * pinch.scale, 0.1, MAX_ZOOM);
                    pinch.scale = 1;
                    schedule(0);
                },
            },
        });

    // Mover y escalar (manteniendo la proporción) el bloque del marcador.
    let drag = { x: 0, y: 0 };

    function commitScoreBox(left, top, width, height) {
        const stageW = stage.clientWidth;
        const stageH = stage.clientHeight;
        state.layout.score.x = clamp((left + width / 2) / stageW, 0, 1);
        state.layout.score.y = clamp((top + height / 2) / stageH, 0, 1);
    }

    interact(scoreBox)
        .draggable({
            listeners: {
                start() {
                    drag = { x: 0, y: 0 };
                    scoreBusy = true;
                },
                move(event) {
                    drag.x += event.dx;
                    drag.y += event.dy;
                    scoreBox.style.transform = `translate(${drag.x}px, ${drag.y}px)`;
                },
                end() {
                    scoreBusy = false;
                    // Sin petición: la capa ya está en pantalla, solo cambian las coordenadas.
                    commitScoreBox(
                        scoreBox.offsetLeft + drag.x, scoreBox.offsetTop + drag.y,
                        scoreBox.offsetWidth, scoreBox.offsetHeight
                    );
                    placeScoreBox();
                },
            },
        })
        .resizable({
            edges: { right: '#se-score-handle', bottom: '#se-score-handle' },
            modifiers: [interact.modifiers.aspectRatio({ ratio: 'preserve' })],
            listeners: {
                start() { scoreBusy = true; },
                move(event) {
                    scoreBox.style.width = `${event.rect.width}px`;
                    scoreBox.style.height = `${event.rect.height}px`;
                },
                end() {
                    scoreBusy = false;
                    const base = state.info && state.info.score_box;
                    if (base) {
                        const score = state.layout.score;
                        const next = clamp(score.scale * (scoreBox.offsetWidth / stage.clientWidth) / base[2], 0.5, 1.2);
                        const factor = next / score.scale;
                        score.scale = next;
                        state.info.score_box = [base[0], base[1], base[2] * factor, base[3] * factor];
                        // La esquina superior izquierda se mantiene fija al escalar.
                        commitScoreBox(
                            scoreBox.offsetLeft, scoreBox.offsetTop,
                            state.info.score_box[2] * stage.clientWidth,
                            state.info.score_box[3] * stage.clientHeight
                        );
                    }
                    placeScoreBox();
                    // Mientras llega, la capa se ve estirada por CSS; al llegar queda nítida.
                    schedule(0, ['score']);
                },
            },
        });

    // ---- Guardar, descargar y compartir ----

    async function save() {
        const response = await fetch(msg.saveUrl, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken() },
            body: JSON.stringify({
                id: state.compositionId,
                photo_id: state.photoId,
                format: state.format,
                layout: state.layout,
            }),
        });
        const data = await response.json().catch(function () { return {}; });
        if (!response.ok) {
            toast('error', data.error || msg.msgError);
            return;
        }
        state.compositionId = data.id;
        toast('info', msg.msgSaved);
    }

    async function fetchFull() {
        const response = await fetch(`${msg.cardUrl}?${cardParams()}`);
        if (!response.ok) {
            let text = msg.msgError;
            try { text = (await response.json()).error || text; } catch (_) { /* mensaje genérico */ }
            throw new Error(text);
        }
        return { blob: await response.blob(), filename: `${msg.filename}-${state.format}.png` };
    }

    function downloadBlob(blob, filename) {
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = filename;
        document.body.appendChild(link);
        link.click();
        link.remove();
        URL.revokeObjectURL(url);
    }

    const actionButtons = [document.getElementById('se-share'), document.getElementById('se-download'), document.getElementById('se-save')]
        .filter(Boolean);

    async function busy(run) {
        actionButtons.forEach(function (button) { button.disabled = true; });
        try {
            await run();
        } catch (error) {
            toast('error', (error && error.message) || msg.msgError);
        } finally {
            actionButtons.forEach(function (button) { button.disabled = false; });
        }
    }

    document.getElementById('se-download').addEventListener('click', function () {
        busy(async function () {
            toast('info', msg.msgGenerating);
            const { blob, filename } = await fetchFull();
            downloadBlob(blob, filename);
            toast('info', msg.msgDownloaded);
        });
    });

    // navigator.share() exige un toque justo antes: como generar tarda, se deja la imagen
    // lista y se pide un segundo toque (mismo patrón que los botones de la tarjeta).
    const shareButton = document.getElementById('se-share');
    let ready = null;

    shareButton.addEventListener('click', function () {
        if (ready) {
            const { blob, filename, file } = ready;
            ready = null;
            shareButton.textContent = msg.msgShare;
            navigator.share({ files: [file], text: msg.shareText }).catch(function (error) {
                if (error && error.name === 'AbortError') return;
                downloadBlob(blob, filename);
                toast('info', msg.msgDownloaded);
            });
            return;
        }
        busy(async function () {
            toast('info', msg.msgGenerating);
            const { blob, filename } = await fetchFull();
            const file = new File([blob], filename, { type: 'image/png' });
            if (navigator.canShare && navigator.canShare({ files: [file] })) {
                ready = { blob, filename, file };
                shareButton.textContent = msg.msgTapShare;
                return;
            }
            downloadBlob(blob, filename);
            toast('info', msg.msgDownloaded);
        });
    });

    const saveButton = document.getElementById('se-save');
    if (saveButton) saveButton.addEventListener('click', function () { busy(save); });

    // Cualquier cambio invalida la imagen que estaba lista para compartir.
    ['input', 'click'].forEach(function (type) {
        modal.addEventListener(type, function (event) {
            if (ready && event.target !== shareButton) {
                ready = null;
                shareButton.textContent = msg.msgShare;
            }
        });
    });

    // ---- Abrir y cerrar ----

    function open(keepFocus) {
        buildPhotoStrip();
        const root = document.getElementById('result-card-actions');
        const first = photosBox.querySelector('button');
        const initial = state.photoId || (root && root.dataset.photoId) || (first && first.dataset.photoId);
        modal.classList.remove('hidden');
        modal.classList.add('flex');
        document.body.classList.add('overflow-hidden');
        if (initial) selectPhoto(String(initial), keepFocus);
        else toast('error', msg.msgNoPhoto);
    }

    function close() {
        modal.classList.add('hidden');
        modal.classList.remove('flex');
        document.body.classList.remove('overflow-hidden');
    }

    openButton.addEventListener('click', function () { open(false); });
    document.getElementById('se-close').addEventListener('click', close);
    modal.addEventListener('click', function (event) { if (event.target === modal) close(); });
    document.addEventListener('keydown', function (event) {
        if (event.key === 'Escape' && !modal.classList.contains('hidden')) close();
    });
    window.addEventListener('resize', function () { if (!modal.classList.contains('hidden')) sizeStage(); });

    // Expuesto para "Mis creaciones": reabrir una composición guardada.
    window.StoryEditor = {
        open(saved) {
            if (saved) {
                state.compositionId = saved.id;
                state.format = saved.format;
                syncFormatButtons();
                state.photoId = String(saved.photo_id);
                state.layout = saved.layout;
                state.info = null;
                scoreBox.classList.add('hidden');
                if (state.layout.photo.zoom == null) state.layout.photo.zoom = 1;
            }
            open(Boolean(saved));
        },
    };

    const savedElement = document.getElementById('story-editor-saved');
    if (savedElement) window.StoryEditor.open(JSON.parse(savedElement.textContent));
}());
