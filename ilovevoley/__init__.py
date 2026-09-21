"""Compatibilidad con el antiguo paquete ``videosvoley``.

Las migraciones históricas ya aplicadas en producción serializan callables por
ruta punteada (por ejemplo ``videosvoley.content.models.content.image_upload_path``)
e importan módulos como ``videosvoley.videos.models``. Esos ficheros no se
editan, así que aquí se registra un alias que resuelve ``videosvoley`` y todos
sus subpaquetes contra el paquete actual ``ilovevoley``.
"""

import importlib
import importlib.abc
import importlib.util
import sys

_LEGACY_NAME = "videosvoley"
_CURRENT_NAME = __name__


class _LegacyAliasLoader(importlib.abc.Loader):
    """Carga un módulo aliased devolviendo su equivalente actual."""

    def __init__(self, target_name):
        self._target_name = target_name
        self._original_spec = None
        self._original_loader = None

    def create_module(self, spec):
        module = importlib.import_module(self._target_name)
        # ``module_from_spec`` sobrescribirá ``__spec__`` y ``__loader__`` con
        # los del alias; se guardan para restaurarlos y que las importaciones
        # relativas del módulo real sigan coherentes.
        self._original_spec = getattr(module, "__spec__", None)
        self._original_loader = getattr(module, "__loader__", None)
        return module

    def exec_module(self, module):
        # El módulo destino ya está completamente inicializado.
        if self._original_spec is not None:
            module.__spec__ = self._original_spec
        if self._original_loader is not None:
            module.__loader__ = self._original_loader


class _LegacyAliasFinder(importlib.abc.MetaPathFinder):
    """Resuelve ``videosvoley[.submodulo]`` contra ``ilovevoley[.submodulo]``."""

    def find_spec(self, fullname, path=None, target=None):
        if fullname != _LEGACY_NAME and not fullname.startswith(_LEGACY_NAME + "."):
            return None
        target_name = _CURRENT_NAME + fullname[len(_LEGACY_NAME):]
        return importlib.util.spec_from_loader(fullname, _LegacyAliasLoader(target_name))


if _LEGACY_NAME not in sys.modules:
    sys.modules[_LEGACY_NAME] = sys.modules[_CURRENT_NAME]

if not any(isinstance(finder, _LegacyAliasFinder) for finder in sys.meta_path):
    sys.meta_path.insert(0, _LegacyAliasFinder())
