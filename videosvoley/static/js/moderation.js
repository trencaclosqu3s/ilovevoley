/**
 * Sistema de Moderación para VideosVoley
 * Maneja notificaciones, contadores y acciones de moderación para superusers
 */

class ModerationSystem {
    constructor() {
        this.updateInterval = null;
        this.isInitialized = false;
        this.updateIntervalTime = 30000; // 30 segundos
        
        // URLs de API (se configuran dinámicamente)
        this.apiUrls = {
            counts: '/videos/api/moderation/counts/',
            approveUser: '/videos/api/users/{id}/approve/',
            rejectUser: '/videos/api/users/{id}/reject/',
            moderateImage: '/videos/api/images/{id}/moderate/'
        };
    }
    
    init() {
        if (this.isInitialized) return;
        
        this.updateModerationCounts();
        this.startAutoUpdate();
        this.attachEventListeners();
        this.isInitialized = true;
        
        console.log('Sistema de moderación inicializado');
    }
    
    startAutoUpdate() {
        // Limpiar interval existente
        if (this.updateInterval) {
            clearInterval(this.updateInterval);
        }
        
        // Configurar auto-actualización
        this.updateInterval = setInterval(() => {
            this.updateModerationCounts();
        }, this.updateIntervalTime);
    }
    
    stopAutoUpdate() {
        if (this.updateInterval) {
            clearInterval(this.updateInterval);
            this.updateInterval = null;
        }
    }
    
    attachEventListeners() {
        // Limpiar interval al cambiar de página
        window.addEventListener('beforeunload', () => {
            this.stopAutoUpdate();
        });
        
        // Pausar actualizaciones cuando la pestaña no está visible
        document.addEventListener('visibilitychange', () => {
            if (document.hidden) {
                this.stopAutoUpdate();
            } else {
                this.startAutoUpdate();
            }
        });
    }
    
    async updateModerationCounts() {
        try {
            const response = await fetch(this.apiUrls.counts);
            
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            
            const data = await response.json();
            
            if (data.success) {
                this.updateCounterUI(data.total_pending);
            }
        } catch (error) {
            console.log('Error actualizando contadores de moderación:', error);
        }
    }
    
    updateCounterUI(count) {
        const counterDesktop = document.getElementById('moderation-counter');
        const counterMobile = document.getElementById('moderation-counter-mobile');
        
        // Actualizar contador desktop
        if (counterDesktop) {
            counterDesktop.textContent = count;
            if (count > 0) {
                counterDesktop.classList.remove('hidden');
            } else {
                counterDesktop.classList.add('hidden');
            }
        }
        
        // Actualizar contador móvil
        if (counterMobile) {
            counterMobile.textContent = count;
            if (count > 0) {
                counterMobile.classList.remove('hidden');
            } else {
                counterMobile.classList.add('hidden');
            }
        }
    }
    
