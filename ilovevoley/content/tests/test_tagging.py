"""Etiquetado de deportistas en imágenes (#362): permisos, aislamiento y galería."""
from ilovevoley.teams.tests.helpers import identity_of
import uuid
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from ilovevoley.competitions.models import League, Match
from ilovevoley.content.models import Image
from ilovevoley.content.services import apply_image_tags, taggable_persons, tagging_push_audience
from ilovevoley.content.tasks import notify_image_tagged_push_task
from ilovevoley.core.models import Category, Organization, Season
from ilovevoley.rosters.models import Person, PlayerRole
from ilovevoley.teams.models import Club, Team
from ilovevoley.users.models import Membership, NotificationPreference, WebPushSubscription
from ilovevoley.users.tasks import notify_web_push_organization_task

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
            person=self.person_a, identity=identity_of(self.team_a), season=self.season, is_active=True,
        )
        self.other_person = Person.objects.create(first_name='Nuria', last_name='Ruiz')
        self.other_person.organizations.add(self.org_a)
        PlayerRole.objects.create(
            person=self.other_person, identity=identity_of(self.other_team), season=self.season, is_active=True,
        )
        self.person_b = Person.objects.create(first_name='Marta', last_name='Navarro')
        self.person_b.organizations.add(self.org_b)
        PlayerRole.objects.create(
            person=self.person_b, identity=identity_of(self.team_b), season=self.season, is_active=True,
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

    def test_tagging_person_without_image_consent_tags_and_warns(self):
        # Se etiqueta igual: la etiqueta es lo que permite avisar al moderar (#122).
        self.person_a.image_consent = Person.ImageConsent.NONE
        self.person_a.save()
        self.client.force_login(self.uploader)
        response = self.client.post(
            reverse('content:image_tag', args=[self.image.id]),
            {'person_ids': [self.person_a.id], 'action': 'replace'},
            HTTP_HOST='testclub.ilovevoley.es', follow=True,
        )
        self.assertEqual(list(self.image.persons.values_list('id', flat=True)), [self.person_a.id])
        warnings = [str(m) for m in response.context['messages'] if m.level_tag == 'warning']
        self.assertEqual(len(warnings), 1)
        self.assertIn(self.person_a.full_name, warnings[0])

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

    def test_gallery_search_matches_tagged_person_name(self):
        other_image = Image.objects.create(
            image=SimpleUploadedFile('o2.jpg', TINY_GIF, content_type='image/jpeg'),
            title='Otra', uploaded_by=self.uploader, organization=self.org_a,
            status='approved', season=self.season,
        )
        self.image.persons.add(self.person_a)

        self.client.force_login(self.uploader)
        response = self.client.get(
            reverse('content:image_gallery_individual'),
            {'search': 'García', 'season': '', 'show_all': '1'},
            HTTP_HOST='testclub.ilovevoley.es',
        )
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

    def test_bulk_page_rejects_match_from_another_club(self):
        league = League.objects.create(
            name='Liga B', federation_id='L-B', season=self.season,
            is_active=True, visibility_type='main', is_our_team_related=True,
        )
        foreign_match = Match.objects.create(
            league=league, home_team=self.team_b, away_team=self.team_b,
            match_date=timezone.now(), round_number=1, status='scheduled',
        )
        self.client.force_login(self.manager)
        response = self.client.get(
            reverse('content:image_tag_bulk'), {'match': foreign_match.id},
            HTTP_HOST='testclub.ilovevoley.es',
        )
        self.assertEqual(response.status_code, 404)

    def test_bulk_ignores_external_next(self):
        self.client.force_login(self.manager)
        response = self.client.post(
            reverse('content:image_tag_bulk'),
            {
                'album': self.album_group_id,
                'image_ids': [self.image.id],
                'person_ids': [self.person_a.id],
                'action': 'add',
                'next': 'https://evil.example.com/',
            },
            HTTP_HOST='testclub.ilovevoley.es',
        )
        self.assertEqual(response.status_code, 302)
        self.assertNotIn('evil.example.com', response.url)

    @patch('ilovevoley.content.tasks.notify_image_tagged_push_task.delay')
    def test_tagging_enqueues_push_only_for_new_tags(self, mock_delay):
        self.client.force_login(self.uploader)
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(
                reverse('content:image_tag', args=[self.image.id]),
                {'person_ids': [self.person_a.id], 'action': 'replace'},
                HTTP_HOST='testclub.ilovevoley.es',
            )
        mock_delay.assert_called_once()
        args, _kwargs = mock_delay.call_args
        self.assertEqual(args[0], self.org_a.id)
        self.assertEqual(args[1], self.person_a.id)
        self.assertEqual(args[2], [self.image.id])
        self.assertEqual(args[3], self.uploader.id)

        # Reetiquetar a la misma persona no vuelve a avisar.
        mock_delay.reset_mock()
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(
                reverse('content:image_tag', args=[self.image.id]),
                {'person_ids': [self.person_a.id], 'action': 'replace'},
                HTTP_HOST='testclub.ilovevoley.es',
            )
        mock_delay.assert_not_called()

    @patch('ilovevoley.content.tasks.notify_image_tagged_push_task.delay')
    def test_pending_image_not_notified_until_approved(self, mock_delay):
        pending = Image.objects.create(
            image=SimpleUploadedFile('pend.jpg', TINY_GIF, content_type='image/jpeg'),
            title='Pendiente', uploaded_by=self.uploader, organization=self.org_a,
            status='pending',
        )
        with self.captureOnCommitCallbacks(execute=True):
            apply_image_tags(self.uploader, self.org_a, [pending], [self.person_a])
        mock_delay.assert_not_called()
        self.assertEqual(
            list(pending.persons.values_list('id', flat=True)), [self.person_a.id],
        )

        from ilovevoley.content.services import moderate_image

        with self.captureOnCommitCallbacks(execute=True):
            moderate_image(actor=self.manager, tenant=self.org_a, image=pending, decision='approve')

        mock_delay.assert_called_once()
        args, _kwargs = mock_delay.call_args
        self.assertEqual(args[1], self.person_a.id)
        self.assertEqual(args[2], [pending.id])
        self.assertEqual(args[3], self.manager.id)


@override_settings(ALLOWED_HOSTS=['testclub.ilovevoley.es', 'localhost'])
class ImageTagPushTests(TestCase):
    """El aviso de etiquetado solo llega al deportista y a su familia (#362)."""

    def setUp(self):
        cache.clear()
        User = get_user_model()
        self.org = Organization.objects.create(
            slug='testclub', name='Club A', club_team_names={'1': 'Club A'}, is_active=True,
        )
        self.player = User.objects.create_user(username='player', password='pass')
        self.parent1 = User.objects.create_user(username='parent1', password='pass')
        self.parent2 = User.objects.create_user(username='parent2', password='pass')
        self.unrelated = User.objects.create_user(username='unrelated', password='pass')
        for u in (self.player, self.parent1, self.parent2, self.unrelated):
            Membership.objects.create(user=u, organization=self.org, is_approved=True)

        self.person = Person.objects.create(first_name='Lluc', last_name='Puig', user=self.player)
        self.parent1.children.add(self.person)
        self.parent2.children.add(self.person)

        self.image = Image.objects.create(
            image=SimpleUploadedFile('p.jpg', TINY_GIF, content_type='image/jpeg'),
            title='Foto', uploaded_by=self.unrelated, organization=self.org, status='approved',
        )

    def _subscribe(self, user, endpoint):
        return WebPushSubscription.objects.create(
            user=user, organization=self.org, endpoint=endpoint,
            p256dh='key', auth='auth',
        )

    def test_audience_is_only_player_and_parents(self):
        player_id, parent_ids = tagging_push_audience(self.person, actor=self.unrelated)
        self.assertEqual(player_id, self.player.id)
        self.assertEqual(parent_ids, {self.parent1.id, self.parent2.id})

    def test_audience_excludes_the_actor(self):
        player_id, parent_ids = tagging_push_audience(self.person, actor=self.player)
        self.assertIsNone(player_id)
        self.assertNotIn(self.player.id, parent_ids)

        _, parent_ids = tagging_push_audience(self.person, actor=self.parent1)
        self.assertNotIn(self.parent1.id, parent_ids)

    @patch('ilovevoley.users.tasks.notify_web_push_organization_task.delay')
    def test_task_sends_player_and_parent_messages(self, mock_push):
        result = notify_image_tagged_push_task(
            self.org.id, self.person.id, [self.image.id], actor_id=self.unrelated.id,
        )
        self.assertEqual(result, 2)
        # La audiencia de padres se construye con un set: el orden no es estable.
        calls = {frozenset(call.kwargs['user_ids']): call.kwargs for call in mock_push.call_args_list}
        self.assertIn(frozenset({self.player.id}), calls)
        player_kwargs = calls[frozenset({self.player.id})]
        self.assertEqual(player_kwargs['title'], 'Te han etiquetado en una foto')
        self.assertEqual(player_kwargs['notification_type'], 'image_tag')
        parent_kwargs = calls[frozenset({self.parent1.id, self.parent2.id})]
        self.assertEqual(parent_kwargs['title'], 'Han etiquetado a Lluc Puig')
        self.assertEqual(
            parent_kwargs['url'], reverse('content:image_detail', args=[self.image.id]),
        )

    @patch('ilovevoley.users.tasks.send_web_push')
    def test_notify_task_targets_user_ids_and_respects_disabled_preference(self, mock_send):
        self._subscribe(self.player, 'https://fcm.googleapis.com/player')
        self._subscribe(self.parent1, 'https://fcm.googleapis.com/parent1')
        NotificationPreference.objects.create(
            user=self.parent1, organization=self.org,
            notification_type='image_tag', is_enabled=False,
        )

        sent = notify_web_push_organization_task(
            self.org.id, 'Título', 'Cuerpo',
            user_ids=[self.player.id, self.parent1.id],
            notification_type='image_tag',
        )
        self.assertEqual(sent, 1)
        recipients = {call.args[0].user_id for call in mock_send.call_args_list}
        self.assertEqual(recipients, {self.player.id})
