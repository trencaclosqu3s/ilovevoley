import tempfile
from io import BytesIO
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import translation
from PIL import Image as PILImage

from ilovevoley.competitions.models import League, Match
from ilovevoley.content.models import Image, ImageFavorite
from ilovevoley.core import narrative
from ilovevoley.rosters.models import Person, SeasonWrapped
from ilovevoley.rosters.season_wrapped import (
    OFFICIAL_CAPTION,
    Screen,
    build_screens,
    build_wrapped_facts,
    build_wrapped_stats,
    season_organization,
)
from ilovevoley.rosters.tasks import generate_season_wrappeds_task, redact_pending_wrapped_narratives_task
from ilovevoley.rosters.tests.test_player_card import PlayerCardTestBase, _lineup
from ilovevoley.rosters.wrapped_render import render_wrapped_screen
from ilovevoley.users.models import Membership


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
        # El contrato es no reventar con texto desbordado o foto ausente y
        # devolver un PNG no vacío; el tamaño Story se comprueba una sola vez.
        rendered = {}
        for screen in (
            Screen('rival', 'Tu rival más repetido', 'Club Voleibol ' * 12, '9 partidos', 'Partidos oficiales'),
            Screen('top_photo', 'Tu foto más votada', photo_id=1),
            Screen('cover', 'Marc Ferrer', '2025-26', 'Tu temporada'),
            Screen('narrative', 'Tu temporada en palabras', subtitle='Marc ha jugado muchos partidos. ' * 10),
        ):
            with self.subTest(kind=screen.kind):
                png = render_wrapped_screen(organization=self.org, screen=screen)
                self.assertTrue(png.startswith(b'\x89PNG'))
                self.assertGreater(len(png), 0)
                rendered[screen.kind] = png
        self.assertEqual(PILImage.open(BytesIO(rendered['cover'])).size, (1080, 1920))


class GenerateWrappedsTests(WrappedTestBase):
    def run_task(self):
        with mock.patch('ilovevoley.rosters.tasks.notify_web_push_organization_task.delay') as push, \
                mock.patch('ilovevoley.rosters.tasks.send_notification_email') as email:
            created = generate_season_wrappeds_task(self.season.pk)
        return created, push, email

    def test_relanzar_no_duplica_filas_ni_vuelve_a_notificar(self):
        # Idempotencia del cierre: get_or_create + aviso solo en fila nueva (Foco 4).
        self.play_official([(25, 20, _lineup())] * 3)
        parent = get_user_model().objects.create_user(username='madre', password='x', email='m@x.es')
        parent.children.add(self.person)

        created, push, email = self.run_task()
        self.assertEqual(created, 1)
        self.assertEqual(SeasonWrapped.objects.count(), 1)
        self.assertEqual(push.call_count, 1)   # un push a la familia (el jugador no tiene usuario)
        self.assertEqual(email.call_count, 1)

        created, push, email = self.run_task()
        self.assertEqual(created, 0)
        self.assertEqual(SeasonWrapped.objects.count(), 1)
        push.assert_not_called()
        email.assert_not_called()

    def test_jugador_sin_actas_ni_fotos_no_recibe_wrapped(self):
        # Sin datos no se crea fila ni se avisa (Foco 5).
        created, push, email = self.run_task()
        self.assertEqual(created, 0)
        self.assertFalse(SeasonWrapped.objects.exists())
        push.assert_not_called()

    def test_generar_sin_notificar_crea_filas_y_no_envia_push_ni_email(self):
        # #506: `notify=False` y `no_notify=True` son la misma rama
        # (`should_notify = notify and not no_notify`): generan el Wrapped pero
        # suprimen push y email para pruebas.
        self.play_official([(25, 20, _lineup())] * 3)
        parent = get_user_model().objects.create_user(username='madre_no_notify', password='x', email='m@x.es')
        parent.children.add(self.person)

        for kwargs in ({'notify': False}, {'no_notify': True}):
            with self.subTest(kwargs=kwargs):
                SeasonWrapped.objects.all().delete()
                with mock.patch('ilovevoley.rosters.tasks.notify_web_push_organization_task.delay') as push, \
                        mock.patch('ilovevoley.rosters.tasks.send_notification_email') as email:
                    created = generate_season_wrappeds_task(self.season.pk, **kwargs)

                self.assertEqual(created, 1)
                self.assertEqual(SeasonWrapped.objects.count(), 1)
                push.assert_not_called()
                email.assert_not_called()




