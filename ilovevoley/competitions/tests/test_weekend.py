from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from ilovevoley.competitions.models import League, Match
from ilovevoley.competitions.services.weekend import (
    following_match_filter,
    has_follow_preferences,
    recent_photos,
    recent_results,
    upcoming_matches,
    weekend_bounds,
    weekend_entry,
    weekend_overview,
    weekend_variant,
)
from ilovevoley.content.models import Image
from ilovevoley.core.models import Category, Organization, Season
from ilovevoley.teams.models import Club, Team
from ilovevoley.users.models import CategoryPreference, Membership


class WeekendBoundsAndVariantTests(TestCase):
    """Pruebas para el cálculo temporal de fin de semana y su variante."""

    def test_weekend_bounds_monday_to_following_weekend(self):
        # Justificación: Protege el caso límite de fecha y decisión de producto:
        # de lunes a jueves la ventana debe apuntar al fin de semana siguiente (viernes a domingo).
        tz = ZoneInfo('Europe/Madrid')
        monday = datetime(2026, 10, 12, 10, 0, 0, tzinfo=tz)  # Lunes
        start, end = weekend_bounds(monday)

        self.assertEqual(start, datetime(2026, 10, 16, 0, 0, 0, tzinfo=tz))
        self.assertEqual(end, datetime(2026, 10, 18, 23, 59, 59, 999999, tzinfo=tz))

    def test_weekend_bounds_sunday_to_current_weekend(self):
        # Justificación: Protege el caso límite de fin de semana en curso:
        # un domingo debe seguir acotando al fin de semana actual (desde el viernes previo).
        tz = ZoneInfo('Europe/Madrid')
        sunday = datetime(2026, 10, 18, 18, 30, 0, tzinfo=tz)  # Domingo
        start, end = weekend_bounds(sunday)

        self.assertEqual(start, datetime(2026, 10, 16, 0, 0, 0, tzinfo=tz))
        self.assertEqual(end, datetime(2026, 10, 18, 23, 59, 59, 999999, tzinfo=tz))

    def test_weekend_bounds_friday_and_saturday(self):
        # Justificación: Verifica que el viernes y el sábado pertenezcan al fin de semana en curso.
        tz = ZoneInfo('Europe/Madrid')
        friday = datetime(2026, 10, 16, 15, 0, 0, tzinfo=tz)
        saturday = datetime(2026, 10, 17, 12, 0, 0, tzinfo=tz)

        start_fri, end_fri = weekend_bounds(friday)
        start_sat, end_sat = weekend_bounds(saturday)

        self.assertEqual(start_fri, datetime(2026, 10, 16, 0, 0, 0, tzinfo=tz))
        self.assertEqual(end_fri, datetime(2026, 10, 18, 23, 59, 59, 999999, tzinfo=tz))
        self.assertEqual(start_sat, datetime(2026, 10, 16, 0, 0, 0, tzinfo=tz))
        self.assertEqual(end_sat, datetime(2026, 10, 18, 23, 59, 59, 999999, tzinfo=tz))

    def test_weekend_variant_selection(self):
        # Justificación: Protege la regla de negocio que determina el estado de la UI
        # (resumen en lunes, en vivo el finde, previa entre semana).
        tz = ZoneInfo('Europe/Madrid')
        monday = datetime(2026, 10, 12, 10, 0, tzinfo=tz)
        tuesday = datetime(2026, 10, 13, 10, 0, tzinfo=tz)
        wednesday = datetime(2026, 10, 14, 10, 0, tzinfo=tz)
        thursday = datetime(2026, 10, 15, 10, 0, tzinfo=tz)
        friday = datetime(2026, 10, 16, 10, 0, tzinfo=tz)
        saturday = datetime(2026, 10, 17, 10, 0, tzinfo=tz)
        sunday = datetime(2026, 10, 18, 10, 0, tzinfo=tz)

        self.assertEqual(weekend_variant(monday), 'summary')
        self.assertEqual(weekend_variant(tuesday), 'upcoming')
        self.assertEqual(weekend_variant(wednesday), 'upcoming')
        self.assertEqual(weekend_variant(thursday), 'upcoming')
        self.assertEqual(weekend_variant(friday), 'live')
        self.assertEqual(weekend_variant(saturday), 'live')
        self.assertEqual(weekend_variant(sunday), 'live')


