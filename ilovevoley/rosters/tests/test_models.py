from datetime import date
from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError
from django.test import TestCase
from PIL import Image as PILImage
from PIL.ExifTags import Base, GPS

from ilovevoley.core.models import Organization, Season
from ilovevoley.rosters.models import Person, PlayerRole, StaffRole
from ilovevoley.teams.models import Team


def _create_image_with_gps(width=100, height=80, orientation=None, format='JPEG'):
    img = PILImage.new('RGB', (width, height), color='blue')
    exif = img.getexif()
    exif[Base.Make] = 'TestCamera'
    if orientation is not None:
        exif[Base.Orientation] = orientation
    gps_ifd = exif.get_ifd(Base.GPSInfo)
    gps_ifd[GPS.GPSLatitude] = (41.0, 23.0, 10.0)
    gps_ifd[GPS.GPSLongitude] = (2.0, 10.0, 5.0)

    buf = BytesIO()
    img.save(buf, format=format, exif=exif)
    buf.seek(0)
    return buf


class PersonIdentityConstraintTests(TestCase):
    """La identidad (nombre + año de nacimiento) es única en toda la plataforma."""

    def test_birth_year_se_deduce_de_la_fecha(self):
        person = Person.objects.create(
            first_name='Ana', last_name='Gomez', birth_date=date(2010, 5, 1),
        )
        self.assertEqual(person.birth_year, 2010)

    def test_misma_identidad_falla_aunque_cambie_la_fecha_dentro_del_año(self):
        Person.objects.create(first_name='Ana', last_name='Gomez', birth_date=date(2010, 5, 1))
        with self.assertRaises(IntegrityError):
            Person.objects.create(first_name='Ana', last_name='Gomez', birth_year=2010)


class PlayerRoleSeasonConstraintTests(TestCase):
    """Los roles se identifican por temporada: mismo jugador/dorsal en otra temporada es válido."""

    def setUp(self):
        self.org = Organization.objects.create(slug='club', name='Club')
        self.team = Team.objects.create(name='Infantil', federation_id='T-INF')
        self.person = Person.objects.create(
            first_name='Mario', last_name='Perez',
        )
        self.past = Season.objects.resolve('2025-26')
        self.current = Season.objects.resolve('2026-27')

    def test_mismo_jugador_y_dorsal_en_dos_temporadas(self):
        PlayerRole.objects.create(person=self.person, team=self.team, season=self.past, jersey_number=13)
        PlayerRole.objects.create(person=self.person, team=self.team, season=self.current, jersey_number=13)
        self.assertEqual(self.person.player_roles.count(), 2)

    def test_mismo_jugador_duplicado_en_la_misma_temporada_falla(self):
        PlayerRole.objects.create(person=self.person, team=self.team, season=self.past, jersey_number=7)
        with self.assertRaises(IntegrityError):
            PlayerRole.objects.create(person=self.person, team=self.team, season=self.past, jersey_number=8)

    def test_dorsal_duplicado_en_la_misma_temporada_falla(self):
        other = Person.objects.create(
            first_name='Luis', last_name='Gomez',
        )
        PlayerRole.objects.create(person=self.person, team=self.team, season=self.past, jersey_number=7)
        with self.assertRaises(IntegrityError):
            PlayerRole.objects.create(person=other, team=self.team, season=self.past, jersey_number=7)


class StaffRoleSeasonConstraintTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(slug='club-s', name='Club S')
        self.team = Team.objects.create(name='Infantil', federation_id='T-INF-S')
        self.person = Person.objects.create(
            first_name='Ana', last_name='Lopez',
        )
        self.past = Season.objects.resolve('2025-26')
        self.current = Season.objects.resolve('2026-27')

    def test_mismo_rol_en_dos_temporadas(self):
        StaffRole.objects.create(person=self.person, team=self.team, role='head_coach', season=self.past)
        StaffRole.objects.create(person=self.person, team=self.team, role='head_coach', season=self.current)
        self.assertEqual(self.person.staff_roles.count(), 2)

    def test_rol_duplicado_en_la_misma_temporada_falla(self):
        StaffRole.objects.create(person=self.person, team=self.team, role='head_coach', season=self.past)
        with self.assertRaises(IntegrityError):
            StaffRole.objects.create(person=self.person, team=self.team, role='head_coach', season=self.past)

    def test_dos_roles_distintos_en_el_mismo_equipo_y_temporada(self):
        StaffRole.objects.create(person=self.person, team=self.team, role='head_coach', season=self.past)
        StaffRole.objects.create(person=self.person, team=self.team, role='delegate', season=self.past)
        self.assertEqual(self.person.staff_roles.count(), 2)


class ModelSaveSanitizationTests(TestCase):
    def test_person_model_save_automatically_sanitizes(self):
        raw_image = _create_image_with_gps()
        uploaded = SimpleUploadedFile('person_admin.jpg', raw_image.read(), content_type='image/jpeg')

        person = Person.objects.create(
            first_name='Admin',
            last_name='Person',
            photo=uploaded,
        )
        person.photo.open()
        saved_img = PILImage.open(person.photo)
        self.assertEqual(dict(saved_img.getexif().get_ifd(Base.GPSInfo)), {})