@override_settings(ALLOWED_HOSTS=['testclub.ilovevoley.es', 'localhost'], MEDIA_ROOT=tempfile.mkdtemp())
class WrappedViewTests(WrappedTestBase):
    HOST = 'testclub.ilovevoley.es'

    def setUp(self):
        super().setUp()
        self.play_official([(25, 20, _lineup())] * 3)
        SeasonWrapped.objects.create(
            person=self.person, season=self.season, stats=build_wrapped_stats(self.person, self.season),
        )
        self.page = reverse('rosters:season_wrapped_page', args=[self.person.id])

    def login(self, username, parent=False):
        user = get_user_model().objects.create_user(username=username, password='x')
        Membership.objects.create(user=user, organization=self.org, is_approved=True)
        if parent:
            user.children.add(self.person)
        self.client.force_login(user)
        return user

    def test_padre_ve_el_visor_y_un_png(self):
        # Permisos de menor + PNG Story legible (Foco 3/5: familia ve el visor).
        self.login('padre', parent=True)
        self.assertEqual(self.client.get(self.page, HTTP_HOST=self.HOST).status_code, 200)
        png = self.client.get(reverse('rosters:season_wrapped_png', args=[self.person.id, 0]), HTTP_HOST=self.HOST)
        self.assertTrue(png.content.startswith(b'\x89PNG'))

    def test_otro_socio_no_puede_verlo(self):
        # Solo familia, jugador o gestores (Foco permisos).
        self.login('socio')
        self.assertEqual(self.client.get(self.page, HTTP_HOST=self.HOST).status_code, 403)

    def test_sin_fila_para_la_temporada_da_404(self):
        # Sin SeasonWrapped no hay visor (Foco 5).
        self.login('padre', parent=True)
        SeasonWrapped.objects.all().delete()
        self.assertEqual(self.client.get(self.page, HTTP_HOST=self.HOST).status_code, 404)

    def test_png_de_pantalla_inexistente_da_404(self):
        self.login('padre', parent=True)
        url = reverse('rosters:season_wrapped_png', args=[self.person.id, 99])
        self.assertEqual(self.client.get(url, HTTP_HOST=self.HOST).status_code, 404)


class WrappedOrganizationTests(WrappedTestBase):
    def test_cada_temporada_se_ve_con_el_club_donde_jugo(self):
        # Marc jugó en Sant Josep un curso y en otro club al siguiente: cada Wrapped, con su club.
        from ilovevoley.core.models import Category, Organization, Season
        from ilovevoley.rosters.models import PlayerRole
        from ilovevoley.teams.models import Club, Team
        from ilovevoley.teams.tests.helpers import identity_of

        other_club = Club.objects.create(official_name='Otro Club', federation_id='CLUB-O')
        other_org = Organization.objects.create(
            slug='otroclub', name='Otro Club', club=other_club, club_team_names={'1': 'Otro Club'}, is_active=True,
        )
        other_team = Team.objects.create(
            name='Otro Club Cadete', category=Category.objects.first(), club=other_club,
            federation_id='TEAM-O', is_active=True,
        )
        next_season = Season.objects.resolve('2026-27')
        PlayerRole.objects.create(
            person=self.person, identity=identity_of(other_team), season=next_season,
            jersey_number=5, position='setter', is_active=True,
        )

        self.assertEqual(season_organization(self.person, self.season), self.org)
        self.assertEqual(season_organization(self.person, next_season), other_org)
        self.assertIsNone(season_organization(self.person, Season.objects.resolve('2019-20')))


class NarrativeTestBase(WrappedTestBase):
    """Redacción con LLM (#551): un Wrapped con cifras y, si se pide, narrativa ya guardada."""

    def wrapped_with(self, narrative_stats=None):
        self.play_official([(25, 20, _lineup())] * 3)
        stats = build_wrapped_stats(self.person, self.season)
        if narrative_stats is not None:
            stats['narrative'] = narrative_stats
        return SeasonWrapped.objects.create(person=self.person, season=self.season, stats=stats)

    def screens(self, wrapped):
        return build_screens(wrapped, get_user_model()(), self.org)


