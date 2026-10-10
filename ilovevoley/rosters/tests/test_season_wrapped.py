import tempfile
from io import BytesIO

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from PIL import Image as PILImage

from ilovevoley.competitions.models import League, Match
from ilovevoley.content.models import Image, ImageFavorite
from ilovevoley.rosters.models import Person, SeasonWrapped
from ilovevoley.rosters.season_wrapped import (
    OFFICIAL_CAPTION,
    Screen,
    build_screens,
    build_wrapped_stats,
)
from ilovevoley.rosters.tests.test_player_card import PlayerCardTestBase, _lineup
from ilovevoley.rosters.wrapped_render import render_wrapped_screen


class WrappedTestBase(PlayerCardTestBase):
    """Partidos oficiales (con federation_id) para los tests del Wrapped; sin tests propios."""

    def play_official(self, sets):
        match = self.play(sets)
        Match.objects.filter(pk=match.pk).update(federation_id=f'FED-{match.pk}')
        return match


class WrappedStatsTests(WrappedTestBase):
    def test_solo_cuentan_partidos_oficiales_ganados_y_sets(self):
        self.play_official([(25, 20, _lineup())] * 3)      # ganado, 3 sets
        self.play_official([(20, 25, _lineup())] * 3)      # perdido, 3 sets
        self.play([(25, 10, _lineup())] * 3)               # sin federation_id: amistoso/no oficial

        stats = build_wrapped_stats(self.person, self.season)

        self.assertEqual((stats['matches'], stats['sets'], stats['wins']), (2, 6, 1))
        self.assertEqual(stats['rival'], {'name': self.rival.name, 'matches': 2, 'team_id': self.rival.id})

    def test_partido_de_playa_no_suma_al_wrapped_indoor(self):
        match = self.play_official([(25, 20, _lineup())] * 3)
        League.objects.filter(pk=match.league_id).update(modality=League.MODALITY_BEACH)

        self.assertIsNone(build_wrapped_stats(self.person, self.season))
        self.assertEqual(
            build_wrapped_stats(self.person, self.season, League.MODALITY_BEACH)['matches'], 1,
        )

    def test_sin_actas_ni_fotos_no_hay_wrapped(self):
        self.assertIsNone(build_wrapped_stats(self.person, self.season))


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class WrappedScreensTests(WrappedTestBase):
    def snapshot(self):
        stats = build_wrapped_stats(self.person, self.season)
        return SeasonWrapped.objects.create(person=self.person, season=self.season, stats=stats)

    def top_photo(self):
        user = get_user_model().objects.create_user(username='fan', password='x')
        buffer = BytesIO()
        PILImage.new('RGB', (40, 40)).save(buffer, 'JPEG')
        image = Image.objects.create(
            image=SimpleUploadedFile('remate.jpg', buffer.getvalue(), content_type='image/jpeg'),
            title='Remate', status='approved', organization=self.org,
            season=self.season, uploaded_by=user,
        )
        image.persons.add(self.person)
        ImageFavorite.objects.create(image=image, user=user)
        return image

    def test_cifras_de_actas_llevan_la_etiqueta_oficial_y_sin_acta_se_omiten(self):
        self.top_photo()
        wrapped = self.snapshot()
        kinds = [s.kind for s in build_screens(wrapped, self.person.user or get_user_model()(), self.org)]
        self.assertNotIn('matches', kinds)  # sin actas, solo portada/fotos/cierre

        self.play_official([(25, 20, _lineup())] * 3)
        wrapped.stats = build_wrapped_stats(self.person, self.season)
        screens = build_screens(wrapped, get_user_model()(), self.org)
        official = [s for s in screens if s.kind in ('matches', 'sets', 'wins', 'rival')]
        self.assertTrue(official)
        self.assertTrue(all(s.caption == OFFICIAL_CAPTION() for s in official))

    def test_foto_mas_votada_desaparece_si_se_retira_el_consentimiento(self):
        image = self.top_photo()
        self.person.image_consent = Person.ImageConsent.FULL_PUBLIC
        self.person.save()
        wrapped = self.snapshot()
        anonymous = get_user_model()()

        shown = [s for s in build_screens(wrapped, anonymous, self.org) if s.kind == 'top_photo']
        self.assertEqual([s.photo_id for s in shown], [image.id])

        self.person.image_consent = Person.ImageConsent.NONE
        self.person.save()
        self.assertEqual([s for s in build_screens(wrapped, anonymous, self.org) if s.kind == 'top_photo'], [])


class WrappedRenderTests(PlayerCardTestBase):
    def test_render_aguanta_nombre_de_rival_larguisimo_y_foto_ausente(self):
        for screen in (
            Screen('rival', 'Tu rival más repetido', 'Club Voleibol ' * 12, '9 partidos', 'Partidos oficiales'),
            Screen('top_photo', 'Tu foto más votada', photo_id=1),
            Screen('cover', 'Marc Ferrer', '2025-26', 'Tu temporada'),
        ):
            png = render_wrapped_screen(organization=self.org, screen=screen)
            self.assertEqual(PILImage.open(BytesIO(png)).size, (1080, 1920))
