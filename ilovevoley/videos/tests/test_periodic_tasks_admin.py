from django.contrib import admin
from django.test import RequestFactory
from django_celery_beat.models import PeriodicTask


class _SuperuserStub:
    is_active = is_staff = is_superuser = is_authenticated = True

    def has_perm(self, *args, **kwargs):
        return True


def test_periodic_task_admin_keeps_generic_run_tasks_action():
    """Regresión: el admin custom no debe eliminar la acción ``run_tasks`` del
    admin base, que es la que lanza cualquier tarea registrada por su nombre (no
    una lista fija de tareas)."""
    model_admin = admin.site._registry[PeriodicTask]
    request = RequestFactory().get('/')
    request.user = _SuperuserStub()

    actions = model_admin.get_actions(request)

    assert 'run_tasks' in actions
    assert 'run_tasks_now' not in actions
