/*
 * Cola local de subida de fotos tolerante a mala cobertura (#611).
 *
 * - Comprime las imágenes en el navegador (máx. 2560 px, JPEG calidad 0.85) antes de
 *   encolarlas, respetando el límite de 10 MB post-compresión (#121) y dejando que el
 *   servidor ejecute sanitize_image para purgar EXIF/GPS (#86).
 * - Persiste la cola en IndexedDB (ilovevoley_upload_queue) aislada por origen (tenant).
 * - Sube foto a foto a /content/api/imagenes/subir/ con idempotencia por client_upload_id,
 *   reintentos automáticos con backoff exponencial, Background Sync en Service Worker
 *   ('sync-photo-uploads') y fallback en online / visibilitychange / DOMContentLoaded.
 */
(function () {
    "use strict";

    var DB_NAME = "ilovevoley_upload_queue";
    var DB_VERSION = 1;
    var STORE_NAME = "uploads";
    var SYNC_TAG = "sync-photo-uploads";
    // Límite compartido: reintentos HTTP con backoff y pasadas por uploading obsoleto en cleanupStaleItems.
    var MAX_AUTO_ATTEMPTS = 4;
    var BACKOFF_DELAYS_MS = [2000, 5000, 12000, 25000];
    var UPLOAD_TIMEOUT_MS = 45000;
    var MAX_COMPRESSED_BYTES = 10 * 1024 * 1024;
    var MAX_DIMENSION = 2560;
    var JPEG_QUALITY = 0.85;
    var STALE_UPLOADING_MS = 2 * 60 * 1000;
    var EXPIRY_MS = 7 * 24 * 60 * 60 * 1000;

    var isProcessingQueue = false;
    var isPanelCollapsed = false;
    var activeUploadAbortController = null;
    var activeUploadClientId = null;

    function materializeUploadBlob(item) {
        return window.UploadQueueBlob.materializeFromRecord(item);
    }

    function generateUuid() {
        if (window.crypto && typeof window.crypto.randomUUID === "function") {
            return window.crypto.randomUUID();
        }
        return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, function (c) {
            var r = (Math.random() * 16) | 0;
            var v = c === "x" ? r : (r & 0x3) | 0x8;
            return v.toString(16);
        });
    }

    function escapeHtml(str) {
        return String(str || "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#39;");
    }

    function getWidget() {
        return document.getElementById("upload-queue-widget");
    }

    function getI18n(key, fallback) {
        var widget = getWidget();
        if (!widget) {
            return fallback;
        }
        return widget.getAttribute("data-i18n-" + key) || fallback;
    }

    function getUploadEndpoint() {
        var widget = getWidget();
        if (widget && widget.getAttribute("data-upload-endpoint")) {
            return widget.getAttribute("data-upload-endpoint");
        }
        return "/content/api/imagenes/subir/";
    }

    function openDb() {
        return new Promise(function (resolve, reject) {
            if (!("indexedDB" in window)) {
                reject(new Error("IndexedDB no disponible"));
                return;
            }
            var req = window.indexedDB.open(DB_NAME, DB_VERSION);
            req.onupgradeneeded = function (event) {
                var db = event.target.result;
                if (!db.objectStoreNames.contains(STORE_NAME)) {
                    var store = db.createObjectStore(STORE_NAME, { keyPath: "client_upload_id" });
                    store.createIndex("tenant_origin", "tenant_origin", { unique: false });
                    store.createIndex("status", "status", { unique: false });
                }
            };
            req.onsuccess = function () {
                resolve(req.result);
            };
            req.onerror = function () {
                reject(req.error || new Error("No se pudo abrir IndexedDB"));
            };
        });
    }

    function getAllTenantItems() {
        return openDb().then(function (db) {
            return new Promise(function (resolve, reject) {
                var tx = db.transaction(STORE_NAME, "readonly");
                var store = tx.objectStore(STORE_NAME);
                var req = store.getAll();
                req.onsuccess = function () {
                    var all = req.result || [];
                    var origin = window.location.origin;
                    var filtered = all
                        .filter(function (item) {
                            return item.tenant_origin === origin;
                        })
                        .sort(function (a, b) {
                            return (a.created_at || 0) - (b.created_at || 0);
                        });
                    resolve(filtered);
                };
                req.onerror = function () {
                    reject(req.error);
                };
            });
        }).catch(function () {
            return [];
        });
    }

    function getItemById(clientUploadId) {
        return openDb()
            .then(function (db) {
                return new Promise(function (resolve, reject) {
                    var tx = db.transaction(STORE_NAME, "readonly");
                    var req = tx.objectStore(STORE_NAME).get(clientUploadId);
                    req.onsuccess = function () {
                        resolve(req.result || null);
                    };
                    req.onerror = function () {
                        reject(req.error);
                    };
                });
            })
            .catch(function () {
                return null;
            });
    }

    function putItem(item) {
        return openDb().then(function (db) {
            return new Promise(function (resolve, reject) {
                var tx = db.transaction(STORE_NAME, "readwrite");
                var store = tx.objectStore(STORE_NAME);
                item.updated_at = Date.now();
                store.put(item);
                tx.oncomplete = function () {
                    resolve(item);
                };
                tx.onerror = function () {
                    reject(tx.error);
                };
            });
        });
    }

    function deleteItem(clientUploadId) {
        return openDb().then(function (db) {
            return new Promise(function (resolve, reject) {
                var tx = db.transaction(STORE_NAME, "readwrite");
                tx.objectStore(STORE_NAME).delete(clientUploadId);
                tx.oncomplete = function () {
                    resolve();
                };
                tx.onerror = function () {
                    reject(tx.error);
                };
            });
        });
    }

    function cleanupStaleItems() {
        var now = Date.now();
        return getAllTenantItems().then(function (items) {
            var ops = [];
            var staleUploadIds = [];
            items.forEach(function (item) {
                if (now - (item.created_at || now) > EXPIRY_MS) {
                    ops.push(deleteItem(item.client_upload_id));
                } else if (
                    item.status === "uploading" &&
                    now - (item.updated_at || item.created_at || now) > STALE_UPLOADING_MS
                ) {
                    staleUploadIds.push(item.client_upload_id);
                    item.status = "pending";
                    item.attempts = (item.attempts || 0) + 1;
                    if (item.attempts >= MAX_AUTO_ATTEMPTS) {
                        item.status = "error";
                        item.error_message = getI18n(
                            "stale-error",
                            "La subida se interrumpió. Reintenta o quita la foto de la cola."
                        );
                    }
                    ops.push(putItem(item));
                }
            });
            if (staleUploadIds.length && activeUploadClientId && staleUploadIds.indexOf(activeUploadClientId) !== -1) {
                if (activeUploadAbortController) {
                    try {
                        activeUploadAbortController.abort();
                    } catch (abortErr) {
                        /* ignore */
                    }
                    activeUploadAbortController = null;
                }
                activeUploadClientId = null;
                isProcessingQueue = false;
            }
            return Promise.all(ops);
        });
    }

    function decodeImageElement(file) {
        return new Promise(function (resolve, reject) {
            if (typeof window.createImageBitmap === "function") {
                window
                    .createImageBitmap(file, { imageOrientation: "from-image" })
                    .then(function (bitmap) {
                        resolve({ source: bitmap, width: bitmap.width, height: bitmap.height, isBitmap: true });
                    })
                    .catch(function () {
                        loadViaImgTag(file, resolve, reject);
                    });
            } else {
                loadViaImgTag(file, resolve, reject);
            }
        });
    }

    function loadViaImgTag(file, resolve, reject) {
        var url = URL.createObjectURL(file);
        var img = new Image();
        img.onload = function () {
            URL.revokeObjectURL(url);
            resolve({ source: img, width: img.naturalWidth || img.width, height: img.naturalHeight || img.height, isBitmap: false });
        };
        img.onerror = function () {
            URL.revokeObjectURL(url);
            reject(new Error("No se pudo decodificar la imagen en el navegador"));
        };
        img.src = url;
    }

    function normalizeJpegName(originalName) {
        var base = String(originalName || "foto").replace(/\.[^/.]+$/, "");
        return base + ".jpg";
    }

    function compressImageForUpload(file) {
        return decodeImageElement(file)
            .then(function (decoded) {
                var width = decoded.width;
                var height = decoded.height;
                if (width > MAX_DIMENSION || height > MAX_DIMENSION) {
                    if (width >= height) {
                        height = Math.round((height * MAX_DIMENSION) / width);
                        width = MAX_DIMENSION;
                    } else {
                        width = Math.round((width * MAX_DIMENSION) / height);
                        height = MAX_DIMENSION;
                    }
                }

                var canvas = document.createElement("canvas");
                canvas.width = width;
                canvas.height = height;
                var ctx = canvas.getContext("2d");
                ctx.fillStyle = "#FFFFFF";
                ctx.fillRect(0, 0, width, height);
                ctx.drawImage(decoded.source, 0, 0, width, height);

                var thumbCanvas = document.createElement("canvas");
                var thumbSize = 96;
                var tw = width >= height ? thumbSize : Math.max(1, Math.round((width * thumbSize) / height));
                var th = height > width ? thumbSize : Math.max(1, Math.round((height * thumbSize) / width));
                thumbCanvas.width = tw;
                thumbCanvas.height = th;
                var tctx = thumbCanvas.getContext("2d");
                tctx.drawImage(canvas, 0, 0, tw, th);
                var previewDataUrl = "";
                try {
                    previewDataUrl = thumbCanvas.toDataURL("image/jpeg", 0.65);
                } catch (err) {
                    previewDataUrl = "";
                }

                if (decoded.isBitmap && typeof decoded.source.close === "function") {
                    decoded.source.close();
                }

                return new Promise(function (resolve) {
                    canvas.toBlob(
                        function (blob) {
                            if (!blob) {
                                resolve({
                                    blob: file,
                                    fileName: file.name || "foto.jpg",
                                    previewDataUrl: previewDataUrl
                                });
                                return;
                            }
                            resolve({
                                blob: blob,
                                fileName: normalizeJpegName(file.name),
                                previewDataUrl: previewDataUrl
                            });
                        },
                        "image/jpeg",
                        JPEG_QUALITY
                    );
                });
            })
            .catch(function () {
                // Fallback (p. ej. HEIC en un navegador que no lo decodifica en canvas):
                // se envía el fichero original para que Pillow/pillow-heif lo convierta en servidor.
                return {
                    blob: file,
                    fileName: file.name || "foto.heic",
                    previewDataUrl: ""
                };
            });
    }

    function registerBackgroundSync() {
        if (!("serviceWorker" in navigator)) {
            return;
        }
        navigator.serviceWorker.ready
            .then(function (registration) {
                if (registration && "sync" in registration) {
                    return registration.sync.register(SYNC_TAG);
                }
            })
            .catch(function () {});
    }

    function renderWidget() {
        var widget = getWidget();
        if (!widget) {
            return Promise.resolve();
        }
        return getAllTenantItems().then(function (items) {
            if (!items.length) {
                widget.classList.add("hidden");
                return;
            }
            widget.classList.remove("hidden");

            var total = items.length;
            var uploadedCount = 0;
            var pendingCount = 0;
            var uploadingCount = 0;
            var errorCount = 0;

            items.forEach(function (item) {
                if (item.status === "uploaded") {
                    uploadedCount += 1;
                } else if (item.status === "uploading") {
                    uploadingCount += 1;
                } else if (item.status === "error") {
                    errorCount += 1;
                } else {
                    pendingCount += 1;
                }
            });

            var titleEl = document.getElementById("upload-queue-title");
            var subtitleEl = document.getElementById("upload-queue-subtitle");
            var spinnerEl = document.getElementById("upload-queue-spinner");
            var retryAllBtn = document.getElementById("upload-queue-retry-all-btn");
            var closeBtn = document.getElementById("upload-queue-close-btn");
            var progressEl = document.getElementById("upload-queue-progress");
            var bodyEl = document.getElementById("upload-queue-body");
            var chevronEl = document.getElementById("upload-queue-chevron");

            var percent = total > 0 ? Math.round((uploadedCount / total) * 100) : 0;
            if (progressEl) {
                progressEl.value = percent;
            }

            if (subtitleEl) {
                subtitleEl.textContent = uploadedCount + " / " + total;
            }

            var isOnline = navigator.onLine !== false;
            if (uploadingCount > 0 || (pendingCount > 0 && isOnline)) {
                if (titleEl) {
                    titleEl.textContent = getI18n("uploading", "Subiendo fotos…");
                }
                if (spinnerEl) {
                    spinnerEl.className = "inline-block w-2.5 h-2.5 rounded-full bg-accent animate-pulse flex-shrink-0";
                }
            } else if (pendingCount > 0 && !isOnline) {
                if (titleEl) {
                    titleEl.textContent = getI18n("offline", "Sin cobertura — en cola para reanudar automáticamente");
                }
                if (spinnerEl) {
                    spinnerEl.className = "inline-block w-2.5 h-2.5 rounded-full bg-yellow-500 flex-shrink-0";
                }
            } else if (errorCount > 0) {
                if (titleEl) {
                    titleEl.textContent = getI18n("errors", "Algunas fotos no se pudieron subir");
                }
                if (spinnerEl) {
                    spinnerEl.className = "inline-block w-2.5 h-2.5 rounded-full bg-red-500 flex-shrink-0";
                }
            } else {
                if (titleEl) {
                    titleEl.textContent = getI18n("completed", "Subida completada");
                }
                if (spinnerEl) {
                    spinnerEl.className = "inline-block w-2.5 h-2.5 rounded-full bg-green-500 flex-shrink-0";
                }
            }

            if (retryAllBtn) {
                if (errorCount > 0) {
                    retryAllBtn.classList.remove("hidden");
                } else {
                    retryAllBtn.classList.add("hidden");
                }
            }

            if (closeBtn) {
                if (pendingCount === 0 && uploadingCount === 0) {
                    closeBtn.classList.remove("hidden");
                } else {
                    closeBtn.classList.add("hidden");
                }
            }

            if (bodyEl) {
                if (isPanelCollapsed) {
                    bodyEl.classList.add("hidden");
                } else {
                    bodyEl.classList.remove("hidden");
                }
                if (chevronEl) {
                    chevronEl.className = isPanelCollapsed
                        ? "fas fa-chevron-up text-xs"
                        : "fas fa-chevron-down text-xs";
                }

                var rowsHtml = items.map(function (item) {
                    var statusLabel = getI18n("status-pending", "Pendiente");
                    var badgeClass = "bg-tint text-muted";
                    if (item.status === "uploading") {
                        statusLabel = getI18n("status-uploading", "Subiendo…");
                        badgeClass = "bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-200";
                    } else if (item.status === "uploaded") {
                        statusLabel = getI18n("status-uploaded", "Subida");
                        badgeClass = "bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-200";
                    } else if (item.status === "error") {
                        statusLabel = getI18n("status-error", "Error");
                        badgeClass = "bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-200";
                    }

                    var thumbHtml = item.preview_data_url
                        ? '<img src="' + escapeHtml(item.preview_data_url) + '" alt="" class="w-9 h-9 rounded-lg object-cover flex-shrink-0 bg-tint">'
                        : '<div class="w-9 h-9 rounded-lg bg-tint flex items-center justify-center flex-shrink-0 text-muted"><i class="fas fa-image text-xs"></i></div>';

                    var displayTitle = (item.metadata && item.metadata.title) || item.file_name || "Foto";
                    var errHtml = item.error_message
                        ? '<p class="text-xs text-red-600 dark:text-red-400 truncate mt-0.5">' + escapeHtml(item.error_message) + "</p>"
                        : "";

                    var actionsHtml = "";
                    var argJson = escapeHtml(JSON.stringify([item.client_upload_id]));
                    if (item.status === "error") {
                        actionsHtml =
                            '<button type="button" data-call="retryUploadItem" data-call-args="' + argJson + '" class="text-xs font-medium text-brand-text hover:underline mr-2">' +
                            escapeHtml(getI18n("retry", "Reintentar")) +
                            "</button>" +
                            '<button type="button" data-call="removeUploadItem" data-call-args="' + argJson + '" class="text-xs text-muted hover:text-red-600">' +
                            escapeHtml(getI18n("remove", "Quitar")) +
                            "</button>";
                    } else if (item.status === "pending") {
                        actionsHtml =
                            '<button type="button" data-call="removeUploadItem" data-call-args="' + argJson + '" class="text-xs text-muted hover:text-red-600">' +
                            escapeHtml(getI18n("remove", "Quitar")) +
                            "</button>";
                    }

                    return (
                        '<div class="py-2 flex items-center gap-2.5">' +
                        thumbHtml +
                        '<div class="min-w-0 flex-1">' +
                        '<div class="flex items-center justify-between gap-2">' +
                        '<p class="text-xs font-medium text-ink truncate">' + escapeHtml(displayTitle) + "</p>" +
                        '<span class="text-[11px] px-2 py-0.5 rounded-full font-medium flex-shrink-0 ' + badgeClass + '">' +
                        escapeHtml(statusLabel) +
                        "</span>" +
                        "</div>" +
                        errHtml +
                        (actionsHtml ? '<div class="mt-1">' + actionsHtml + "</div>" : "") +
                        "</div>" +
                        "</div>"
                    );
                });

                bodyEl.innerHTML = rowsHtml.join("");
            }

            if (pendingCount === 0 && uploadingCount === 0 && errorCount === 0 && uploadedCount > 0) {
                setTimeout(function () {
                    getAllTenantItems().then(function (current) {
                        var stillAllDone =
                            current.length > 0 &&
                            current.every(function (i) {
                                return i.status === "uploaded";
                            });
                        if (stillAllDone) {
                            Promise.all(
                                current.map(function (i) {
                                    return deleteItem(i.client_upload_id);
                                })
                            ).then(renderWidget);
                        }
                    });
                }, 6000);
            }
        });
    }

    function sendSingleItem(item) {
        return materializeUploadBlob(item).then(function (uploadBlob) {
            if (!uploadBlob || !uploadBlob.size) {
                return {
                    ok: false,
                    status: 0,
                    data: {
                        error: getI18n("blob-read-error", window.UploadQueueBlob.BLOB_READ_ERROR)
                    },
                    blobMissing: true
                };
            }

            var formData = new FormData();
            formData.append("client_upload_id", item.client_upload_id);
            formData.append("batch_id", item.batch_id || item.client_upload_id);
            formData.append("image", uploadBlob, item.file_name || "foto.jpg");
            return postUploadForm(item, formData);
        });
    }

    function postUploadForm(item, formData) {

        var meta = item.metadata || {};
        if (meta.title) formData.append("title", meta.title);
        if (meta.description) formData.append("description", meta.description);
        if (meta.image_type) formData.append("image_type", meta.image_type);
        if (meta.match) formData.append("match", meta.match);
        if (meta.set_number) formData.append("set_number", meta.set_number);
        if (meta.season) formData.append("season", meta.season);
        if (meta.tags) formData.append("tags", meta.tags);
        if (meta.shared_title) formData.append("shared_title", meta.shared_title);
        if (meta.create_album) formData.append("create_album", "true");
        if (meta.album_group_id) formData.append("album_group_id", meta.album_group_id);
        if (meta.album_name) formData.append("album_name", meta.album_name);
        if (Array.isArray(meta.categories)) {
            meta.categories.forEach(function (catId) {
                formData.append("categories", catId);
            });
        }

        var csrfToken =
            (typeof window.getCsrfToken === "function" && window.getCsrfToken()) ||
            item.csrf_token ||
            "";

        var controller = typeof AbortController !== "undefined" ? new AbortController() : null;
        activeUploadAbortController = controller;
        var timer = null;
        if (controller) {
            timer = setTimeout(function () {
                controller.abort();
            }, UPLOAD_TIMEOUT_MS);
        }

        return fetch(item.endpoint || getUploadEndpoint(), {
            method: "POST",
            headers: {
                "X-CSRFToken": csrfToken,
                "X-Requested-With": "XMLHttpRequest"
            },
            credentials: "same-origin",
            body: formData,
            signal: controller ? controller.signal : undefined
        })
            .then(function (response) {
                return response
                    .json()
                    .catch(function () {
                        return {};
                    })
                    .then(function (data) {
                        return { ok: response.ok, status: response.status, data: data };
                    });
            })
            .finally(function () {
                if (timer) {
                    clearTimeout(timer);
                }
                if (activeUploadAbortController === controller) {
                    activeUploadAbortController = null;
                }
                if (activeUploadClientId === item.client_upload_id) {
                    activeUploadClientId = null;
                }
            });
    }

    function applyUploadResultIfStillActive(clientUploadId, result, nextStep, handleRetryableFailure) {
        return getItemById(clientUploadId).then(function (stored) {
            if (!stored || stored.status !== "uploading") {
                return nextStep();
            }

            var status = result.status;
            var data = result.data || {};
            if (result.ok && data && data.ok) {
                stored.status = "uploaded";
                stored.error_message = "";
                return putItem(stored).then(renderWidget).then(nextStep);
            }

            var isRetryableHttp =
                !result.blobMissing &&
                (status === 408 ||
                    status === 429 ||
                    status === 502 ||
                    status === 503 ||
                    status === 504 ||
                    status >= 500 ||
                    status === 0);
            if (!isRetryableHttp) {
                stored.status = "error";
                stored.error_message = (data && data.error) || "Error (" + status + ")";
                return putItem(stored).then(renderWidget).then(nextStep);
            }

            return handleRetryableFailure(
                stored,
                (data && data.error) || getI18n("network-error", "Corte de conexión. Se reintentará al recuperar señal.")
            );
        });
    }

    function sleep(ms) {
        return new Promise(function (resolve) {
            setTimeout(resolve, ms);
        });
    }

    function processQueue() {
        if (isProcessingQueue) {
            return Promise.resolve();
        }
        if (navigator.onLine === false) {
            renderWidget();
            return Promise.resolve();
        }
        isProcessingQueue = true;

        function nextStep() {
            if (navigator.onLine === false) {
                isProcessingQueue = false;
                renderWidget();
                return Promise.resolve();
            }
            return getAllTenantItems().then(function (items) {
                var nextItem = items.find(function (i) {
                    return i.status === "pending";
                });
                if (!nextItem) {
                    isProcessingQueue = false;
                    renderWidget();
                    return Promise.resolve();
                }

                nextItem.status = "uploading";
                nextItem.error_message = "";
                activeUploadClientId = nextItem.client_upload_id;
                return putItem(nextItem)
                    .then(renderWidget)
                    .then(function () {
                        return sendSingleItem(nextItem);
                    })
                    .then(function (result) {
                        return applyUploadResultIfStillActive(
                            nextItem.client_upload_id,
                            result,
                            nextStep,
                            handleRetryableFailure
                        );
                    })
                    .catch(function () {
                        return applyUploadResultIfStillActive(
                            nextItem.client_upload_id,
                            {
                                ok: false,
                                status: 0,
                                data: {},
                                blobMissing: false
                            },
                            nextStep,
                            handleRetryableFailure
                        );
                    });
            });
        }

        function handleRetryableFailure(item, message) {
            if (navigator.onLine === false) {
                item.status = "pending";
                item.error_message = message;
                registerBackgroundSync();
                return putItem(item).then(function () {
                    isProcessingQueue = false;
                    return renderWidget();
                });
            }

            item.attempts = (item.attempts || 0) + 1;
            if (item.attempts < MAX_AUTO_ATTEMPTS) {
                item.status = "pending";
                item.error_message = message;
                var delay = BACKOFF_DELAYS_MS[Math.min(item.attempts - 1, BACKOFF_DELAYS_MS.length - 1)];
                return putItem(item)
                    .then(renderWidget)
                    .then(function () {
                        return sleep(delay);
                    })
                    .then(nextStep);
            }

            item.status = "error";
            item.error_message = message;
            registerBackgroundSync();
            return putItem(item).then(renderWidget).then(nextStep);
        }

        return nextStep().catch(function () {
            isProcessingQueue = false;
        });
    }

    function enqueueFilesWithMetadata(files, metadataList, batchId) {
        var csrfToken = typeof window.getCsrfToken === "function" ? window.getCsrfToken() : "";
        var endpoint = getUploadEndpoint();
        var origin = window.location.origin;
        var resolvedBatchId = batchId || generateUuid();

        var chain = Promise.resolve();
        files.forEach(function (file, idx) {
            chain = chain.then(function () {
                return compressImageForUpload(file).then(function (compressed) {
                    var itemMeta = metadataList[idx] || metadataList[0] || {};
                    var tooLarge = compressed.blob && compressed.blob.size > MAX_COMPRESSED_BYTES;
                    var item = {
                        client_upload_id: generateUuid(),
                        batch_id: resolvedBatchId,
                        tenant_origin: origin,
                        endpoint: endpoint,
                        csrf_token: csrfToken,
                        file_name: compressed.fileName,
                        preview_data_url: compressed.previewDataUrl,
                        metadata: itemMeta,
                        status: tooLarge ? "error" : "pending",
                        attempts: 0,
                        error_message: tooLarge
                            ? getI18n("size-error", "El archivo comprimido supera el límite de 10MB.")
                            : "",
                        created_at: Date.now() + idx,
                        updated_at: Date.now() + idx
                    };
                    if (tooLarge || !compressed.blob) {
                        return putItem(item);
                    }
                    return compressed.blob.arrayBuffer().then(function (buf) {
                        item.file_bytes = buf;
                        item.file_mime = compressed.blob.type || "image/jpeg";
                        return putItem(item);
                    });
                });
            });
        });

        return chain.then(function () {
            isPanelCollapsed = false;
            registerBackgroundSync();
            if (typeof window.showToast === "function") {
                window.showToast("info", getI18n("queued-toast", "Fotos añadidas a la cola de subida."));
            }
            return renderWidget().then(processQueue);
        });
    }

    function collectSelectedCategories(form) {
        var checked = form.querySelectorAll('input[name="categories"]:checked');
        var ids = [];
        checked.forEach(function (cb) {
            if (!cb.disabled && cb.value) {
                ids.push(cb.value);
            }
        });
        return ids;
    }

    function enqueueFromSingleForm(form, file) {
        var meta = {
            title: (form.querySelector('[name="title"]') || {}).value || "",
            description: (form.querySelector('[name="description"]') || {}).value || "",
            image_type: (form.querySelector('[name="image_type"]') || {}).value || "other",
            match: (form.querySelector('[name="match"]') || {}).value || "",
            set_number: (form.querySelector('[name="set_number"]') || {}).value || "",
            season: (form.querySelector('[name="season"]') || {}).value || "",
            tags: (form.querySelector('[name="tags"]') || {}).value || "",
            categories: collectSelectedCategories(form)
        };
        return enqueueFilesWithMetadata([file], [meta], generateUuid());
    }

    function enqueueFromBulkForm(form, files) {
        var batchId = generateUuid();
        var matchVal = (form.querySelector('[name="match"]') || {}).value || "";
        var existingAlbumInput = form.querySelector('[name="existing_album_id"]');
        var createAlbumCheckbox = form.querySelector('[name="create_album"]');
        var albumNameInput = form.querySelector('[name="album_name"]');

        var isCreateAlbum = Boolean(!matchVal && !existingAlbumInput && createAlbumCheckbox && createAlbumCheckbox.checked);
        var albumGroupId = "";
        var albumName = "";
        if (existingAlbumInput && existingAlbumInput.value) {
            albumGroupId = existingAlbumInput.value;
        } else if (isCreateAlbum) {
            albumGroupId = generateUuid();
            albumName = (albumNameInput && albumNameInput.value.trim()) || "";
        }

        var sharedCategories = collectSelectedCategories(form);
        var sharedType = (form.querySelector('[name="image_type"]') || {}).value || "other";
        var sharedSeason = (form.querySelector('[name="season"]') || {}).value || "";
        var sharedSetNumber = (form.querySelector('[name="set_number"]') || {}).value || "";
        var sharedTags = (form.querySelector('[name="tags"]') || {}).value || "";
        var sharedTitle = (form.querySelector('[name="shared_title"]') || {}).value || "";

        var metadataList = files.map(function (_file, index) {
            var titleInput = form.querySelector('[name="title_' + index + '"]');
            var descInput = form.querySelector('[name="description_' + index + '"]');
            return {
                title: (titleInput && titleInput.value) || "",
                description: (descInput && descInput.value) || "",
                image_type: sharedType,
                match: matchVal,
                set_number: sharedSetNumber,
                season: sharedSeason,
                tags: sharedTags,
                shared_title: sharedTitle,
                categories: sharedCategories,
                create_album: isCreateAlbum,
                album_group_id: albumGroupId,
                album_name: albumName
            };
        });

        return enqueueFilesWithMetadata(files, metadataList, batchId);
    }

    window.toggleUploadQueuePanel = function () {
        isPanelCollapsed = !isPanelCollapsed;
        renderWidget();
    };

    window.retryFailedUploads = function () {
        getAllTenantItems()
            .then(function (items) {
                var failed = items.filter(function (i) {
                    return i.status === "error";
                });
                return Promise.all(
                    failed.map(function (item) {
                        item.status = "pending";
                        item.attempts = 0;
                        item.error_message = "";
                        return putItem(item);
                    })
                );
            })
            .then(renderWidget)
            .then(processQueue);
    };

    window.retryUploadItem = function (clientUploadId) {
        getAllTenantItems()
            .then(function (items) {
                var target = items.find(function (i) {
                    return i.client_upload_id === clientUploadId;
                });
                if (!target) {
                    return;
                }
                target.status = "pending";
                target.attempts = 0;
                target.error_message = "";
                return putItem(target);
            })
            .then(renderWidget)
            .then(processQueue);
    };

    window.removeUploadItem = function (clientUploadId) {
        deleteItem(clientUploadId).then(renderWidget);
    };

    window.closeUploadQueueWidget = function () {
        getAllTenantItems()
            .then(function (items) {
                var removable = items.filter(function (i) {
                    return i.status === "uploaded" || i.status === "error";
                });
                return Promise.all(
                    removable.map(function (i) {
                        return deleteItem(i.client_upload_id);
                    })
                );
            })
            .then(function () {
                var widget = getWidget();
                if (widget) {
                    widget.classList.add("hidden");
                }
            });
    };

    window.UploadQueue = {
        compressImageForUpload: compressImageForUpload,
        enqueueFilesWithMetadata: enqueueFilesWithMetadata,
        enqueueFromSingleForm: enqueueFromSingleForm,
        enqueueFromBulkForm: enqueueFromBulkForm,
        processQueue: processQueue,
        renderWidget: renderWidget
    };

    document.addEventListener("DOMContentLoaded", function () {
        if (!getWidget()) {
            return;
        }
        cleanupStaleItems()
            .then(renderWidget)
            .then(processQueue);
    });

    window.addEventListener("online", function () {
        if (!getWidget()) {
            return;
        }
        renderWidget().then(processQueue);
    });

    document.addEventListener("visibilitychange", function () {
        if (document.visibilityState === "visible" && getWidget()) {
            cleanupStaleItems()
                .then(renderWidget)
                .then(processQueue);
        }
    });

    if ("serviceWorker" in navigator) {
        navigator.serviceWorker.addEventListener("message", function (event) {
            var data = (event && event.data) || {};
            if (data.type === "PROCESS_UPLOAD_QUEUE") {
                processQueue();
            } else if (data.type === "UPLOAD_QUEUE_UPDATED") {
                renderWidget();
            }
        });
    }
})();
