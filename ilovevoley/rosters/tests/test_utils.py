import uuid

from django.test import SimpleTestCase

from ilovevoley.rosters.models.rosters import person_photo_upload_path


class PersonPhotoUploadPathTests(SimpleTestCase):
    def test_person_photo_upload_path_generates_uuid(self):
        class DummyPerson:
            id = None
            first_name = 'Juan'
            last_name = 'Perez'

        path = person_photo_upload_path(DummyPerson(), 'mi_foto.png')
        # Format: people/<uuid>.png
        parts = path.split('/')
        self.assertEqual(parts[0], 'people')
        filename = parts[1]
        base_name, ext = filename.split('.')
        self.assertEqual(uuid.UUID(base_name).hex, base_name)
