/**
 * Cookie Consent Management
 * Gestiona el banner de consentimiento de cookies y las preferencias del usuario
 */

class CookieConsent {
    constructor() {
        this.cookieName = 'cookie_consent';
        this.cookieExpiry = 365; // días
        this.banner = null;
        this.modal = null;
        
        this.init();
    }
    
    init() {
        // Esperar a que el DOM esté listo
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', () => this.setup());
        } else {
            this.setup();
        }
    }
    
    setup() {
        this.banner = document.getElementById('cookie-banner');
        this.modal = document.getElementById('cookie-info-modal');
        
        if (!this.banner) return;
        
        // Verificar si el usuario ya ha dado su consentimiento
        if (!this.hasConsent()) {
            this.showBanner();
        }
        
        // Configurar event listeners
        this.setupEventListeners();
    }
    
    setupEventListeners() {
        // Botón aceptar
        const acceptBtn = document.getElementById('cookie-accept');
        if (acceptBtn) {
            acceptBtn.addEventListener('click', () => this.acceptCookies());
        }
        
        // Botón rechazar
        const rejectBtn = document.getElementById('cookie-reject');
        if (rejectBtn) {
            rejectBtn.addEventListener('click', () => this.rejectCookies());
        }
        
        // Enlace de más información
        const infoLink = document.getElementById('cookie-info-link');
        if (infoLink) {
            infoLink.addEventListener('click', (e) => {
                e.preventDefault();
                this.showModal();
            });
        }
        
        // Cerrar modal
        const closeModalBtn = document.getElementById('close-cookie-modal');
        const closeModalBtnBottom = document.getElementById('close-cookie-modal-btn');
        
        if (closeModalBtn) {
            closeModalBtn.addEventListener('click', () => this.hideModal());
        }
        
        if (closeModalBtnBottom) {
            closeModalBtnBottom.addEventListener('click', () => this.hideModal());
        }
        
        // Cerrar modal al hacer clic fuera
        if (this.modal) {
            this.modal.addEventListener('click', (e) => {
                if (e.target === this.modal) {
                    this.hideModal();
                }
            });
        }
        
        // Cerrar modal con Escape
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && this.modal && !this.modal.classList.contains('hidden')) {
                this.hideModal();
            }
        });
    }
    
    hasConsent() {
        const consent = this.getCookie(this.cookieName);
        return consent === 'accepted' || consent === 'rejected';
    }
    
    showBanner() {
        if (!this.banner) return;
        
        this.banner.style.display = 'block';
        // Forzar reflow para que la transición funcione
        this.banner.offsetHeight;
        this.banner.classList.remove('translate-y-full');
    }
    
    hideBanner() {
        if (!this.banner) return;
        
        this.banner.classList.add('translate-y-full');
        setTimeout(() => {
            this.banner.style.display = 'none';
        }, 300);
    }
    
    showModal() {
        if (!this.modal) return;
        
        this.modal.classList.remove('hidden');
        // Enfocar el botón de cerrar para accesibilidad
        const closeBtn = document.getElementById('close-cookie-modal');
        if (closeBtn) closeBtn.focus();
    }
    
    hideModal() {
        if (!this.modal) return;
        
        this.modal.classList.add('hidden');
    }
    
    acceptCookies() {
        this.setCookie(this.cookieName, 'accepted', this.cookieExpiry);
        this.hideBanner();
        
        // Mostrar notificación
        if (window.showToast) {
            window.showToast('success', 'Cookies aceptadas. Gracias por tu consentimiento.');
        }
    }
    
    rejectCookies() {
        this.setCookie(this.cookieName, 'rejected', this.cookieExpiry);
        this.hideBanner();
        
        // Mostrar notificación
        if (window.showToast) {
            window.showToast('info', 'Cookies rechazadas. Solo se utilizarán las estrictamente necesarias.');
        }
        
        // Aquí podrías agregar lógica para desactivar cookies no esenciales
        this.disableNonEssentialCookies();
    }
    
    disableNonEssentialCookies() {
        // En este caso particular, como solo usamos cookies esenciales,
        // no hay mucho que desactivar, pero aquí es donde podrías
        // desactivar Google Analytics, tracking, etc.
        
        console.log('Cookies no esenciales desactivadas');
    }
    
    setCookie(name, value, days) {
        const expires = new Date();
        expires.setTime(expires.getTime() + (days * 24 * 60 * 60 * 1000));
        document.cookie = `${name}=${value};expires=${expires.toUTCString()};path=/;SameSite=Lax`;
    }
    
    getCookie(name) {
        const nameEQ = name + "=";
        const ca = document.cookie.split(';');
        
        for (let i = 0; i < ca.length; i++) {
            let c = ca[i];
            while (c.charAt(0) === ' ') {
                c = c.substring(1, c.length);
            }
            if (c.indexOf(nameEQ) === 0) {
                return c.substring(nameEQ.length, c.length);
            }
        }
        return null;
    }
    
    // Método público para verificar el consentimiento
    isAccepted() {
        return this.getCookie(this.cookieName) === 'accepted';
    }
    
    // Método público para revocar el consentimiento
    revoke() {
        this.setCookie(this.cookieName, '', -1);
        location.reload();
    }
}

// Inicializar el sistema de cookies
const cookieConsent = new CookieConsent();

// Exponer funciones útiles globalmente
window.cookieConsent = cookieConsent;