class WrappedNarrativeTests(NarrativeTestBase):
    """Pantalla con respaldo y hechos seudonimizados."""

    def test_pantalla_va_tras_la_portada_con_el_nombre_y_respeta_el_idioma(self):
        wrapped = self.wrapped_with({'es': '{nombre} ha jugado 1 partido.', 'ca': '{nombre} ha jugat 1 partit.'})
        for language, expected in (('es', 'Marc ha jugado 1 partido.'), ('ca', 'Marc ha jugat 1 partit.')):
            with self.subTest(language), translation.override(language):
                screens = self.screens(wrapped)
                self.assertEqual([s.kind for s in screens][:2], ['cover', 'narrative'])
                self.assertEqual(screens[1].subtitle, expected)

    def test_sin_texto_en_el_idioma_cae_al_idioma_por_defecto_y_sin_ninguno_no_hay_pantalla(self):
        solo_es = self.wrapped_with({'es': '{nombre} ha jugado.', 'ca': None})
        with translation.override('ca'):
            self.assertEqual(self.screens(solo_es)[1].subtitle, 'Marc ha jugado.')
        solo_es.stats['narrative'] = {'es': None, 'ca': None}
        self.assertNotIn('narrative', [s.kind for s in self.screens(solo_es)])
        del solo_es.stats['narrative']
        self.assertNotIn('narrative', [s.kind for s in self.screens(solo_es)])

    def test_hechos_enviados_no_llevan_datos_personales(self):
        wrapped = self.wrapped_with()
        facts = build_wrapped_facts(wrapped)
        sent = ' '.join(f'{key} {value}' for key, value in facts.items())
        for forbidden in (self.person.first_name, self.person.last_name, str(self.person.birth_year)):
            self.assertNotIn(forbidden, sent)
        self.assertNotIn(self.person.id, facts.values())
        self.assertEqual((facts['partidos_jugados'], facts['sets_disputados'], facts['victorias']), (1, 3, 1))
        self.assertEqual(facts['rival_mas_repetido'], self.rival.name)


@override_settings(LLM_NARRATIVE_ENABLED=True, LLM_NARRATIVE_API_KEY='k')
class RedactPendingNarrativesTests(NarrativeTestBase):
    def run_task(self, side_effect):
        with mock.patch.object(narrative, 'redact', side_effect=side_effect) as redact:
            saved = redact_pending_wrapped_narratives_task()
        return saved, redact

    def test_guarda_los_dos_idiomas(self):
        wrapped = self.wrapped_with()
        saved, _redact = self.run_task(lambda facts, locale, **kw: f'{{nombre}} {locale}')
        wrapped.refresh_from_db()
        self.assertEqual(saved, 2)
        self.assertEqual(wrapped.stats['narrative'], {'es': '{nombre} es', 'ca': '{nombre} ca'})
        self.assertEqual(wrapped.stats['matches'], 1)  # el resto del snapshot no se toca

    def test_api_caida_no_escribe_nada_y_se_reintenta_la_noche_siguiente(self):
        wrapped = self.wrapped_with()
        saved, redact = self.run_task(narrative.NarrativeTransientError('429'))
        wrapped.refresh_from_db()
        self.assertEqual(saved, 0)
        self.assertNotIn('narrative', wrapped.stats)
        self.assertEqual(redact.call_count, 1)  # corta la tanda al primer fallo
        saved, _redact = self.run_task(lambda facts, locale, **kw: '{nombre}')
        self.assertEqual(saved, 2)

    def test_solo_redacta_el_idioma_que_falta_y_no_reintenta_lo_descartado(self):
        wrapped = self.wrapped_with({'es': '{nombre} ha jugado.'})
        saved, redact = self.run_task(narrative.NarrativeDiscarded('cifras'))
        wrapped.refresh_from_db()
        self.assertEqual([call.kwargs['locale'] for call in redact.call_args_list], ['ca'])
        self.assertEqual(wrapped.stats['narrative'], {'es': '{nombre} ha jugado.', 'ca': None})
        saved, redact = self.run_task(lambda facts, locale, **kw: 'x')
        self.assertEqual((saved, redact.call_count), (0, 0))  # idempotente

    def test_respeta_el_limite_de_textos_por_tanda(self):
        self.wrapped_with()
        with mock.patch.object(narrative, 'redact', return_value='{nombre}') as redact:
            saved = redact_pending_wrapped_narratives_task(limit=1)
        self.assertEqual((saved, redact.call_count), (1, 1))
