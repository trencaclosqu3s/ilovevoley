from datetime import datetime, timedelta, timezone as dt_timezone
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from ilovevoley.competitions.models import League, Match, MatchChangeLog, Venue
from ilovevoley.core.models import Organization, Season
from ilovevoley.teams.models import Club, Team

User = get_user_model()


class LeagueForTenantTest(TestCase):
    """for_tenant acota las ligas visibles a las del club del tenant."""

    @classmethod
    def setUpTestData(cls):
        cls.club = Club.objects.create(federation_id='c-1', official_name='CV SANT JOSEP')
        cls.own_team = Team.objects.create(name='SANT JOSEP', federation_id='t-1', club=cls.club)
        cls.other_team = Team.objects.create(name='CV ALTRES', federation_id='t-2')

        cls.own_league = League.objects.create(
            name='Lliga pròpia', federation_id='l-1',
            visibility_type='main', is_our_team_related=True, is_active=True,
        )
        cls.other_league = League.objects.create(
            name='Lliga aliena', federation_id='l-2',
            visibility_type='main', is_our_team_related=True, is_active=True,
        )
        Match.objects.create(league=cls.own_league, home_team=cls.own_team, match_date=timezone.now())
        Match.objects.create(league=cls.other_league, home_team=cls.other_team, match_date=timezone.now())

        cls.org_with_club = Organization.objects.create(
            slug='test-with-club', name='Amb club', club=cls.club, club_team_names={'Senior': 'SANT JOSEP'},
        )
        cls.org_without_club = Organization.objects.create(
            slug='test-without-club', name='Sense club', club=None, club_team_names={'Senior': 'BALEARS'},
        )

    def test_tenant_with_club_only_sees_own_leagues(self):
        leagues = League.objects.for_tenant(self.org_with_club)
        self.assertQuerySetEqual(leagues, [self.own_league])

    def test_tenant_without_club_keeps_global_behaviour(self):
        leagues = League.objects.for_tenant(self.org_without_club)
        self.assertQuerySetEqual(leagues, [self.own_league, self.other_league], ordered=False)


class MatchChangeLogTest(TestCase):
    """Pruebas unitarias del modelo MatchChangeLog y su queryset multi-tenant."""

    @classmethod
    def setUpTestData(cls):
        cls.club = Club.objects.create(federation_id='club-1', official_name='CV SANT JOSEP')
        cls.other_club = Club.objects.create(federation_id='club-2', official_name='CV MANACOR')

        cls.team_a = Team.objects.create(name='SANT JOSEP A', federation_id='team-1', club=cls.club)
        cls.team_b = Team.objects.create(name='MANACOR B', federation_id='team-2', club=cls.other_club)
        cls.team_c = Team.objects.create(name='INCA C', federation_id='team-3')

        cls.league = League.objects.create(
            name='1a Balear', federation_id='l-balear',
            visibility_type='main', is_our_team_related=True, is_active=True,
        )
        cls.match_own = Match.objects.create(
            league=cls.league, home_team=cls.team_a, away_team=cls.team_b, match_date=timezone.now()
        )
        cls.match_other = Match.objects.create(
            league=cls.league, home_team=cls.team_b, away_team=cls.team_c, match_date=timezone.now()
        )

        cls.org_with_club = Organization.objects.create(
            slug='sant-josep', name='Sant Josep Org', club=cls.club,
            club_team_names={'Senior': 'SANT JOSEP A'},
        )
        cls.org_without_club = Organization.objects.create(
            slug='fvb', name='Federació Org', club=None,
            club_team_names={'Senior': 'BALEARS'},
        )

        cls.user = User.objects.create_user(username='admin_director', email='director@test.com')

    def test_for_tenant_filters_by_club_matches(self):
        log_own = MatchChangeLog.objects.create(
            match=self.match_own,
            change_type='venue',
            field_name='venue',
            old_value='Pista 1',
            new_value='Pista 2',
        )
        log_other = MatchChangeLog.objects.create(
            match=self.match_other,
            change_type='venue',
            field_name='venue',
            old_value='Pabellón A',
            new_value='Pabellón B',
        )

        # Tenant con club solo ve los logs de partidos de su club
        logs_tenant = MatchChangeLog.objects.for_tenant(self.org_with_club)
        self.assertQuerySetEqual(logs_tenant, [log_own])

        # Tenant sin club no ve ningún log (antes filtraba el panel global: #200)
        logs_without_club = MatchChangeLog.objects.for_tenant(self.org_without_club)
        self.assertQuerySetEqual(logs_without_club, [])

        # Tenant None devuelve none
        self.assertQuerySetEqual(MatchChangeLog.objects.for_tenant(None), [])


