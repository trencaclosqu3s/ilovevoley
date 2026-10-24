import json
from datetime import timedelta

from django.test import TestCase, override_settings
from django.utils import timezone

from ilovevoley.competitions.models import MatchLineup, MatchMark
from ilovevoley.competitions.services.lineups import mark_person_choices
from ilovevoley.rosters.models import Person, PlayerRole
from ilovevoley.teams.tests.helpers import identity_of


class MatchMarkTest(TestCase):
    """Marcas de jugada (#580): el etiquetado depende del acta o, sin ella, de la plantilla."""

    def setUp(self):
        from ilovevoley.competitions.tests.test_live_stream_push import LiveStreamPushTest

        LiveStreamPushTest.setUp(self)
        self.roster_person = Person.objects.create(first_name='Ana', last_name='Ruiz')
        PlayerRole.objects.create(
            person=self.roster_person, identity=identity_of(self.team1),
            season=self.season, jersey_number=7,
        )
        self.acta_person = Person.objects.create(first_name='Bea', last_name='Soler')

    def test_without_acta_choices_are_the_season_roster(self):
        """Sin acta aún se puede etiquetar con la plantilla del club."""
        ids = [c['id'] for c in mark_person_choices(self.match, self.org)]
        self.assertEqual(ids, [self.roster_person.pk])

    def test_with_acta_choices_are_only_the_convocados_of_our_team(self):
        """Con acta resuelta mandan los convocados del acta, no toda la plantilla."""
        MatchLineup.objects.create(
            match=self.match, team=self.team1, person=self.acta_person,
            jersey_number=3, is_convocado=True,
        )
        ids = [c['id'] for c in mark_person_choices(self.match, self.org)]
        self.assertEqual(ids, [self.acta_person.pk])

    @override_settings(SCOREBOARD_STREAM_TOKEN='s3cret', ALLOWED_HOSTS=['santjust.ilovevoley.es'])
    def test_api_saves_mark_for_the_live_match(self):
        """El marcador guarda el segundo y el estado del instante; no se acepta un segundo absurdo."""
        def post(payload):
            return self.client.post(
                '/competitions/api/match/mark/', json.dumps(payload),
                content_type='application/json', HTTP_HOST='santjust.ilovevoley.es',
                HTTP_AUTHORIZATION='Bearer s3cret',
            )

        self.match.match_date = timezone.now() - timedelta(minutes=10)
        self.match.save(update_fields=['match_date'])
        self.assertEqual(post({'seconds': 125}).status_code, 200)
        self.assertEqual(MatchMark.objects.get(match=self.match).seconds, 125)
        self.assertEqual(post({'seconds': 10**9}).status_code, 400)

    @override_settings(ALLOWED_HOSTS=['santjust.ilovevoley.es'])
    def test_tagging_ignores_persons_outside_the_choices(self):
        from django.contrib.auth import get_user_model

        from ilovevoley.users.models import Membership

        user = get_user_model().objects.create_user(username='mgr', email='m@x.es', password='x')
        Membership.objects.create(user=user, organization=self.org, role='manager', is_approved=True)
        self.client.force_login(user)
        mark = MatchMark.objects.create(match=self.match, seconds=65)
        stranger = Person.objects.create(first_name='Otra', last_name='Persona')

        response = self.client.post(
            f'/competitions/partidos/{self.match.pk}/jugadas/{mark.pk}/jugadores/',
            {'persons': [self.roster_person.pk, stranger.pk]},
            HTTP_HOST='santjust.ilovevoley.es',
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(list(mark.persons.all()), [self.roster_person])
        page = self.client.get(f'/competitions/partidos/{self.match.pk}/', HTTP_HOST='santjust.ilovevoley.es')
        self.assertContains(page, '1:05')

    @override_settings(ALLOWED_HOSTS=['santjust.ilovevoley.es'])
    def test_video_detail_links_marks_to_its_own_video(self):
        """El enlace &t= se arma siempre sobre watch?v=: en youtu.be el parámetro pegado al path no vale."""
        from django.contrib.auth import get_user_model

        from ilovevoley.content.models import Video
        from ilovevoley.users.models import Membership

        user = get_user_model().objects.create_user(username='mem', email='mem@x.es', password='x')
        Membership.objects.create(user=user, organization=self.org, role='member', is_approved=True)
        self.client.force_login(user)
        video = Video.objects.create(
            title='Partido', youtube_url='https://youtu.be/abc123',
            match=self.match, organization=self.org, created_by=user,
        )
        MatchMark.objects.create(match=self.match, seconds=125)

        page = self.client.get(f'/content/{video.pk}/', HTTP_HOST='santjust.ilovevoley.es')

        self.assertContains(page, 'https://www.youtube.com/watch?v=abc123&amp;t=125s')


@override_settings(ALLOWED_HOSTS=['santjust.ilovevoley.es', 'otro.ilovevoley.es'], PROTECTED_MEDIA_USE_X_ACCEL=True)
class MatchMarkClipTest(TestCase):
    """Clips 9:16 de las jugadas (#629): emparejado por partido y segundo, y mismo acceso que el detalle."""

    def setUp(self):
        import tempfile
        from pathlib import Path

        from django.contrib.auth import get_user_model

        from ilovevoley.competitions.tests.test_live_stream_push import LiveStreamPushTest
        from ilovevoley.users.models import Membership

        LiveStreamPushTest.setUp(self)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.clips = Path(tmp.name)
        clips_settings = override_settings(SCOREBOARD_CLIPS_DIR=tmp.name)
        clips_settings.enable()
        self.addCleanup(clips_settings.disable)
        self.mark = MatchMark.objects.create(match=self.match, seconds=125)
        self.user = get_user_model().objects.create_user(username='mem', email='mem@x.es', password='x')
        Membership.objects.create(user=self.user, organization=self.org, role='member', is_approved=True)

    def _clip(self, name):
        (self.clips / name).write_bytes(b'mp4')

    def test_mark_only_pairs_with_the_clip_of_its_match_and_second(self):
        """Un clip de otro partido o de otro segundo no se cuela en la marca."""
        from ilovevoley.competitions.services.marks import match_marks

        self._clip(f'm{self.match.pk + 1}_125.mp4')
        self._clip(f'm{self.match.pk}_126.mp4')
        self.assertFalse(match_marks(self.match)[0].has_clip)

        self._clip(f'm{self.match.pk}_125.mp4')
        self.assertTrue(match_marks(self.match)[0].has_clip)

    def test_clip_is_served_to_who_sees_the_detail_and_nobody_else(self):
        """Se entrega vía X-Accel a la zona interna; desde otro club, o si el fichero ya caducó, 404."""
        from ilovevoley.core.models import Organization
        from ilovevoley.users.models import Membership

        self.client.force_login(self.user)
        url = f'/competitions/partidos/{self.match.pk}/jugadas/{self.mark.pk}/clip/'
        self.assertEqual(self.client.get(url, HTTP_HOST='santjust.ilovevoley.es').status_code, 404)

        self._clip(f'm{self.match.pk}_125.mp4')
        response = self.client.get(url, HTTP_HOST='santjust.ilovevoley.es')
        self.assertEqual(response['X-Accel-Redirect'], f'/protected-clips/m{self.match.pk}_125.mp4')

        other_org = Organization.objects.create(name='Otro', slug='otro')
        Membership.objects.create(user=self.user, organization=other_org, role='member', is_approved=True)
        self.assertEqual(self.client.get(url, HTTP_HOST='otro.ilovevoley.es').status_code, 404)

    def test_share_link_serves_only_marks_of_its_match(self):
        """El enlace temporal da los clips de su partido; con otra marca o token desconocido, 404."""
        import uuid

        from ilovevoley.competitions.models import Match
        from ilovevoley.competitions.share import create_match_share_link

        self._clip(f'm{self.match.pk}_125.mp4')
        link = create_match_share_link(self.match, self.org, self.user, hours=48)
        other = Match.objects.create(
            league=self.league, home_team=self.team2, away_team=self.team1, match_date=self.match.match_date,
        )
        other_mark = MatchMark.objects.create(match=other, seconds=125)
        self._clip(f'm{other.pk}_125.mp4')

        ok = self.client.get(f'/p/partido/{link.token}/jugadas/{self.mark.pk}/clip/', HTTP_HOST='santjust.ilovevoley.es')
        self.assertEqual(ok['X-Accel-Redirect'], f'/protected-clips/m{self.match.pk}_125.mp4')
        page = self.client.get(f'/p/partido/{link.token}/', HTTP_HOST='santjust.ilovevoley.es')
        self.assertContains(page, f'/p/partido/{link.token}/jugadas/{self.mark.pk}/clip/')
        for path in (f'/p/partido/{link.token}/jugadas/{other_mark.pk}/clip/',
                     f'/p/partido/{uuid.uuid4()}/jugadas/{self.mark.pk}/clip/'):
            self.assertEqual(self.client.get(path, HTTP_HOST='santjust.ilovevoley.es').status_code, 404)
