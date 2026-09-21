import importlib

from django.test import SimpleTestCase


class LegacyPackageAliasTest(SimpleTestCase):
    """Las migraciones históricas serializan rutas ``videosvoley.*``.

    El alias debe resolver al mismo objeto de módulo que ``ilovevoley``; si
    cargara copias independientes, los modelos se registrarían dos veces.
    """

    def test_root_package_aliases_current_package(self):
        self.assertIs(
            importlib.import_module('videosvoley'),
            importlib.import_module('ilovevoley'),
        )

    def test_submodule_resolves_to_same_module(self):
        self.assertIs(
            importlib.import_module('videosvoley.videos.models'),
            importlib.import_module('ilovevoley.videos.models'),
        )

    def test_serialized_upload_path_from_historical_migration(self):
        # videos/0012_image.py referencia este callable por ruta punteada.
        self.assertIs(
            importlib.import_module('videosvoley.videos.models').image_upload_path,
            importlib.import_module('ilovevoley.videos.models').image_upload_path,
        )

    def test_serialized_upload_path_from_historical_roster_migration(self):
        # rosters/0001_initial.py referencia este callable por ruta punteada.
        self.assertIs(
            importlib.import_module('videosvoley.rosters.models.legacy').player_photo_upload_path,
            importlib.import_module('ilovevoley.rosters.models.legacy').player_photo_upload_path,
        )