class VenueModelTest(TestCase):
    def test_venue_full_address_composes_name_address_and_city(self):
        venue = Venue.objects.create(
            name="Pavelló Test Joan Pericás Riera",
            city="Bunyola",
            address="Son Serra s/n",
            google_maps_url="https://maps.app.goo.gl/sample123",
            aliases="Pav. Juan Pericas Riera, Pav. Bunyola"
        )
        self.assertEqual(venue.full_address, "Pavelló Test Joan Pericás Riera, Son Serra s/n, Bunyola")

    def test_venue_full_address_avoids_duplicate_fragments(self):
        venue = Venue.objects.create(
            name="Poliesportiu Test Germans Escalas",
            address="Test Germans Escalas, Mare de Deu de Monserrat 66",
            city="Palma"
        )
        # No debe duplicar "Test Germans Escalas"
        self.assertIn("Mare de Deu de Monserrat 66", venue.full_address)
        self.assertEqual(venue.full_address.count("Test Germans Escalas"), 1)

    def test_venue_maps_url_fallback_when_empty(self):
        venue = Venue.objects.create(
            name="Pavelló Municipal Test Alaró",
            city="Alaró"
        )
        self.assertIn("https://www.google.com/maps/search/?api=1&query=", venue.maps_url)
        self.assertIn("Alar%C3%B3", venue.maps_url)

    def test_venue_maps_url_with_coordinates_prioritizes_coords_over_address(self):
        venue = Venue.objects.create(
            name="Pavelló Test Coordenadas",
            city="Algaida",
            latitude=Decimal("39.564230"),
            longitude=Decimal("2.895819"),
        )
        self.assertEqual(venue.maps_url, "https://www.google.com/maps/search/?api=1&query=39.564230,2.895819")

    def test_venue_matches_text(self):
        venue = Venue.objects.create(
            name="Pav. Test Son Angelats",
            city="Sóller",
            aliases="Poliesportiu Test Son Angelats, Pavelló Test Sóller"
        )
        self.assertTrue(venue.matches_text("Pav. Test Son Angelats"))
        self.assertTrue(venue.matches_text("Poliesportiu Test Son Angelats"))
        self.assertTrue(venue.matches_text("pav. test son angelats"))
        self.assertFalse(venue.matches_text("Pav. Germans Escalas"))



class MatchManagerTests(TestCase):
    """El manager por defecto oculta los partidos retirados. Regla no evidente."""

    @classmethod
    def setUpTestData(cls):
        cls.league = League.objects.create(
            name='Liga', federation_id='LIG-M', season=Season.objects.resolve('2024-25'),
        )
        cls.a = Team.objects.create(name='A', federation_id='T-A')
        cls.b = Team.objects.create(name='B', federation_id='T-B')
        cls.jugado = Match.objects.create(
            league=cls.league, home_team=cls.a, away_team=cls.b,
            match_date=datetime(2024, 11, 3, 12, 0, tzinfo=dt_timezone.utc),
            status='finished', federation_id='M-OK',
        )
        cls.retirado = Match.objects.create(
            league=cls.league, home_team=cls.a, away_team=cls.b,
            match_date=datetime(2024, 11, 10, 12, 0, tzinfo=dt_timezone.utc),
            status='withdrawn', federation_id='M-W',
        )

    def test_manager_por_defecto_oculta_los_retirados(self):
        self.assertEqual(list(Match.objects.all()), [self.jugado])

    def test_all_objects_incluye_los_retirados(self):
        self.assertEqual(Match.all_objects.count(), 2)


