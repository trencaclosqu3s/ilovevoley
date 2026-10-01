"""Elimina las PeriodicTask creadas a mano que el schedule versionado sustituye.

`DatabaseScheduler` crea y actualiza las `PeriodicTask` desde
`CELERY_BEAT_SCHEDULE`, pero no borra las que ya no aparecen. Estas filas
antiguas (nombres dispares, timezones mezclados UTC/Europe/Madrid) seguirían
programadas en paralelo a las nuevas entradas de `config/celery_schedule.py`,
duplicando ejecuciones de los scrapers.
"""
from django.db import migrations

# Nombres exactos de las filas manuales presentes en producción el 03/10/2026.
LEGACY_PERIODIC_TASK_NAMES = [
    'clubs',
    'enrich_matches',
    'json results',
    'scrape ligas',
    "scrape y enrich to'",
    'upcoming_matches',
]


def delete_legacy_periodic_tasks(apps, schema_editor):
    PeriodicTask = apps.get_model('django_celery_beat', 'PeriodicTask')
    PeriodicTask.objects.filter(name__in=LEGACY_PERIODIC_TASK_NAMES).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0009_organization_notify_match_changes'),
        ('django_celery_beat', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(delete_legacy_periodic_tasks, migrations.RunPython.noop),
    ]
