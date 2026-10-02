from io import BytesIO

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from PIL import Image as PILImage
from PIL.ExifTags import Base, GPS

from ilovevoley.core.models import Organization
from ilovevoley.rosters.models import Person
from ilovevoley.users.models import Membership


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


class ModelSaveSanitizationTests(TestCase):
    def test_user_model_save_automatically_sanitizes(self):
        raw_image = _create_image_with_gps()
        uploaded = SimpleUploadedFile('avatar_admin.jpg', raw_image.read(), content_type='image/jpeg')

        user = get_user_model().objects.create_user(
            username='admin_avatar_user',
            avatar=uploaded,
        )
        user.avatar.open()
        saved_img = PILImage.open(user.avatar)
        self.assertEqual(dict(saved_img.getexif().get_ifd(Base.GPSInfo)), {})


class UserCanEditPersonTests(TestCase):
    """``User.can_edit_person`` solo autoriza a managers/admins del tenant."""

    def setUp(self):
        User = get_user_model()
        self.org_a = Organization.objects.create(slug='org-a', name='Org A')
        self.org_b = Organization.objects.create(slug='org-b', name='Org B')

        self.staff = User.objects.create_user(
            username='staff', password='pass', is_staff=True,
        )
        Membership.objects.create(
            user=self.staff, organization=self.org_a, is_approved=True, role='manager',
        )
        self.member = User.objects.create_user(username='member', password='pass')
        Membership.objects.create(
            user=self.member, organization=self.org_a, is_approved=True,
        )
        self.person_a = Person.objects.create(
            first_name='Ana', last_name='Propia', organization=self.org_a,
        )
        self.person_b = Person.objects.create(
            first_name='Bea', last_name='Ajena', organization=self.org_b,
        )

    def test_staff_global_sin_membresia_no_edita_otra_organizacion(self):
        # Tiene is_staff y membresía en A, pero ninguna en B.
        self.assertFalse(self.staff.can_edit_person(self.person_b, self.org_b))
        # Y sí puede sobre las fichas de su propia organización.
        self.assertTrue(self.staff.can_edit_person(self.person_a, self.org_a))

    def test_miembro_sin_staff_no_edita_ficha_del_club(self):
        self.assertFalse(self.member.can_edit_person(self.person_a, self.org_a))

    def test_staff_global_con_rol_miembro_no_edita_ficha_del_club(self):
        User = get_user_model()
        staff_member = User.objects.create_user(
            username='staff-member', password='pass', is_staff=True,
        )
        Membership.objects.create(
            user=staff_member, organization=self.org_a, role='member', is_approved=True,
        )
        self.assertFalse(staff_member.can_edit_person(self.person_a, self.org_a))