class WeekendServicesDataTests(TestCase):
    """Pruebas de capa de datos para la pantalla Este finde."""

    def setUp(self):
        cache.clear()
        self.tz = ZoneInfo('Europe/Madrid')
        self.now_friday = datetime(2026, 10, 16, 12, 0, 0, tzinfo=self.tz)

        # Organización principal
        self.club = Club.objects.create(official_name='Club Test Weekend', federation_id='C_TEST_WKND_1')
        self.org = Organization.objects.create(
            slug='test-weekend-club',
            name='Test Weekend Club',
            club=self.club,
            club_team_names={'1': 'Test Weekend Club'},
            is_active=True,
        )

        # Otra organización para pruebas de aislamiento
        self.club_other = Club.objects.create(official_name='Club Test Rival', federation_id='C_TEST_WKND_2')
        self.org_other = Organization.objects.create(
            slug='test-weekend-rival',
            name='Test Weekend Rival',
            club=self.club_other,
            club_team_names={'1': 'Test Weekend Rival'},
            is_active=True,
        )

        self.user = get_user_model().objects.create_user(username='test_weekend_fan', password='secret')
        Membership.objects.create(user=self.user, organization=self.org, is_approved=True)

        self.senior = Category.objects.create(name='Senior Test', is_active=True)
        self.cadete = Category.objects.create(name='Cadete Test', is_active=True)
        self.season = Season.objects.resolve('2026-2027')

        # Equipos propios y rivales
        self.team_senior_a = Team.objects.create(
            name='Test Weekend Club Senior A', category=self.senior, club=self.club,
            federation_id='T_WKND_SA', is_active=True,
        )
        self.team_senior_b = Team.objects.create(
            name='Test Weekend Club Senior B', category=self.senior, club=self.club,
            federation_id='T_WKND_SB', is_active=True,
        )
        self.team_cadete = Team.objects.create(
            name='Test Weekend Club Cadete', category=self.cadete, club=self.club,
            federation_id='T_WKND_CAD', is_active=True,
        )
        self.team_other_org = Team.objects.create(
            name='Test Weekend Rival Team', category=self.senior, club=self.club_other,
            federation_id='T_WKND_OTHER', is_active=True,
        )
        self.team_external = Team.objects.create(
            name='Equipo Externo Test', category=self.senior,
            federation_id='T_WKND_EXT', is_active=True,
        )

        # Ligas
        self.league_senior = League.objects.create(
            name='Liga Senior Test', federation_id='L_WKND_SEN', season=self.season, is_active=True,
        )
        self.league_senior.categories.add(self.senior)

        self.league_cadete = League.objects.create(
            name='Liga Cadete Test', federation_id='L_WKND_CAD', season=self.season, is_active=True,
        )
        self.league_cadete.categories.add(self.cadete)

    def _match(self, home, away, league, dt, status='scheduled', **kwargs):
        return Match.objects.create(
            home_team=home,
            away_team=away,
            league=league,
            match_date=dt,
            status=status,
            **kwargs,
        )

    def _photo(self, org, match=None, categories=None, status='approved', upload_dt=None):
        photo = Image.objects.create(
            title='Foto Test',
            image='photo.jpg',
            uploaded_by=self.user,
            organization=org,
            match=match,
            status=status,
        )
        if categories:
            photo.categories.set(categories)
        if upload_dt:
            # upload_date es auto_now_add, forzamos timestamp si se requiere
            Image.objects.filter(pk=photo.pk).update(upload_date=upload_dt)
            photo.refresh_from_db()
        return photo

    def test_following_rule_followed_teams_overrides_categories(self):
        # Justificación: Protege la regla de negocio crítica: si el usuario sigue equipos
        # concretos en el club, solo se muestran los partidos de esos equipos, ignorando
        # el resto de partidos de su categoría o de otras categorías preferidas.
        pref = CategoryPreference.objects.create(user=self.user, organization=self.org)
        pref.categories.set([self.senior, self.cadete])
        pref.teams.set([self.team_senior_a])  # Sigue exclusivamente Senior A

        # Partidos del fin de semana
        match_senior_a = self._match(
            self.team_senior_a, self.team_external, self.league_senior,
            self.now_friday + timedelta(days=1),
        )
        match_senior_b = self._match(
            self.team_senior_b, self.team_external, self.league_senior,
            self.now_friday + timedelta(days=1),
        )
        match_cadete = self._match(
            self.team_cadete, self.team_external, self.league_cadete,
            self.now_friday + timedelta(days=2),
        )

        overview = weekend_overview(self.user, self.org, now=self.now_friday)

        self.assertIn(match_senior_a, overview['upcoming'])
        self.assertNotIn(match_senior_b, overview['upcoming'])
        self.assertNotIn(match_cadete, overview['upcoming'])
        self.assertEqual(overview['upcoming_count'], 1)

    def test_following_rule_category_fallback_when_no_teams_followed(self):
        # Justificación: Protege la regla de negocio: si el usuario no sigue equipos
        # específicos, se devuelven todos los partidos del club de sus categorías preferidas.
        pref = CategoryPreference.objects.create(user=self.user, organization=self.org)
        pref.categories.set([self.cadete])  # Solo cadete, sin equipos

        match_senior = self._match(
            self.team_senior_a, self.team_external, self.league_senior,
            self.now_friday + timedelta(days=1),
        )
        match_cadete = self._match(
            self.team_cadete, self.team_external, self.league_cadete,
            self.now_friday + timedelta(days=1),
        )

        overview = weekend_overview(self.user, self.org, now=self.now_friday)

        self.assertIn(match_cadete, overview['upcoming'])
        self.assertNotIn(match_senior, overview['upcoming'])

    def test_upcoming_matches_widens_to_7_days_when_weekend_empty(self):
        # Justificación: Protege la regla de negocio de fallback temporal:
        # si no hay partidos programados el fin de semana, busca en los próximos 7 días.
        pref = CategoryPreference.objects.create(user=self.user, organization=self.org)
        pref.teams.set([self.team_senior_a])

        # Miércoles siguiente (fuera del fin de semana actual, pero dentro de los 7 días desde el viernes)
        midweek_date = self.now_friday + timedelta(days=5)  # Miércoles siguiente
        midweek_match = self._match(
            self.team_senior_a, self.team_external, self.league_senior, midweek_date,
        )

        upcoming = list(upcoming_matches(self.user, self.org, now=self.now_friday))

        self.assertEqual(upcoming, [midweek_match])

    def test_tenant_isolation_matches_and_photos_never_leak(self):
        # Justificación: Protege el aislamiento multi-tenant estricto: ni partidos
        # ni fotos de otra organización deben filtrarse en la vista de Sant Josep.
        # Usuario con membresía y preferencias en ambas organizaciones
        Membership.objects.create(user=self.user, organization=self.org_other, is_approved=True)

        pref_ours = CategoryPreference.objects.create(user=self.user, organization=self.org)
        pref_ours.categories.set([self.senior])

        pref_other = CategoryPreference.objects.create(user=self.user, organization=self.org_other)
        pref_other.categories.set([self.senior])

        # Partido de la otra organización
        other_match = self._match(
            self.team_other_org, self.team_external, self.league_senior,
            self.now_friday + timedelta(days=1),
        )
        # Foto de la otra organización
        other_photo = self._photo(self.org_other, match=other_match, categories=[self.senior])

        overview = weekend_overview(self.user, self.org, now=self.now_friday)

        self.assertNotIn(other_match, overview['upcoming'])
        self.assertNotIn(other_photo, overview['photos'])

    def test_recent_results_window_and_ordering(self):
        # Justificación: Protege la ventana de 7 días y orden descendente de partidos terminados.
        pref = CategoryPreference.objects.create(user=self.user, organization=self.org)
        pref.teams.set([self.team_senior_a])

        r1 = self._match(
            self.team_senior_a, self.team_external, self.league_senior,
            self.now_friday - timedelta(days=1), status='finished', home_score=3, away_score=0,
        )
        r2 = self._match(
            self.team_senior_a, self.team_external, self.league_senior,
            self.now_friday - timedelta(days=3), status='finished', home_score=3, away_score=1,
        )
        # Partido viejo (> 7 días)
        self._match(
            self.team_senior_a, self.team_external, self.league_senior,
            self.now_friday - timedelta(days=10), status='finished', home_score=3, away_score=2,
        )
        # Partido no finalizado
        self._match(
            self.team_senior_a, self.team_external, self.league_senior,
            self.now_friday - timedelta(days=2), status='scheduled',
        )

        results = list(recent_results(self.user, self.org, now=self.now_friday))

        self.assertEqual(results, [r1, r2])

    def test_recent_photos_prioritizes_relevant_and_fills_with_club_photos(self):
        # Justificación: Protege la regla de ordenación y moderación de fotos:
        # primero las fotos de los equipos seguidos y luego relleno con fotos aprobadas del club.
        pref = CategoryPreference.objects.create(user=self.user, organization=self.org)
        pref.teams.set([self.team_senior_a])

        match_a = self._match(
            self.team_senior_a, self.team_external, self.league_senior, self.now_friday,
        )
        match_b = self._match(
            self.team_senior_b, self.team_external, self.league_senior, self.now_friday,
        )

        photo_relevant = self._photo(self.org, match=match_a, status='approved')
        photo_filler = self._photo(self.org, match=match_b, status='approved')
        photo_unapproved = self._photo(self.org, match=match_a, status='pending')

        photos = recent_photos(self.user, self.org, limit=6)

        self.assertEqual(photos[0], photo_relevant)
        self.assertIn(photo_filler, photos)
        self.assertNotIn(photo_unapproved, photos)

    def test_weekend_overview_degrades_summary_to_upcoming_when_no_results(self):
        # Justificación: Protege la degradación de variante en lunes si no hubo partidos
        # finalizados que resumir, asegurando que se presente la previa en lugar de un resumen vacío.
        monday = datetime(2026, 10, 19, 10, 0, tzinfo=self.tz)
        pref = CategoryPreference.objects.create(user=self.user, organization=self.org)
        pref.teams.set([self.team_senior_a])

        # Próximo partido para el fin de semana siguiente
        next_match = self._match(
            self.team_senior_a, self.team_external, self.league_senior,
            datetime(2026, 10, 24, 18, 0, tzinfo=self.tz),
        )

        overview = weekend_overview(self.user, self.org, now=monday)

        self.assertEqual(overview['variant'], 'upcoming')
        self.assertTrue(overview['has_content'])
        self.assertIn(next_match, overview['upcoming'])

    def test_weekend_overview_has_content_ignores_filler_photos(self):
        # Justificación: Protege la regla de negocio de has_content: las fotos de relleno
        # del club no activan has_content si no hay partidos ni fotos relevantes del usuario.
        pref = CategoryPreference.objects.create(user=self.user, organization=self.org)
        pref.teams.set([self.team_senior_a])

        # Foto del club de otro equipo (relleno)
        match_b = self._match(
            self.team_senior_b, self.team_external, self.league_senior, self.now_friday,
        )
        self._photo(self.org, match=match_b, status='approved')

        overview = weekend_overview(self.user, self.org, now=self.now_friday)

        # La foto aparece en photos, pero has_content es False porque es puro relleno
        self.assertEqual(len(overview['photos']), 1)
        self.assertFalse(overview['has_content'])

    def test_weekend_entry_returns_none_without_follow_preferences(self):
        # Justificación: Protege el contrato ligero para la UI de navegación:
        # si el usuario no tiene preferencias en el club, weekend_entry debe ser None.
        entry = weekend_entry(self.user, self.org, now=self.now_friday)
        self.assertIsNone(entry)

    def test_weekend_entry_fast_counts_with_preferences(self):
        # Justificación: Protege el payload ligero de weekend_entry cuando hay contenido.
        pref = CategoryPreference.objects.create(user=self.user, organization=self.org)
        pref.teams.set([self.team_senior_a])

        self._match(
            self.team_senior_a, self.team_external, self.league_senior,
            self.now_friday + timedelta(days=1),
        )

        entry = weekend_entry(self.user, self.org, now=self.now_friday)

        self.assertIsNotNone(entry)
        self.assertTrue(entry['has_content'])
        self.assertEqual(entry['upcoming_count'], 1)
        self.assertEqual(entry['variant'], 'live')
