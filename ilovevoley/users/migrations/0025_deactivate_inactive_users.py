"""Apagado masivo de cuentas inactivas desde el 1 de febrero de 2026 (#327).

Se desactivan (`is_active=False`) las cuentas que no han iniciado sesión desde
el 1 de febrero de este año, incluyendo las que nunca han entrado y se dieron de
alta antes de esa fecha. No se envía ningún correo y no se toca `is_approved`:
la reentrada a moderación es a la carta (la persona la pide al intentar entrar).

Se revocan las suscripciones push de las cuentas afectadas. La migración no es
reversible: no hay forma de distinguir estas desactivaciones de una desactivación
legítima hecha por un administrador, así que revertirla reactivaría cuentas por
error.
"""

import datetime

from django.db import migrations
from django.db.models import Q

CUTOFF = datetime.datetime(2026, 2, 1, tzinfo=datetime.timezone.utc)


def deactivate_inactive_users(apps, schema_editor):
    User = apps.get_model('users', 'User')
    WebPushSubscription = apps.get_model('users', 'WebPushSubscription')

    inactive_ids = list(
        User.objects.filter(
            is_active=True,
            is_staff=False,
            is_superuser=False,
        )
        .filter(
            Q(last_login__lt=CUTOFF)
            | Q(last_login__isnull=True, date_joined__lt=CUTOFF)
        )
        .values_list('id', flat=True)
    )
    if not inactive_ids:
        return

    WebPushSubscription.objects.filter(user_id__in=inactive_ids).delete()
    User.objects.filter(id__in=inactive_ids).update(is_active=False)


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0024_user_reactivation_requested_at'),
    ]

    operations = [
        migrations.RunPython(deactivate_inactive_users, migrations.RunPython.noop),
    ]
