/**
 * Cookie Consent Management
 * Gestiona el banner de consentimiento de cookies y las preferencias del usuario
 */

class CookieConsent {
    constructor() {
        this.cookieName = 'cookie_consent';
        this.cookieExpiry = 365; // días
        this.banner = null;
        
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