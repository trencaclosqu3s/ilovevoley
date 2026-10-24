// Compartir el clip 9:16 de una jugada (#629) con navigator.share.
(function () {
    if (!navigator.canShare) return;
    document.querySelectorAll('.mark-clip-share').forEach(function (button) {
        let ready = null;
        const label = button.textContent;
        button.hidden = false;
        button.addEventListener('click', async function () {
            if (ready) {
                const file = ready;
                ready = null;
                button.textContent = label;
                navigator.share({ files: [file] }).catch(function (error) {
                    if (error && error.name !== 'AbortError') window.location = button.dataset.url;
                });
                return;
            }
            button.disabled = true;
            try {
                const response = await fetch(button.dataset.url, { credentials: 'same-origin' });
                if (!response.ok) throw new Error(response.status);
                const file = new File([await response.blob()], button.dataset.filename, { type: 'video/mp4' });
                // navigator.share() exige un toque reciente y bajar el clip tarda:
                // se deja listo y se pide un segundo toque. Sin soporte, se descarga.
                if (navigator.canShare({ files: [file] })) {
                    ready = file;
                    button.textContent = button.dataset.tapLabel;
                } else {
                    window.location = button.dataset.url;
                }
            } catch (error) {
                window.location = button.dataset.url;
            } finally {
                button.disabled = false;
            }
        });
    });
})();
