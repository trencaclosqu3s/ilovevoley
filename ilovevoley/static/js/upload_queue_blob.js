/*
 * Materialización de blobs para la cola de subida (#611, #636).
 * Compartido entre upload_queue.js y sw.js — mantener una sola copia de la lógica.
 */
(function (global) {
    "use strict";

    var DEFAULT_MIME = "image/jpeg";

    function materializeFromRecord(item) {
        if (item.file_bytes && item.file_bytes.byteLength) {
            return Promise.resolve(
                new Blob([item.file_bytes], { type: item.file_mime || DEFAULT_MIME })
            );
        }
        var blob = item.file_blob;
        if (!blob || typeof blob.arrayBuffer !== "function") {
            return Promise.resolve(null);
        }
        // En iOS el blob guardado en IndexedDB puede perder su contenido y arrayBuffer() rechaza:
        // null = ilegible, no un corte de red que merezca reintentos.
        return blob.arrayBuffer().then(function (buf) {
            if (!buf || !buf.byteLength) {
                return null;
            }
            return new Blob([buf], { type: blob.type || DEFAULT_MIME });
        }).catch(function () {
            return null;
        });
    }

    global.UploadQueueBlob = {
        materializeFromRecord: materializeFromRecord,
        BLOB_READ_ERROR: "No se pudo leer la imagen guardada en el dispositivo."
    };
})(typeof self !== "undefined" ? self : window);
