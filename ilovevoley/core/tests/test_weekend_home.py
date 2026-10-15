from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from ilovevoley.competitions.models import League, Match
from ilovevoley.competitions.services.weekend import weekend_bounds
from ilovevoley.content.models import Image
from ilovevoley.core.models import Category, Organization, Season
from ilovevoley.teams.models import Club, Team
from ilovevoley.users.models import CategoryPreference, Membership

HOST = 'testclub.ilovevoley.es'


@override_settings(ALLOWED_HOSTS=[HOST, 'localhost'])
class WeekendHomeViewTests(TestCase):
    """Vista /finde/ y visibilidad de la entrada «Este finde» en plantillas."""

    def setUp(self):
        cache.clear()
        self.club = Club.objects.create(official_name='Club Test', federation_id='C_WKND_HOME')
        self.org = Organization.objects.create(
            slug='testclub',
            name='Test Club',
            club=self.club,
            club_team_names={'1': 'Test Club'},
            is_active=True,
        )
        self.club_other = Club.objects.create(official_name='Club Rival', federation_id='C_WKND_OTHER')
        self.org_other = Organization.objects.create(
            slug='otherclub',
            name='Other Club',
            club=self.club_other,
            club_team_names={'1': 'Other Club'},
            is_active=True,
        )
        self.user = get_user_model().objects.create_user(username='weekend_member', password='pass')
        Membership.objects.create(
            user=self.user, organization=self.org, is_approved=True, role='member',
        )
        self.senior = Category.objects.create(name='Senior', is_active=True)
        self.season = Season.objects.resolve('2026-2027')
        self.ours = Team.objects.create(
            name='Test Club Senior', category=self.senior, club=self.club,
            federation_id='T_WKND_OURS', is_active=True,
        )
        self.rival = Team.objects.create(
            name='Rival A', category=self.senior, federation_id='T_WKND_RIV', is_active=True,
        )
        self.other_org_team = Team.objects.create(
            name='Other Club Senior', category=self.senior, club=self.club_other,
            federation_id='T_WKND_OTH', is_active=True,
        )
        self.league = League.objects.create(
            name='Liga Senior', federation_id='L_WKND_L1', season=self.season, is_active=True,
        )
        self.league.categories.add(self.senior)
        self.client.force_login(self.user)

    def _match_in_weekend_window(self, home, away, league=None, **kwargs):
        window_start, _ = weekend_bounds()
        match_date = window_start + timedelta(days=1, hours=12)
        kwargs.setdefault('status', 'scheduled')
        return Match.objects.create(
            home_team=home,
            away_team=away,
            league=league or self.league,
            match_date=match_date,
            **kwargs,
        )

    def _photo(self, organization, match=None):
        return Image.objects.create(
            title='Foto finde',
            image='photo.jpg',
            uploaded_by=self.user,
            organization=organization,
            match=match,
            status='approved',
        )

    def test_anonymous_weekend_redirects_to_login(self):
        # Justificación: AC «anónimo mantiene el comportamiento actual»; la pantalla
        # no debe abrirse sin sesión (tenant_access_required → login).
        self.client.logout()
        response = self.client.get(reverse('weekend'), HTTP_HOST=HOST)
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login/', response.url)

    def test_weekend_shows_own_upcoming_and_isolates_other_tenant(self):
        # Justificación: regla de negocio multi-tenant; partidos y fotos de otra
        # organización no deben filtrarse en la vista del club actual.
        pref = CategoryPreference.objects.create(user=self.user, organization=self.org)
        pref.categories.add(self.senior)

        ours_match = self._match_in_weekend_window(self.ours, self.rival)
        other_match = self._match_in_weekend_window(self.other_org_team, self.rival)
        other_photo = self._photo(self.org_other, match=other_match)

        response = self.client.get(reverse('weekend'), HTTP_HOST=HOST)
        self.assertEqual(response.status_code, 200)
        upcoming = list(response.context['upcoming'])
        photos = list(response.context['photos'])
        self.assertIn(ours_match, upcoming)
        self.assertNotIn(other_match, upcoming)
        self.assertNotIn(other_photo, photos)

    def test_weekend_entry_none_without_follow_preferences(self):
        # Justificación: producto «solo con preferencias y contenido»; sin seguimiento
        # no hay entrada en navegación (weekend_entry = None).
        response = self.client.get(reverse('competitions:league_list'), HTTP_HOST=HOST)
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context['weekend_entry'])

    def test_weekend_entry_and_finde_link_when_preferences_and_content(self):
        # Justificación: con preferencias y partido relevante, la entrada existe y
        # la UI ofrece el enlace a /finde/ (pestaña inferior o card).
        pref = CategoryPreference.objects.create(user=self.user, organization=self.org)
        pref.teams.set([self.ours])
        self._match_in_weekend_window(self.ours, self.rival)

        response = self.client.get(reverse('competitions:league_list'), HTTP_HOST=HOST)
        self.assertEqual(response.status_code, 200)
        entry = response.context['weekend_entry']
        self.assertIsNotNone(entry)
        self.assertTrue(entry['has_content'])
        self.assertContains(response, '/finde/')

    def test_is_home_screen_on_portada_views(self):
        # Justificación: el card del sidebar solo debe mostrarse en portadas del tenant.
        pref = CategoryPreference.objects.create(user=self.user, organization=self.org)
        pref.teams.set([self.ours])

        for url_name in ('content:video_list', 'content:image_gallery', 'competitions:league_list'):
            with self.subTest(url_name=url_name):
                response = self.client.get(reverse(url_name), HTTP_HOST=HOST)
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context['is_home_screen'])

    def test_is_home_screen_false_on_internal_page(self):
        # Justificación: páginas internas (p. ej. Acerca de) no son portada.
        response = self.client.get(reverse('core:about'), HTTP_HOST=HOST)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context['is_home_screen'])
