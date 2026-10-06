"""Etiquetado de deportistas en imágenes (#362): permisos, aislamiento y galería."""
import uuid

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from ilovevoley.competitions.models import League, Match
from ilovevoley.content.models import Image
from ilovevoley.content.services import taggable_persons
from ilovevoley.core.models import Category, Organization, Season
from ilovevoley.rosters.models import Person, PlayerRole
from ilovevoley.teams.models import Club, Team
from ilovevoley.users.models import Membership

TINY_GIF = (
    b'GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!'
    b'\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00'
    b'\x00\x02\x02D\x01\x00;'
)


@override_settings(ALLOWED_HOSTS=['testclub.ilovevoley.es', 'localhost'])
class ImageTaggingTests(TestCase):
    def setUp(self):
        cache.clear()
        User = get_user_model()
        self.season = Season.objects.resolve('2025-26')
        self.category = Category.objects.create(name='Senior', is_active=True)

        self.club_a = Club.objects.create(official_name='Club A', federation_id='C-A')
        self.org_a = Organization.objects.create(
            slug='testclub', name='Club A', club=self.club_a,
            club_team_names={'1': 'Club A'}, is_active=True,
        )
        self.team_a = Team.objects.create(
            name='Club A Senior', category=self.category, club=self.club_a,
            federation_id='T-A', is_active=True,
        )
        self.other_team = Team.objects.create(
            name='Club A Juvenil', category=self.category, club=self.club_a,
            federation_id='T-A2', is_active=True,
        )

        self.club_b = Club.objects.create(official_name='Club B', federation_id='C-B')
        self.org_b = Organization.objects.create(
            slug='otherclub', name='Club B', club=self.club_b,
            club_team_names={'1': 'Club B'}, is_active=True,
        )
        self.team_b = Team.objects.create(
            name='Club B Senior', category=self.category, club=self.club_b,
            federation_id='T-B', is_active=True,
        )

        self.uploader = User.objects.create_user(username='uploader', password='pass')
        Membership.objects.create(user=self.uploader, organization=self.org_a, is_approved=True)
        self.other_member = User.objects.create_user(username='other', password='pass')
        Membership.objects.create(user=self.other_member, organization=self.org_a, is_approved=True)
        self.manager = User.objects.create_user(username='manager', password='pass')
        Membership.objects.create(
            user=self.manager, organization=self.org_a, role='manager', is_approved=True
        )

        self.person_a = Person.objects.create(first_name='Laura', last_name='García')
        self.person_a.organizations.add(self.org_a)
        PlayerRole.objects.create(
            person=self.person_a, team=self.team_a, season=self.season, is_active=True,
        )
        self.other_person = Person.objects.create(first_name='Nuria', last_name='Ruiz')
        self.other_person.organizations.add(self.org_a)
        PlayerRole.objects.create(
            person=self.other_person, team=self.other_team, season=self.season, is_active=True,
        )
        self.person_b = Person.objects.create(first_name='Marta', last_name='Navarro')
        self.person_b.organizations.add(self.org_b)
        PlayerRole.objects.create(
            person=self.person_b, team=self.team_b, season=self.season, is_active=True,
        )

        self.album_group_id = uuid.uuid4()
        self.image = Image.objects.create(
            image=SimpleUploadedFile('photo.jpg', TINY_GIF, content_type='image/jpeg'),
            title='Foto', uploaded_by=self.uploader, organization=self.org_a,
            status='approved', season=self.season,
            album_group_id=self.album_group_id, album_name='Álbum',
        )

    def test_uploader_tags_own_image(self):
        self.client.force_login(self.uploader)
        response = self.client.post(
            reverse('content:image_tag', args=[self.image.id]),
            {'person_ids': [self.person_a.id], 'action': 'replace'},
            HTTP_HOST='testclub.ilovevoley.es',
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(list(self.image.persons.values_list('id', flat=True)), [self.person_a.id])

    def test_uploader_sees_tag_picker_on_image_detail(self):
        self.image.persons.add(self.person_a)
        self.client.force_login(self.uploader)
        response = self.client.get(
            reverse('content:image_detail', args=[self.image.id]),
            HTTP_HOST='testclub.ilovevoley.es',
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="person_ids"')
        self.assertContains(response, self.person_a.full_name)

    def test_member_without_permission_cannot_tag_someone_elses_image(self):
        self.client.force_login(self.other_member)
        response = self.client.post(
            reverse('content:image_tag', args=[self.image.id]),
            {'person_ids': [self.person_a.id], 'action': 'replace'},
            HTTP_HOST='testclub.ilovevoley.es',
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(self.image.persons.exists())

    def test_manager_can_tag_any_image_in_the_club(self):
        self.client.force_login(self.manager)
        self.client.post(
            reverse('content:image_tag', args=[self.image.id]),
            {'person_ids': [self.person_a.id], 'action': 'replace'},
            HTTP_HOST='testclub.ilovevoley.es',
        )
        self.assertEqual(list(self.image.persons.values_list('id', flat=True)), [self.person_a.id])

    def test_cannot_tag_a_person_from_another_club(self):
        self.client.force_login(self.uploader)
        self.client.post(
            reverse('content:image_tag', args=[self.image.id]),
            {'person_ids': [self.person_b.id], 'action': 'replace'},
            HTTP_HOST='testclub.ilovevoley.es',
        )
        self.assertFalse(self.image.persons.exists())

    def test_gallery_filters_by_tagged_person(self):
        other_image = Image.objects.create(
            image=SimpleUploadedFile('other.jpg', TINY_GIF, content_type='image/jpeg'),
            title='Otra', uploaded_by=self.uploader, organization=self.org_a,
            status='approved', season=self.season,
        )
        self.image.persons.add(self.person_a)

        self.client.force_login(self.uploader)
        response = self.client.get(
            reverse('content:image_gallery_individual'),
            {'person': self.person_a.id, 'season': '', 'show_all': '1'},
            HTTP_HOST='testclub.ilovevoley.es',
        )
        self.assertEqual(response.context['tagged_person'], self.person_a)
        returned = list(response.context['page_obj'].object_list)
        self.assertIn(self.image, returned)
        self.assertNotIn(other_image, returned)

    def test_person_detail_lists_tagged_photos(self):
        self.image.persons.add(self.person_a)
        self.client.force_login(self.uploader)
        response = self.client.get(
            reverse('rosters:person_detail', args=[self.person_a.id]),
            HTTP_HOST='testclub.ilovevoley.es',
        )
        self.assertIn(self.image, response.context['tagged_images'])

    def test_taggable_persons_limits_to_match_rosters(self):
        league = League.objects.create(
            name='Liga', federation_id='L-1', season=self.season,
            is_active=True, visibility_type='main', is_our_team_related=True,
        )
        match = Match.objects.create(
            league=league, home_team=self.team_a, away_team=self.team_b,
            match_date=timezone.now(), round_number=1, status='scheduled',
        )
        candidates = set(taggable_persons(match, self.org_a))
        self.assertIn(self.person_a, candidates)
        self.assertNotIn(self.other_person, candidates)

    def test_bulk_tagging_requires_staff(self):
        self.client.force_login(self.other_member)
        response = self.client.get(
            reverse('content:image_tag_bulk'), {'album': self.album_group_id},
            HTTP_HOST='testclub.ilovevoley.es',
        )
        self.assertEqual(response.status_code, 403)

    def test_manager_bulk_page_renders(self):
        self.client.force_login(self.manager)
        response = self.client.get(
            reverse('content:image_tag_bulk'), {'album': self.album_group_id},
            HTTP_HOST='testclub.ilovevoley.es',
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.person_a.full_name)

    def test_manager_bulk_tags_images(self):
        self.client.force_login(self.manager)
        response = self.client.post(
            reverse('content:image_tag_bulk'),
            {
                'album': self.album_group_id,
                'image_ids': [self.image.id],
                'person_ids': [self.person_a.id],
                'action': 'add',
            },
            HTTP_HOST='testclub.ilovevoley.es',
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(self.image.persons.filter(id=self.person_a.id).exists())
