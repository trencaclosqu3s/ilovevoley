"""Programación de tareas periódicas de Celery (`CELERY_BEAT_SCHEDULE`).

Se importa desde `config/settings.py` para mantener settings centrado en
configuración Django y este módulo centrado en *cuándo* corre cada tarea.

Contexto: Beat corre con `django_celery_beat.schedulers:DatabaseScheduler`, que
en cada arranque hace `update_from_dict(CELERY_BEAT_SCHEDULE)`: crea y actualiza
las `PeriodicTask` desde este diccionario, pero **no borra** las que ya no
aparecen. Por eso las filas creadas a mano en producción (con nombres dispares y
timezones mezclados UTC/Europe/Madrid) se sustituyen aquí por entradas
versionadas y la migración de datos `core.0010_delete_legacy_periodic_tasks` las
elimina para no duplicar ejecuciones.

Los `crontab(...)` se interpretan en `CELERY_TIMEZONE`, que es `Europe/Madrid`
(igual que `TIME_ZONE`), no en UTC. Los horarios de abajo son hora peninsular.
"""

from datetime import timedelta

from celery.schedules import crontab

CELERY_BEAT_SCHEDULE = {
    # --- Media / mantenimiento -------------------------------------------------
    # Los ZIP de álbumes caducan a las 24 h; build_album_zip limpia antes de cada
    # generación, así que una pasada diaria acota el disco residual.
    'cleanup-expired-album-zips': {
        'task': 'cleanup_expired_album_zips',
        'schedule': timedelta(days=1),
    },
    # Limpieza de auditoría de avisos push (retención 90 días).
    'cleanup-expired-web-push-audits': {
        'task': 'cleanup_expired_web_push_audits',
        'schedule': timedelta(days=1),
    },
    # Ciclo de vida y aviso de cuentas inactivas (#327). Pasada diaria a las 03:30 peninsular.
    'process-inactive-users': {
        'task': 'process_inactive_users',
        'schedule': crontab(minute=30, hour=3),
    },
    # Recordatorio push 2 h antes del partido. Ventana de ±15 min por pasada, así
    # que una cadencia de 10 min no deja huecos.
    'send-match-reminders-2h': {
        'task': 'send_match_reminders_2h',
        'schedule': timedelta(minutes=10),
    },
    # --- Scrapers federativos legacy (antes creados a mano en la BD) -----------
    # Nombres normalizados (slug) para que DatabaseScheduler los reconozca; las
    # filas viejas las borra la migración de datos.
    'scrape-clubs': {
        'task': 'scrape_clubs',
        'schedule': crontab(minute=0, hour=6),
        'kwargs': {'match_teams': True, 'delay': 2.0},
        'options': {'expire_seconds': 3600},
    },
    'enrich-matches': {
        'task': 'enrich_matches_json',
        'schedule': crontab(minute=0, hour=8),
        'options': {'expire_seconds': 3600},
    },
    'scrape-all-leagues': {
        'task': 'scrape_all_leagues',
        'schedule': crontab(minute=0, hour='*/4'),
        'kwargs': {'delay': 2.0},
        'options': {'expire_seconds': 3600},
    },
    'scrape-json-results': {
        'task': 'scrape_json_results',
        'schedule': crontab(minute=0, hour='*/4'),
        'options': {'expire_seconds': 3600},
    },
    'scrape-json-upcoming': {
        'task': 'scrape_json_upcoming',
        'schedule': crontab(minute=0, hour='*/4'),
        'options': {'expire_seconds': 3600},
    },
    'scrape-and-enrich-all': {
        'task': 'scrape_and_enrich_all',
        'schedule': crontab(minute=30, hour=7),
        'options': {'expire_seconds': 3600},
    },
    # --- Convocatorias y seguimiento federativo (#287 / #288) ------------------
    # La federación publica circulares de forma esporádica; cada 6 h es de sobra.
    # El seguimiento va 15 min después para no solapar la descarga de PDFs.
    'scrape-balearic-callups': {
        'task': 'scrape_balearic_callups',
        'schedule': crontab(minute=0, hour='*/6'),
        'options': {'expire_seconds': 3600},
    },
    'scrape-balearic-tracking': {
        'task': 'scrape_balearic_tracking',
        'schedule': crontab(minute=15, hour='*/6'),
        'options': {'expire_seconds': 3600},
    },
}
