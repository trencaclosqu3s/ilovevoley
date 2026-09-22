"""
Configuración de logging para producción

Para usar esta configuración, añadir al final de settings.py:

    if not DEBUG:
        from .logging_production import LOGGING
"""

import os

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '[{levelname}] {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
        'simple': {
            'format': '[{levelname}] {asctime} {message}',
            'style': '{',
        },
    },
    'filters': {
        'require_debug_false': {
            '()': 'django.utils.log.RequireDebugFalse',
        },
        'require_debug_true': {
            '()': 'django.utils.log.RequireDebugTrue',
        },
    },
    'handlers': {
        'console': {
            'level': 'INFO',
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
        },
        'file': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': '/var/log/django/ilovevoley.log',
            'maxBytes': 1024 * 1024 * 10,  # 10 MB
            'backupCount': 5,
            'formatter': 'verbose',
        },
        'error_file': {
            'level': 'ERROR',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': '/var/log/django/ilovevoley_errors.log',
            'maxBytes': 1024 * 1024 * 10,  # 10 MB
            'backupCount': 5,
            'formatter': 'verbose',
        },
        'mail_admins': {
            'level': 'ERROR',
            'class': 'django.utils.log.AdminEmailHandler',
            'filters': ['require_debug_false'],
            'formatter': 'verbose',
        },
    },
    'loggers': {
        # Logger principal de la aplicación
        'ilovevoley': {
            'handlers': ['console', 'file', 'error_file'],
            'level': 'INFO',
            'propagate': False,
        },
        # Logger específico para videos
        'ilovevoley.videos': {
            'handlers': ['console', 'file', 'error_file'],
            'level': 'INFO',
            'propagate': False,
        },
        # Logger específico para usuarios
        'ilovevoley.users': {
            'handlers': ['console', 'file', 'error_file'],
            'level': 'INFO',
            'propagate': False,
        },
        # Logger de Django
        'django': {
            'handlers': ['console', 'file'],
            'level': 'INFO',
            'propagate': False,
        },
        # Errores de Django
        'django.request': {
            'handlers': ['error_file', 'mail_admins'],
            'level': 'ERROR',
            'propagate': False,
        },
        # Errores de seguridad
        'django.security': {
            'handlers': ['error_file', 'mail_admins'],
            'level': 'ERROR',
            'propagate': False,
        },
        # Base de datos (solo errores)
        'django.db.backends': {
            'handlers': ['error_file'],
            'level': 'ERROR',
            'propagate': False,
        },
    },
    'root': {
        'handlers': ['console', 'file'],
        'level': 'INFO',
    },
}


# Instrucciones de instalación:
"""
1. Crear directorio de logs:
   sudo mkdir -p /var/log/django
   sudo chown $USER:$USER /var/log/django
   chmod 755 /var/log/django

2. En settings.py, añadir al final:
   
   # Logging configuration
   if not DEBUG:
       from .logging_production import LOGGING
   else:
       # Logging simple para desarrollo
       LOGGING = {
           'version': 1,
           'disable_existing_loggers': False,
           'handlers': {
               'console': {
                   'class': 'logging.StreamHandler',
               },
           },
           'root': {
               'handlers': ['console'],
               'level': 'INFO',
           },
       }

3. Configurar logrotate (opcional pero recomendado):
   sudo nano /etc/logrotate.d/django-ilovevoley
   
   Contenido:
   /var/log/django/*.log {
       daily
       missingok
       rotate 30
       compress
       delaycompress
       notifempty
       create 0644 www-data www-data
       sharedscripts
       postrotate
           systemctl reload tu-servicio-django > /dev/null 2>&1 || true
       endscript
   }

4. Probar logging:
   python manage.py shell
   >>> import logging
   >>> logger = logging.getLogger('ilovevoley')
   >>> logger.info('Test log message')
   >>> logger.error('Test error message')
   
   Verificar:
   tail -f /var/log/django/ilovevoley.log
   tail -f /var/log/django/ilovevoley_errors.log

5. Para Docker, montar volumen:
   En docker-compose.yml:
   
   services:
     web:
       volumes:
         - ./logs:/var/log/django
   
   Y crear directorio:
   mkdir logs
"""