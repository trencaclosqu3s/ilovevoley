/**
 * Sistema de Lightbox Reutilizable para VideosVoley
 * Maneja la visualización ampliada de imágenes en toda la aplicación
 */

class ImageLightbox {
    constructor(options = {}) {
        this.options = {
            showNavigation: options.showNavigation || false,
            showActions: options.showActions || false,
            onApprove: options.onApprove || null,
            onReject: options.onReject || null,
            ...options
        };
        
        this.currentImages = [];
        this.currentIndex = 0;
        this.isInitialized = false;
        
        this.init();
    }
    
    init() {
        if (this.isInitialized) return;
        
        this.createLightboxHTML();
        this.attachEventListeners();
        this.isInitialized = true;
    }
    
    createLightboxHTML() {
        // Crear el HTML del lightbox si no existe
        if (document.getElementById('image-lightbox')) {
            return; // Ya existe
        }
        
        const lightboxHTML = `
            <div id="image-lightbox" class="fixed inset-0 bg-black bg-opacity-75 hidden z-50 flex items-center justify-center p-4">
                <div class="lightbox-container relative w-full h-full flex items-center justify-center">
                    <!-- Botón cerrar -->
                    <button id="lightbox-close" class="absolute top-4 right-4 bg-white hover:bg-gray-100 text-gray-900 rounded-full w-12 h-12 flex items-center justify-center z-20 transition-all duration-200 hover:scale-110 shadow-lg font-bold text-2xl leading-none">
                        ×
                    </button>
                    
                    <!-- Navegación izquierda -->
                    <button id="lightbox-prev" class="absolute left-4 top-1/2 transform -translate-y-1/2 bg-white bg-opacity-80 hover:bg-opacity-100 text-gray-900 rounded-full w-12 h-12 flex items-center justify-center z-20 transition-all duration-200 hover:scale-110 shadow-lg hidden">
                        ←
                    </button>
                    
                    <!-- Navegación derecha -->
                    <button id="lightbox-next" class="absolute right-4 top-1/2 transform -translate-y-1/2 bg-white bg-opacity-80 hover:bg-opacity-100 text-gray-900 rounded-full w-12 h-12 flex items-center justify-center z-20 transition-all duration-200 hover:scale-110 shadow-lg hidden">
                        →
                    </button>
                    
                    <!-- Imagen principal -->
                    <img id="lightbox-image" src="" alt="" class="max-w-full max-h-[90vh] object-contain">
                    
                    <!-- Información y acciones -->
                    <div id="lightbox-info" class="absolute bottom-4 left-4 right-4 text-white bg-black bg-opacity-70 rounded-lg p-4 max-w-4xl mx-auto">
                        <div class="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
                            <!-- Info básica -->
                            <div class="flex-1">
                                <h3 id="lightbox-title" class="font-semibold text-lg mb-2"></h3>
                                <div id="lightbox-description" class="text-sm text-gray-300 mb-2"></div>
                                <div class="flex flex-wrap gap-2 text-sm">
                                    <span id="lightbox-user" class="text-blue-300"></span>
                                    <span id="lightbox-date" class="text-gray-400"></span>
                                </div>
                            </div>
                            
                            <!-- Acciones de moderación (solo si está habilitado) -->
                            <div id="lightbox-actions" class="flex gap-3 hidden">
                                <button id="lightbox-approve" class="bg-green-500 hover:bg-green-600 text-white px-4 py-2 rounded-lg font-semibold transition-colors">
                                    ✅ Aprobar
                                </button>
                                <button id="lightbox-reject" class="bg-red-500 hover:bg-red-600 text-white px-4 py-2 rounded-lg font-semibold transition-colors">
                                    ❌ Rechazar
                                </button>
                            </div>
                            
                            <!-- Enlaces adicionales -->
                            <div class="flex gap-3">
                                <a id="lightbox-detail-link" href="#" class="text-blue-300 hover:text-blue-100 underline">Ver detalles</a>
                            </div>
                        </div>
                        
                        <!-- Información adicional (Vision API, etc.) -->
                        <div id="lightbox-extra-info" class="mt-4 hidden">
                            <div id="lightbox-vision-info" class="bg-red-900 bg-opacity-50 rounded p-3 mb-3 hidden">
                                <div class="font-medium text-red-200 mb-2">⚠️ Análisis automático:</div>
                                <div id="lightbox-vision-reasons" class="text-sm text-red-300"></div>
                            </div>
                            
                            <div id="lightbox-text-detected" class="bg-gray-800 bg-opacity-50 rounded p-3 hidden">
                                <div class="font-medium text-gray-200 mb-2">📝 Texto detectado:</div>
                                <div class="text-sm text-gray-300 max-h-20 overflow-y-auto"></div>
                            </div>
                        </div>
                        
                        <!-- Contador de navegación -->
                        <div id="lightbox-counter" class="text-center text-sm text-gray-400 mt-2 hidden">
                            <span id="lightbox-current">1</span> de <span id="lightbox-total">1</span>
                        </div>
                    </div>
                </div>
            </div>
        `;
        
        document.body.insertAdjacentHTML('beforeend', lightboxHTML);
    }
    
