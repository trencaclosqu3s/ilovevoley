from datetime import timedelta

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from ilovevoley.competitions.models import League, Match, Standing
from ilovevoley.competitions.services.preview import build_match_preview
from ilovevoley.core.models import Category, Season
from ilovevoley.teams.models import Team


class MatchPreviewTests(TestCase):
    """Previa (#358): reglas de visibilidad, origen de datos y G/P por lado."""

    def setUp(self):
        self.now = timezone.now()
        season = Season.objects.resolve('2026-2027')
        self.category = Category.objects.create(name='Cadete Femenino')
        self.league = League.objects.create(name='Liga', federation_id='L1', season=season)
        self.league.categories.add(self.category)
        self.home = Team.objects.create(name='Local', federation_id='T1')
        self.away = Team.objects.create(name='Visitante', federation_id='T2')
        self.other = Team.objects.create(name='Otro', federation_id='T3')
        self.match = self._match(self.home, self.away, days=3, status='scheduled')
        self.match.federation_club_local_id, self.match.federation_club_away_id = 'C1', 'C2'
        self.match.save()

    def _match(self, home, away, *, days, status='finished', score=(None, None)):
        return Match.objects.create(
            league=self.league, home_team=home, away_team=away, status=status,
            match_date=self.now + timedelta(days=days),
            home_score=score[0], away_score=score[1],
        )

    def test_head_to_head_excludes_withdrawn_and_form_reads_from_each_side(self):
        previous = self._match(self.away, self.home, days=-30, score=(3, 1))
        self._match(self.home, self.away, days=-10, status='withdrawn', score=(3, 0))
        self._match(self.other, self.home, days=-5, score=(0, 3))
        Standing.objects.create(league=self.league, team=self.home, position=2)

        preview = build_match_preview(self.match)

        self.assertEqual(preview['head_to_head'], [previous])
        self.assertEqual(preview['home_position'], 2)
        self.assertIsNone(preview['away_position'])
        # Local: perdió fuera ante el visitante y ganó fuera ante "Otro".
        self.assertEqual(preview['home_form'], [False, True])
        self.assertEqual(preview['away_form'], [True])

    def test_head_to_head_crosses_seasons_by_federation_club_within_category(self):
        last_season = League.objects.create(
            name='Liga 25-26', federation_id='L0', season=Season.objects.resolve('2025-2026'),
        )
        last_season.categories.add(self.category)
        other_category = League.objects.create(name='Juvenil', federation_id='L9')
        other_category.categories.add(Category.objects.create(name='Juvenil Femenino'))
        # Filas de Team distintas de las actuales: el patrocinador cambió el nombre
        # y la federación el id, así que solo los ids de club los relacionan.
        old_away = Team.objects.create(name='Pep Mascaró CMV Portol Rojo', federation_id='T8')
        old_home = Team.objects.create(name='Local 25-26', federation_id='T9')

        def past(league):
            return Match.objects.create(
                league=league, home_team=old_away, away_team=old_home, status='finished',
                match_date=self.now - timedelta(days=300), home_score=3, away_score=2,
                federation_club_local_id='C2', federation_club_away_id='C1',
            )

        same_clubs = past(last_season)
        past(other_category)

        preview = build_match_preview(self.match)

        self.assertEqual(preview['head_to_head'], [same_clubs])

    def test_null_federation_club_ids_do_not_match_unrelated_teams(self):
        # El parser guarda 'None' si la federación envía null en ID_CLUB_*.
        self.match.federation_club_local_id = self.match.federation_club_away_id = 'None'
        self.match.save()
        Match.objects.create(
            league=self.league, home_team=self.other,
            away_team=Team.objects.create(name='Ajeno', federation_id='T7'),
            status='finished', match_date=self.now - timedelta(days=10),
            home_score=3, away_score=0,
            federation_club_local_id='None', federation_club_away_id='None',
        )
        Standing.objects.create(league=self.league, team=self.home, position=1)

        preview = build_match_preview(self.match)

        self.assertEqual(preview['head_to_head'], [])

    def test_hidden_for_finished_match_or_without_data(self):
        self.assertIsNone(build_match_preview(self.match))

        self._match(self.away, self.home, days=-30, score=(3, 1))
        self.match.status = 'finished'
        self.match.home_score, self.match.away_score = 3, 0
        self.assertIsNone(build_match_preview(self.match))

    def test_query_count_does_not_grow_with_history(self):
        for i in range(8):
            self._match(self.home, self.away, days=-(i + 1), score=(3, i % 3))
        with CaptureQueriesContext(connection) as ctx:
            build_match_preview(self.match)
        self.assertLessEqual(len(ctx.captured_queries), 4)