    async approveUser(userId, buttonElement) {
        if (!confirm('¿Estás segura de que quieres aprobar este usuario?')) {
            return;
        }
        
        // Deshabilitar todos los botones del card
        const userCard = buttonElement.closest('.user-card');
        const allButtons = userCard?.querySelectorAll('button') || [buttonElement];
        const originalTexts = new Map();
        
        allButtons.forEach(btn => {
            originalTexts.set(btn, btn.textContent);
            btn.disabled = true;
        });
        
        buttonElement.textContent = 'Aprobando...';
        
        try {
            // Crear FormData para enviar como POST
            const formData = new FormData();
            const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]')?.value;
            if (csrfToken) {
                formData.append('csrfmiddlewaretoken', csrfToken);
            }
            
            const url = this.apiUrls.approveUser.replace('{id}', userId);
            const response = await fetch(url, {
                method: 'POST',
                body: formData
            });
            
            const data = await response.json();
            
            if (data.success) {
                this.showToast('success', data.message);
                
                // Remover el card del usuario con animación
                if (userCard) {
                    userCard.style.opacity = '0.5';
                    userCard.style.transform = 'scale(0.95)';
                    setTimeout(() => {
                        userCard.remove();
                        this.updateModerationCounts();
                    }, 500);
                }
            } else {
                throw new Error(data.error || 'Error al aprobar usuario');
            }
        } catch (error) {
            console.error('Error aprobando usuario:', error);
            this.showToast('error', error.message || 'Error de conexión');
            
            // Restaurar botones
            allButtons.forEach(btn => {
                btn.disabled = false;
                btn.textContent = originalTexts.get(btn);
            });
        }
    }
    
    async rejectUser(userId, buttonElement) {
        if (!confirm('¿Estás segura de que quieres RECHAZAR este usuario?\n\nEsta acción desactivará la cuenta del usuario.')) {
            return;
        }
        
        // Deshabilitar todos los botones del card
        const userCard = buttonElement.closest('.user-card');
        const allButtons = userCard?.querySelectorAll('button') || [buttonElement];
        const originalTexts = new Map();
        
        allButtons.forEach(btn => {
            originalTexts.set(btn, btn.textContent);
            btn.disabled = true;
        });
        
        buttonElement.textContent = 'Rechazando...';
        
        try {
            // Crear FormData para enviar como POST
            const formData = new FormData();
            const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]')?.value;
            if (csrfToken) {
                formData.append('csrfmiddlewaretoken', csrfToken);
            }
            
            const url = this.apiUrls.rejectUser.replace('{id}', userId);
            const response = await fetch(url, {
                method: 'POST',
                body: formData
            });
            
            const data = await response.json();
            
            if (data.success) {
                this.showToast('success', data.message);
                
                // Remover el card del usuario con animación
                if (userCard) {
                    userCard.style.opacity = '0.5';
                    userCard.style.transform = 'scale(0.95)';
                    setTimeout(() => {
                        userCard.remove();
                        this.updateModerationCounts();
                    }, 500);
                }
            } else {
                throw new Error(data.error || 'Error al rechazar usuario');
            }
        } catch (error) {
            console.error('Error rechazando usuario:', error);
            this.showToast('error', error.message || 'Error de conexión');
            
            // Restaurar botones
            allButtons.forEach(btn => {
                btn.disabled = false;
                btn.textContent = originalTexts.get(btn);
            });
        }
    }
    
    async moderateImage(imageId, action, buttonElement) {
        const actionText = action === 'approve' ? 'aprobar' : 'rechazar';
        if (!confirm(`¿Estás segura de que quieres ${actionText} esta imagen?`)) {
            return;
        }
        
        // Deshabilitar todos los botones del card
        const imageCard = buttonElement.closest('.image-card');
        const allButtons = imageCard?.querySelectorAll('button') || [buttonElement];
        const originalTexts = new Map();
        
        allButtons.forEach(btn => {
            originalTexts.set(btn, btn.textContent);
            btn.disabled = true;
        });
        
        buttonElement.textContent = action === 'approve' ? 'Aprobando...' : 'Rechazando...';
        
        try {
            // Crear FormData para enviar como POST
            const formData = new FormData();
            const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]')?.value;
            if (csrfToken) {
                formData.append('csrfmiddlewaretoken', csrfToken);
            }
            formData.append('action', action);
            
            const url = this.apiUrls.moderateImage.replace('{id}', imageId);
            const response = await fetch(url, {
                method: 'POST',
                body: formData
            });
            
            const data = await response.json();
            
            if (data.success) {
                this.showToast('success', data.message);
                
                // Remover el card de la imagen con animación
                if (imageCard) {
                    imageCard.style.opacity = '0.5';
                    imageCard.style.transform = 'scale(0.95)';
                    setTimeout(() => {
                        imageCard.remove();
                        this.updateModerationCounts();
                    }, 500);
                }
            } else {
                throw new Error(data.error || 'Error al moderar imagen');
            }
        } catch (error) {
            console.error('Error moderando imagen:', error);
            this.showToast('error', error.message || 'Error de conexión');
            
            // Restaurar botones
            allButtons.forEach(btn => {
                btn.disabled = false;
                btn.textContent = originalTexts.get(btn);
            });
        }
    }
    
    showToast(type, message) {
        // Usar el sistema de toasts global si está disponible
        if (typeof window.showToast === 'function') {
            window.showToast(type, message);
        } else if (typeof notyf !== 'undefined') {
            // Usar Notyf directamente si está disponible
            if (type === 'success') {
                notyf.success(message);
            } else if (type === 'error') {
                notyf.error(message);
            } else {
                notyf.open({ type: type, message: message });
            }
        } else {
            // Fallback a alert nativo
            alert(`${type.toUpperCase()}: ${message}`);
        }
    }
    
    // Método para configurar URLs personalizadas
    setApiUrls(urls) {
        this.apiUrls = { ...this.apiUrls, ...urls };
    }
    
    // Método para cambiar intervalo de actualización
    setUpdateInterval(milliseconds) {
        this.updateIntervalTime = milliseconds;
        if (this.updateInterval) {
            this.stopAutoUpdate();
            this.startAutoUpdate();
        }
    }
}

// Instancia global del sistema de moderación
let globalModerationSystem = null;

// Función para inicializar el sistema de moderación
function initModerationSystem(options = {}) {
    if (!globalModerationSystem) {
        globalModerationSystem = new ModerationSystem();
        
        // Configurar opciones si se proporcionan
        if (options.apiUrls) {
            globalModerationSystem.setApiUrls(options.apiUrls);
        }
        if (options.updateInterval) {
            globalModerationSystem.setUpdateInterval(options.updateInterval);
        }
    }
    
    globalModerationSystem.init();
    return globalModerationSystem;
}

// Funciones de conveniencia para compatibilidad con código existente
function updateModerationCounts() {
    if (globalModerationSystem) {
        globalModerationSystem.updateModerationCounts();
    }
}

function approveUser(userId, buttonElement) {
    if (globalModerationSystem) {
        globalModerationSystem.approveUser(userId, buttonElement);
    } else {
        console.error('Sistema de moderación no inicializado');
    }
}

function rejectUser(userId, buttonElement) {
    if (globalModerationSystem) {
        globalModerationSystem.rejectUser(userId, buttonElement);
    } else {
        console.error('Sistema de moderación no inicializado');
    }
}

function moderateImage(imageId, action, buttonElement) {
    if (globalModerationSystem) {
        globalModerationSystem.moderateImage(imageId, action, buttonElement);
    } else {
        console.error('Sistema de moderación no inicializado');
    }
}

// Inicialización automática cuando se carga el DOM
document.addEventListener('DOMContentLoaded', function() {
    // Solo inicializar si hay elementos de moderación en la página
    const moderationElements = document.querySelector('#moderation-counter, #moderation-counter-mobile, .user-card, .image-card');
    if (moderationElements) {
        initModerationSystem();
    }
});

// Exportar para uso en otros archivos
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { 
        ModerationSystem, 
        initModerationSystem, 
        updateModerationCounts, 
        approveUser,
        rejectUser, 
        moderateImage 
    };
}