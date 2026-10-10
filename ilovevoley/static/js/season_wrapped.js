// Wrapped de temporada (#458): visor de pantallas, compartir una o todas y descargar.
(function () {
    const root = document.getElementById('wrapped');
    if (!root) return;

    const image = document.getElementById('wrapped-image');
    const bars = root.querySelectorAll('[data-bar]');
    const count = Number(root.dataset.count);
    const msg = root.dataset;
    let index = 0;
    let ready = null; // Files generados, a la espera del toque que abre el menú de compartir

    function url(n, isPreview) {
        const u = new URL(msg.pngUrl.replace(/\/0\.png$/, '/' + n + '.png'), window.location.origin);
        new URLSearchParams(msg.query).forEach(function (v, k) { u.searchParams.set(k, v); });
        if (isPreview) u.searchParams.set('preview', '1');
        return u.toString();
    }

    function toast(kind, text) { if (window.showToast) window.showToast(kind, text); }

    function show(n) {
        index = Math.max(0, Math.min(count - 1, n));
        ready = null;
        image.classList.add('opacity-50');
        image.src = url(index, true);
        bars.forEach(function (bar, i) {
            bar.classList.toggle('bg-csj-purple-dark', i <= index);
            bar.classList.toggle('bg-line', i > index);
        });
    }
    image.addEventListener('load', function () { image.classList.remove('opacity-50'); });
    image.addEventListener('error', function () { image.classList.remove('opacity-50'); toast('error', msg.msgError); });
    document.getElementById('wrapped-next').addEventListener('click', function () { show(index + 1); });
    document.getElementById('wrapped-prev').addEventListener('click', function () { show(index - 1); });

    async function fetchFiles(all) {
        const numbers = all ? Array.from({ length: count }, function (_, i) { return i; }) : [index];
        return Promise.all(numbers.map(async function (n) {
            const response = await fetch(url(n, false)).catch(function () { return null; });
            if (!response || !response.ok) throw new Error(msg.msgError);
            return new File([await response.blob()], msg.filename + '-' + (n + 1) + '.png', { type: 'image/png' });
        }));
    }

    function download(files) {
        files.forEach(function (file) {
            const href = URL.createObjectURL(file);
            const link = document.createElement('a');
            link.href = href;
            link.download = file.name;
            document.body.appendChild(link);
            link.click();
            link.remove();
            URL.revokeObjectURL(href);
        });
        toast('info', msg.msgDownloaded);
    }

    async function generate(button, all) {
        button.disabled = true;
        toast('info', msg.msgGenerating);
        try { return await fetchFiles(all); }
        catch (error) { toast('error', error.message); return null; }
        finally { button.disabled = false; }
    }

    function bindShare(button, all) {
        button.dataset.label = button.textContent;
        button.addEventListener('click', async function () {
            if (ready) {
                const files = ready;
                ready = null;
                button.textContent = button.dataset.label;
                navigator.share({ files: files, title: msg.shareTitle }).catch(function (error) {
                    if (error && error.name !== 'AbortError') download(files);
                });
                return;
            }
            const files = await generate(button, all);
            if (!files) return;
            // navigator.share() exige un toque reciente: generar tarda, así que se pide un segundo toque.
            if (navigator.canShare && navigator.canShare({ files: files })) {
                ready = files;
                button.textContent = msg.msgTap;
                toast('info', msg.msgReady);
            } else {
                download(files);
            }
        });
    }
    bindShare(document.getElementById('wrapped-share'), false);
    bindShare(document.getElementById('wrapped-share-all'), true);
    document.getElementById('wrapped-download').addEventListener('click', async function () {
        const files = await generate(this, false);
        if (files) download(files);
    });

    show(0);
})();
