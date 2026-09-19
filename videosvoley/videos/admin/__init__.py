"""Configuración del admin de la app videos, repartida por dominio.

Importar los submódulos aquí es lo que ejecuta los decoradores
@admin.register. No eliminar ningún import: el modelo dejaría de
aparecer en el admin sin que nada falle.
"""

from . import category  # noqa: F401
from . import content  # noqa: F401
from . import legacy  # noqa: F401
from . import teams  # noqa: F401
from . import competitions  # noqa: F401
from . import rosters  # noqa: F401
from . import periodic_tasks  # noqa: F401