class LeagueManagerTests(TestCase):
    """visible_in_app() exige tres condiciones a la vez, no una."""

    @classmethod
    def setUpTestData(cls):
        cls.principal = League.objects.create(
            name='Principal', federation_id='L-M', season=Season.objects.resolve('2024-25'),
            is_active=True, visibility_type='main', is_our_team_related=True,
        )
        cls.inactiva = League.objects.create(
            name='Inactiva', federation_id='L-I', season=Season.objects.resolve('2024-25'),
            is_active=False, visibility_type='main', is_our_team_related=True,
        )
        cls.ajena = League.objects.create(
            name='Ajena', federation_id='L-E', season=Season.objects.resolve('2024-25'),
            is_active=True, visibility_type='external', is_our_team_related=False,
        )
        cls.historica = League.objects.create(
            name='Historica', federation_id='L-H', season=Season.objects.resolve('2019-20'),
            is_active=True, visibility_type='historical', is_historical=True,
        )

    def _nombres(self, queryset):
        return set(queryset.values_list('name', flat=True))

    def test_visible_in_app_solo_devuelve_la_que_cumple_las_tres_condiciones(self):
        self.assertEqual(self._nombres(League.objects.visible_in_app()), {'Principal'})

    def test_reference_leagues_agrupa_los_tres_tipos_no_principales(self):
        self.assertEqual(
            self._nombres(League.objects.reference_leagues()), {'Ajena', 'Historica'}
        )

    def test_historical_leagues_exige_el_flag_ademas_del_tipo(self):
        self.assertEqual(self._nombres(League.objects.historical_leagues()), {'Historica'})

    def test_external_leagues_exige_no_estar_relacionada_con_nuestro_equipo(self):
        self.assertEqual(self._nombres(League.objects.external_leagues()), {'Ajena'})


class LeaguePhaseTests(TestCase):
    """Fases de liga: la recursión sube al padre y agrega sus partidos."""

    @classmethod
    def setUpTestData(cls):
        cls.regular = League.objects.create(
            name='Liga Regular', federation_id='L-R', season=Season.objects.resolve('2024-25'),
        )
        cls.oro = League.objects.create(
            name='Liga Regular', federation_id='L-ORO', season=Season.objects.resolve('2024-25'),
            parent_league=cls.regular, phase_name='Liguilla Oro', phase_order=1,
        )
        cls.plata = League.objects.create(
            name='Liga Regular', federation_id='L-PLA', season=Season.objects.resolve('2024-25'),
            parent_league=cls.regular, phase_name='Liguilla Plata', phase_order=2,
        )
        cls.a = Team.objects.create(name='A', federation_id='TP-A')
        cls.b = Team.objects.create(name='B', federation_id='TP-B')
        cls.partido_regular = Match.objects.create(
            league=cls.regular, home_team=cls.a, away_team=cls.b,
            match_date=datetime(2024, 10, 5, 12, 0, tzinfo=dt_timezone.utc),
            federation_id='MP-1',
        )
        cls.partido_oro = Match.objects.create(
            league=cls.oro, home_team=cls.a, away_team=cls.b,
            match_date=datetime(2025, 2, 8, 12, 0, tzinfo=dt_timezone.utc),
            federation_id='MP-2',
        )

    def test_is_phase_distingue_la_liga_raiz_de_sus_fases(self):
        self.assertFalse(self.regular.is_phase)
        self.assertTrue(self.oro.is_phase)

    def test_root_league_sube_hasta_la_raiz_desde_una_fase(self):
        self.assertEqual(self.oro.root_league, self.regular)

    def test_get_all_phases_devuelve_la_raiz_primero_y_luego_las_fases_ordenadas(self):
        self.assertEqual(
            self.regular.get_all_phases(), [self.regular, self.oro, self.plata]
        )

    def test_get_all_phases_desde_una_fase_devuelve_lo_mismo_que_desde_la_raiz(self):
        self.assertEqual(self.oro.get_all_phases(), self.regular.get_all_phases())

    def test_get_combined_matches_agrega_los_partidos_de_todas_las_fases(self):
        self.assertEqual(
            set(self.regular.get_combined_matches()),
            {self.partido_regular, self.partido_oro},
        )

    def test_get_combined_matches_desde_una_fase_agrega_igual(self):
        self.assertEqual(
            set(self.oro.get_combined_matches()),
            {self.partido_regular, self.partido_oro},
        )

    def test_display_name_prioriza_el_override_sobre_el_nombre_de_fase(self):
        self.oro.display_name_override = 'Fase de Oro 24/25'
        self.assertEqual(self.oro.display_name, 'Fase de Oro 24/25')

    def test_display_name_concatena_el_nombre_de_fase_si_no_hay_override(self):
        self.assertEqual(self.oro.display_name, 'Liga Regular - Liguilla Oro')


