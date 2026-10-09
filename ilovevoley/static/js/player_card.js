// Cromo del jugador (#457): vista previa según la foto elegida, compartir y descargar.
(function () {
    const root = document.getElementById('player-card');
    if (!root) return;

    const preview = document.getElementById('player-card-preview');
    const shareButton = document.getElementById('player-card-share');
    const downloadButton = document.getElementById('player-card-download');
    const msg = root.dataset;
    let photo = root.dataset.photo;
    let ready = null; // File generado, a la espera del toque que abre el menú de compartir

    function cardUrl(isPreview) {
        const url = new URL(root.dataset.cardUrl, window.location.origin);
        url.searchParams.set('foto', photo);
        if (isPreview) url.searchParams.set('preview', '1');
        return url.toString();
    }

    function toast(kind, text) {
        if (window.showToast) window.showToast(kind, text);
    }

    root.querySelectorAll('[data-photo-option]').forEach(function (option) {
        option.addEventListener('click', function () {
            photo = option.dataset.photoOption;
            ready = null;
            shareButton.textContent = shareButton.dataset.label;
            root.querySelectorAll('[data-photo-option]').forEach(function (other) {
                other.setAttribute('aria-pressed', String(other === option));
            });
            preview.classList.add('opacity-50');
            preview.src = cardUrl(true);
        });
    });
    preview.addEventListener('load', function () { preview.classList.remove('opacity-50'); });

    async function fetchCard() {
        const response = await fetch(cardUrl(false)).catch(function () { return null; });
        if (!response || !response.ok) throw new Error(msg.msgError);
        return new File([await response.blob()], root.dataset.filename, { type: 'image/png' });
    }

    function download(file) {
        const url = URL.createObjectURL(file);
        const link = document.createElement('a');
        link.href = url;
        link.download = file.name;
        document.body.appendChild(link);
        link.click();
        link.remove();
        URL.revokeObjectURL(url);
        toast('info', msg.msgDownloaded);
    }

    async function generate(button) {
        button.disabled = true;
        toast('info', msg.msgGenerating);
        try {
            return await fetchCard();
        } catch (error) {
            toast('error', error.message);
            return null;
        } finally {
            button.disabled = false;
        }
    }

    shareButton.dataset.label = shareButton.textContent;
    shareButton.addEventListener('click', async function () {
        if (ready) {
            const file = ready;
            ready = null;
            shareButton.textContent = shareButton.dataset.label;
            navigator.share({ files: [file], title: msg.shareTitle }).catch(function (error) {
                if (error && error.name !== 'AbortError') download(file);
            });
            return;
        }
        const file = await generate(shareButton);
        if (!file) return;
        // navigator.share() exige un toque reciente: generar tarda, así que se deja
        // listo y se pide un segundo toque. Sin soporte para compartir, se descarga.
        if (navigator.canShare && navigator.canShare({ files: [file] })) {
            ready = file;
            shareButton.textContent = msg.msgTap;
            toast('info', msg.msgReady);
        } else {
            download(file);
        }
    });

    downloadButton.addEventListener('click', async function () {
        const file = await generate(downloadButton);
        if (file) download(file);
    });
})();
