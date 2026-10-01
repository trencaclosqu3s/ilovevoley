from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from django_celery_beat.admin import PeriodicTaskAdmin as BasePeriodicTaskAdmin
from django_celery_beat.admin import PeriodicTaskForm as BasePeriodicTaskForm
from django_celery_beat.models import PeriodicTask
from unfold.admin import ModelAdmin


# Desregistrar el admin por defecto de django-celery-beat para poner el de Unfold.
try:
    admin.site.unregister(PeriodicTask)
except admin.sites.NotRegistered:
    pass


class PeriodicTaskForm(BasePeriodicTaskForm):
    """Aclara los campos de tarea y de argumentos.

    ``regtask`` es el desplegable de tareas registradas; ``task`` permite escribir
    un nombre a mano. El ``clean()`` del form base hace que ``regtask`` prevalezca.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['regtask'].help_text = _(
            'Elige aquí la tarea: solo aparecen las registradas en el worker.'
        )
        self.fields['task'].help_text = _(
            'Alternativa manual: nombre exacto de la tarea, solo si no está en el desplegable.'
        )
        self.fields['args'].help_text = _('Argumentos posicionales en JSON válido (lista).')
        self.fields['kwargs'].help_text = _(
            'Argumentos con nombre en JSON válido, por ejemplo {"delay": 2.0}. '
            'Deben coincidir con la firma de la tarea.'
        )


@admin.register(PeriodicTask)
class CustomPeriodicTaskAdmin(BasePeriodicTaskAdmin, ModelAdmin):
    """Admin de tareas periódicas de Celery con estilo Unfold.

    No sobrescribe ``get_actions``: así hereda del admin base ``run_tasks`` (que
    lanza cualquier tarea registrada por su nombre, no una lista fija), además de
    ``enable_tasks``, ``disable_tasks`` y ``toggle_tasks``.
    """

    form = PeriodicTaskForm

    # Añade ``task`` (qué ejecuta cada fila) y ``total_run_count`` a la lista.
    list_display = (
        'name',
        'task',
        'enabled',
        'scheduler',
        'interval',
        'start_time',
        'last_run_at',
        'one_off',
        'total_run_count',
    )
