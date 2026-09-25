// Dark Mode Toggle Handler
(function() {
    'use strict';
    
    // Obtener tema actual
    function getTheme() {
        return localStorage.getItem('theme') || 'light';
    }
    
    // Establecer tema
    function setTheme(theme) {
        localStorage.setItem('theme', theme);
        
        if (theme === 'dark') {
            document.documentElement.classList.add('dark');
        } else {
            document.documentElement.classList.remove('dark');
        }
        
        updateThemeIcons(theme);
    }
    
    // Actualizar iconos según el tema
    function updateThemeIcons(theme) {
        const lightIconsDesktop = document.getElementById('theme-toggle-light-icon-desktop');
        const darkIconsDesktop = document.getElementById('theme-toggle-dark-icon-desktop');
        const lightIconsMobile = document.getElementById('theme-toggle-light-icon-mobile');
        const darkIconsMobile = document.getElementById('theme-toggle-dark-icon-mobile');
        const themeLabelMobile = document.getElementById('theme-label-mobile');
        
        if (theme === 'dark') {
            // Mostrar icono de sol (para cambiar a light)
            if (lightIconsDesktop) lightIconsDesktop.classList.remove('hidden');
            if (darkIconsDesktop) darkIconsDesktop.classList.add('hidden');
            if (lightIconsMobile) lightIconsMobile.classList.remove('hidden');
            if (darkIconsMobile) darkIconsMobile.classList.add('hidden');
            if (themeLabelMobile) themeLabelMobile.textContent = 'Claro';
        } else {
            // Mostrar icono de luna (para cambiar a dark)
            if (lightIconsDesktop) lightIconsDesktop.classList.add('hidden');
            if (darkIconsDesktop) darkIconsDesktop.classList.remove('hidden');
            if (lightIconsMobile) lightIconsMobile.classList.add('hidden');
            if (darkIconsMobile) darkIconsMobile.classList.remove('hidden');
            if (themeLabelMobile) themeLabelMobile.textContent = 'Oscuro';
        }
    }
    
    // Toggle tema
    function toggleTheme() {
        const currentTheme = getTheme();
        const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
        setTheme(newTheme);
        
        // Mostrar notificación
        if (window.showToast) {
            const message = newTheme === 'dark' ? '🌙 Modo oscuro activado' : '☀️ Modo claro activado';
            window.showToast('info', message);
        }
    }
    
    // Inicializar cuando el DOM esté listo
    document.addEventListener('DOMContentLoaded', function() {
        const currentTheme = getTheme();
        updateThemeIcons(currentTheme);
        
        // Agregar event listeners a los botones
        const toggleDesktop = document.getElementById('theme-toggle-desktop');
        const toggleMobile = document.getElementById('theme-toggle-mobile');
        
        if (toggleDesktop) {
            toggleDesktop.addEventListener('click', toggleTheme);
        }
        
        if (toggleMobile) {
            toggleMobile.addEventListener('click', toggleTheme);
        }
    });
    
    // Exportar funciones globales si es necesario
    window.darkMode = {
        get: getTheme,
        set: setTheme,
        toggle: toggleTheme
    };
})();