    attachEventListeners() {
        // Botón cerrar
        document.getElementById('lightbox-close')?.addEventListener('click', () => this.close());
        
        // Navegación
        document.getElementById('lightbox-prev')?.addEventListener('click', () => this.prevImage());
        document.getElementById('lightbox-next')?.addEventListener('click', () => this.nextImage());
        
        // Cerrar con ESC
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && this.isOpen()) {
                this.close();
            }
            if (e.key === 'ArrowLeft' && this.isOpen() && this.options.showNavigation) {
                this.prevImage();
            }
            if (e.key === 'ArrowRight' && this.isOpen() && this.options.showNavigation) {
                this.nextImage();
            }
        });
        
        // Cerrar clickeando fuera
        document.getElementById('image-lightbox')?.addEventListener('click', (e) => {
            if (e.target.id === 'image-lightbox' || e.target.classList.contains('lightbox-container')) {
                this.close();
            }
        });
        
        // Acciones de moderación
        document.getElementById('lightbox-approve')?.addEventListener('click', () => {
            if (this.options.onApprove && this.currentImages[this.currentIndex]) {
                this.options.onApprove(this.currentImages[this.currentIndex]);
            }
        });
        
        document.getElementById('lightbox-reject')?.addEventListener('click', () => {
            if (this.options.onReject && this.currentImages[this.currentIndex]) {
                this.options.onReject(this.currentImages[this.currentIndex]);
            }
        });
    }
    
    open(imageData, images = null) {
        if (Array.isArray(images)) {
            this.currentImages = images;
            this.currentIndex = images.findIndex(img => img.id === imageData.id) || 0;
        } else {
            this.currentImages = [imageData];
            this.currentIndex = 0;
        }
        
        this.updateDisplay();
        document.getElementById('image-lightbox').classList.remove('hidden');
        document.body.style.overflow = 'hidden';
    }
    
    close() {
        document.getElementById('image-lightbox').classList.add('hidden');
        document.body.style.overflow = 'auto';
    }
    
    isOpen() {
        return !document.getElementById('image-lightbox').classList.contains('hidden');
    }
    
    prevImage() {
        if (this.currentIndex > 0) {
            this.currentIndex--;
            this.updateDisplay();
        }
    }
    
    nextImage() {
        if (this.currentIndex < this.currentImages.length - 1) {
            this.currentIndex++;
            this.updateDisplay();
        }
    }
    
    updateDisplay() {
        const imageData = this.currentImages[this.currentIndex];
        if (!imageData) return;
        
        // Actualizar imagen
        document.getElementById('lightbox-image').src = imageData.url;
        document.getElementById('lightbox-image').alt = imageData.title;
        
        // Actualizar información básica
        document.getElementById('lightbox-title').textContent = imageData.title || '';
        document.getElementById('lightbox-description').textContent = imageData.description || '';
        document.getElementById('lightbox-user').textContent = imageData.user ? `👤 ${imageData.user}` : '';
        document.getElementById('lightbox-date').textContent = imageData.date || '';
        document.getElementById('lightbox-detail-link').href = imageData.detailUrl || '#';
        
        // Mostrar/ocultar navegación
        const prevBtn = document.getElementById('lightbox-prev');
        const nextBtn = document.getElementById('lightbox-next');
        const counter = document.getElementById('lightbox-counter');
        
        if (this.options.showNavigation && this.currentImages.length > 1) {
            prevBtn.classList.toggle('hidden', this.currentIndex === 0);
            nextBtn.classList.toggle('hidden', this.currentIndex === this.currentImages.length - 1);
            counter.classList.remove('hidden');
            document.getElementById('lightbox-current').textContent = this.currentIndex + 1;
            document.getElementById('lightbox-total').textContent = this.currentImages.length;
        } else {
            prevBtn.classList.add('hidden');
            nextBtn.classList.add('hidden');
            counter.classList.add('hidden');
        }
        
        // Mostrar/ocultar acciones de moderación
        const actionsDiv = document.getElementById('lightbox-actions');
        if (this.options.showActions) {
            actionsDiv.classList.remove('hidden');
        } else {
            actionsDiv.classList.add('hidden');
        }
        
        // Información adicional (Vision API, etc.)
        const extraInfo = document.getElementById('lightbox-extra-info');
        const visionInfo = document.getElementById('lightbox-vision-info');
        const textDetected = document.getElementById('lightbox-text-detected');
        
        // Limpiar información anterior
        extraInfo.classList.add('hidden');
        visionInfo.classList.add('hidden');
        textDetected.classList.add('hidden');
        
        if (imageData.visionData) {
            extraInfo.classList.remove('hidden');
            
            // Mostrar razones de Vision API
            if (imageData.visionData.reasons && imageData.visionData.reasons.length > 0) {
                visionInfo.classList.remove('hidden');
                const reasonsHTML = imageData.visionData.reasons.map(reason => {
                    if (reason.includes('violence')) return '🚨 Posible contenido violento';
                    if (reason.includes('racy')) return '🔞 Contenido sugerente detectado';
                    if (reason.includes('spoof')) return '🎭 Posible contenido falso/spam';
                    if (reason.includes('medical')) return '🏥 Contenido médico detectado';
                    return `⚠️ ${reason}`;
                }).join('<br>');
                document.getElementById('lightbox-vision-reasons').innerHTML = reasonsHTML;
            }
            
            // Mostrar texto detectado
            if (imageData.visionData.text) {
                textDetected.classList.remove('hidden');
                textDetected.querySelector('.text-gray-300').textContent = imageData.visionData.text;
            }
        }
    }
}

// Instancia global del lightbox
let globalLightbox = null;

// Función de conveniencia para abrir lightbox (compatibilidad con código existente)
function openLightbox(imageUrl, title, imageId, description = '', user = '', date = '') {
    if (!globalLightbox) {
        globalLightbox = new ImageLightbox();
    }
    
    const imageData = {
        id: imageId,
        url: imageUrl,
        title: title,
        description: description,
        user: user,
        date: date,
        detailUrl: `/videos/imagenes/${imageId}/`
    };
    
    globalLightbox.open(imageData);
}

// Función para cerrar lightbox (compatibilidad)
function closeLightbox() {
    if (globalLightbox) {
        globalLightbox.close();
    }
}

// Función para inicializar lightbox con opciones específicas
function initImageLightbox(options = {}) {
    return new ImageLightbox(options);
}

// Exportar para uso en otros archivos
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { ImageLightbox, initImageLightbox, openLightbox, closeLightbox };
}