class MatchCleanTests(TestCase):
    """Validación propia de Match, que no cubre ningún validador de Django."""

    @classmethod
    def setUpTestData(cls):
        cls.league = League.objects.create(
            name='Liga', federation_id='L-C', season=Season.objects.resolve('2024-25'),
        )
        cls.a = Team.objects.create(name='A', federation_id='TC-A')
        cls.b = Team.objects.create(name='B', federation_id='TC-B')

    def test_un_amistoso_no_puede_llevar_federation_id(self):
        partido = Match(
            is_friendly=True,
            federation_id='F-1',
            home_team_text='Equipo invitado',
            away_team_text='Sant Josep',
            match_date=datetime(2024, 12, 1, 12, 0, tzinfo=dt_timezone.utc),
        )
        with self.assertRaises(ValidationError):
            partido.clean()

    def test_un_partido_oficial_ya_guardado_exige_equipo_local(self):
        partido = Match.objects.create(
            league=self.league, home_team=self.a, away_team=self.b,
            match_date=datetime(2024, 12, 1, 12, 0, tzinfo=dt_timezone.utc),
            federation_id='MC-1',
        )
        partido.home_team = None
        with self.assertRaises(ValidationError):
            partido.clean()

    def test_un_partido_oficial_ya_guardado_exige_equipo_visitante(self):
        partido = Match.objects.create(
            league=self.league, home_team=self.a, away_team=self.b,
            match_date=datetime(2024, 12, 1, 12, 0, tzinfo=dt_timezone.utc),
            federation_id='MC-2',
        )
        partido.away_team = None
        with self.assertRaises(ValidationError):
            partido.clean()

    def test_un_partido_oficial_sin_guardar_no_exige_equipos(self):
        # La validación solo aplica si self.pk is not None: durante la creación
        # es el formulario quien valida.
        partido = Match(
            league=self.league,
            match_date=datetime(2024, 12, 1, 12, 0, tzinfo=dt_timezone.utc),
        )
        partido.clean()  # no debe lanzar

    def test_un_amistoso_con_equipos_en_texto_es_valido(self):
        partido = Match(
            is_friendly=True,
            home_team_text='Equipo invitado',
            away_team_text='Sant Josep',
            match_date=datetime(2024, 12, 1, 12, 0, tzinfo=dt_timezone.utc),
        )
        partido.clean()  # no debe lanzar


class MatchStreamUrlTest(TestCase):
    """Reglas de negocio del enlace de retransmisión en directo (issue #359)."""

    @classmethod
    def setUpTestData(cls):
        cls.league = League.objects.create(
            name='Liga', federation_id='L-STR', season=Season.objects.resolve('2024-25'),
        )
        cls.team_a = Team.objects.create(name='A', federation_id='T-STR-A')
        cls.team_b = Team.objects.create(name='B', federation_id='T-STR-B')

    def test_stream_url_accepts_valid_http_and_https(self):
        match = Match(
            league=self.league, home_team=self.team_a, away_team=self.team_b,
            match_date=timezone.now(),
            stream_url='https://www.youtube.com/watch?v=12345',
        )
        match.full_clean()
        self.assertEqual(match.stream_url, 'https://www.youtube.com/watch?v=12345')

    def test_stream_url_rejects_non_http_schemes(self):
        match = Match(
            league=self.league, home_team=self.team_a, away_team=self.team_b,
            match_date=timezone.now(),
            stream_url='javascript:alert(1)',
        )
        with self.assertRaises(ValidationError):
            match.full_clean()

    def test_is_live_window_and_is_live(self):
        now = timezone.now()
        # Partido a 15 minutos en el futuro (dentro de ventana -30 min a +3 h)
        match_live = Match(
            league=self.league, home_team=self.team_a, away_team=self.team_b,
            match_date=now + timedelta(minutes=15),
            status='scheduled',
            stream_url='https://youtube.com/live/xyz',
        )
        self.assertTrue(match_live.is_live_window)
        self.assertTrue(match_live.is_live)

        # Sin stream_url no está en directo
        match_live.stream_url = ''
        self.assertTrue(match_live.is_live_window)
        self.assertFalse(match_live.is_live)

        # Partido finalizado nunca está en ventana de directo
        match_live.stream_url = 'https://youtube.com/live/xyz'
        match_live.status = 'finished'
        self.assertFalse(match_live.is_live_window)
        self.assertFalse(match_live.is_live)

        # Partido fuera de ventana (+4 h en el futuro)
        match_future = Match(
            league=self.league, home_team=self.team_a, away_team=self.team_b,
            match_date=now + timedelta(hours=4),
            status='scheduled',
            stream_url='https://youtube.com/live/xyz',
        )
        self.assertFalse(match_future.is_live_window)
        self.assertFalse(match_future.is_live)

