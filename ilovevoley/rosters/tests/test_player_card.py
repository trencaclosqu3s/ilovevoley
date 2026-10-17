import tempfile
from datetime import timedelta
from io import BytesIO
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone, translation
from PIL import Image as PILImage

from ilovevoley.competitions.models import League, Match
from ilovevoley.content.models import Image
from ilovevoley.competitions.services.lineups import store_match_lineups
from ilovevoley.core import narrative
from ilovevoley.core.models import Category, Organization, Season
from ilovevoley.rosters.models import CardNarrative, Person, PlayerRole
from ilovevoley.rosters.player_card import (
    card_highlight,
    card_narrative_facts,
    card_photo_allowed,
    narrated_highlight,
    pick_profile,
    season_facts,
)
from ilovevoley.rosters.tasks import redact_pending_card_narratives_task
from ilovevoley.teams.models import Club, Team
from ilovevoley.teams.tests.helpers import identity_of
from ilovevoley.users.models import Membership

JERSEY = 7


def _png():
    buffer = BytesIO()
    PILImage.new('RGB', (4, 4)).save(buffer, 'PNG')
    return buffer.getvalue()


def _entry(position, number, sub=None):
    return {'position': position, 'number': number, 'sub': {'number': sub} if sub else None}


def _lineup(with_player=True, sub_for=None):
    """Seis en pista: con ``with_player`` el #7 es titular; con ``sub_for`` entra por ese dorsal."""
    numbers = [JERSEY, 2, 3, 4, 5, 6] if with_player else [1, 2, 3, 4, 5, 6]
    return [
        _entry(pos, n, sub=JERSEY if n == sub_for else None)
        for pos, n in zip(('I', 'II', 'III', 'IV', 'V', 'VI'), numbers)
    ]


class PlayerCardTestBase(TestCase):
    def setUp(self):
        cache.clear()
        self.club = Club.objects.create(official_name='Club Test', federation_id='CLUB-T')
        self.org = Organization.objects.create(
            slug='testclub', name='Test Club', club=self.club,
            club_team_names={'1': 'Test Club'}, is_active=True,
        )
        category = Category.objects.create(name='Cadete', is_active=True)
        self.team = Team.objects.create(
            name='Test Club Cadete', category=category, club=self.club, federation_id='TEAM-1', is_active=True,
        )
        self.rival = Team.objects.create(
            name='Rival Cadete', category=category,
            club=Club.objects.create(official_name='Rival', federation_id='CLUB-R'),
            federation_id='TEAM-2', is_active=True,
        )
        self.season = Season.objects.resolve('2025-26')
        self.league = League.objects.create(
            name='Liga Cadete', federation_id='LEAGUE-T', season=self.season,
            is_active=True, visibility_type='main', is_our_team_related=True,
        )
        self.person = Person.objects.create(first_name='Marc', last_name='Ferrer', birth_year=2011)
        self.person.organizations.add(self.org)
        PlayerRole.objects.create(
            person=self.person, identity=identity_of(self.team), season=self.season,
            jersey_number=JERSEY, position='setter', is_active=True,
        )
        self.round = 0

    def play(self, sets):
        """Partido en casa con acta. ``sets`` = [(nuestros, suyos, alineación), ...]."""
        self.round += 1
        won = sum(ours > theirs for ours, theirs, _ in sets)
        match = Match.objects.create(
            league=self.league, home_team=self.team, away_team=self.rival, round_number=self.round,
            match_date=timezone.now() - timedelta(days=30 - self.round), status='finished',
            home_score=won, away_score=len(sets) - won,
        )
        store_match_lineups(match, {
            'home_team': self.team.name, 'away_team': self.rival.name,
            'home_convocados': [f'{JERSEY} Marc Ferrer'], 'away_convocados': [],
            'sets': [
                {'title': f'Set {i}', 'teams': [
                    {'name': self.team.name, 'points': ours, 'lineup': lineup},
                    {'name': self.rival.name, 'points': theirs, 'lineup': _lineup(False)},
                ]}
                for i, (ours, theirs, lineup) in enumerate(sets, 1)
            ],
        })
        return match

    def highlight(self):
        return card_highlight(self.person, [self.team], self.season)


class PlayerCardProfileTests(PlayerCardTestBase):
    """El perfil tiene que ser cierto: quien lo recibe sabe cuánto ha jugado."""

    def test_lesionado_media_temporada_no_sale_fijo_sino_momento(self):
        # Titular en todo lo que jugó, pero solo 1 de 4 partidos: no es "fijo en el seis".
        self.play([(25, 15, _lineup())] * 3)
        for _ in range(3):
            self.play([(25, 15, _lineup(False))] * 3)

        facts = season_facts(self.person, [self.team], self.season)
        self.assertEqual((facts['starts'], facts['team_sets']), (3, 12))
        self.assertIsNone(pick_profile(facts))
        highlight = self.highlight()
        self.assertEqual(highlight['key'], 'momento')
        self.assertEqual(highlight['title'], 'Victoria 3-0')

    def test_talisman_gana_a_sangre_fria(self):
        # Con él: 15 sets ganados por la mínima. Sin él: el equipo pierde 9.
        for _ in range(5):
            self.play([(25, 23, _lineup())] * 3)
        for _ in range(3):
            self.play([(15, 25, _lineup(False))] * 3)

        self.assertEqual(self.highlight()['key'], 'talisman')

    def test_entrar_de_cambio_cuenta_como_revulsivo_no_como_titular(self):
        for _ in range(5):
            self.play([(25, 18, _lineup(False, sub_for=4))] + [(25, 10, _lineup(False))] * 2)

        facts = season_facts(self.person, [self.team], self.season)
        self.assertEqual((facts['sub_sets'], facts['starts']), (5, 0))
        self.assertEqual(self.highlight()['key'], 'revulsivo')


@override_settings(ALLOWED_HOSTS=['testclub.ilovevoley.es', 'localhost'], MEDIA_ROOT=tempfile.mkdtemp())
class PlayerCardViewTests(PlayerCardTestBase):
    """Es la imagen de un menor para redes: solo la familia, él mismo o los gestores."""

    def setUp(self):
        super().setUp()
        self.url = reverse('rosters:person_card', args=[self.person.id])

    def member(self, username):
        user = get_user_model().objects.create_user(username=username, password='pass')
        Membership.objects.create(user=user, organization=self.org, is_approved=True)
        self.client.force_login(user)
        return user

    def test_padre_descarga_el_cromo_de_su_hijo(self):
        self.play([(25, 20, _lineup())] * 3)
        self.member('padre').children.add(self.person)

        response = self.client.get(self.url, HTTP_HOST='testclub.ilovevoley.es')

        self.assertEqual(response['Content-Type'], 'image/png')
        self.assertTrue(response.content.startswith(b'\x89PNG'))

    def test_otro_socio_del_club_no_puede_generarlo(self):
        self.member('socio')

        response = self.client.get(self.url, HTTP_HOST='testclub.ilovevoley.es')

        self.assertEqual(response.status_code, 403)

    def test_padre_sin_ficha_propia_ve_el_cromo_de_su_hijo_en_tu(self):
        self.member('padre').children.add(self.person)

        response = self.client.get(reverse('rosters:my_profile'), HTTP_HOST='testclub.ilovevoley.es')

        # El hijo aparece en «Tú» con su cromo disponible (has_card), sin
        # depender de que la plantilla pinte un enlace concreto.
        child = response.context['children'][0]
        self.assertEqual(child['person'], self.person)
        self.assertTrue(child['has_card'])

    def test_padre_ve_la_trayectoria_de_su_hijo_tambien_en_otro_club(self):
        # «Tú» es universal: si el hijo jugó el año pasado en otro club, sus padres lo siguen viendo.
        other_child = Person.objects.create(first_name='Pau', last_name='Ferrer', birth_year=2014)
        PlayerRole.objects.create(
            person=other_child, identity=identity_of(self.rival), season=self.season, jersey_number=3, is_active=True,
        )
        self.member('padre').children.add(other_child)

        tu = self.client.get(reverse('rosters:my_profile'), HTTP_HOST='testclub.ilovevoley.es')
        child_url = reverse('rosters:child_profile', args=[other_child.id])
        response = self.client.get(child_url, HTTP_HOST='testclub.ilovevoley.es')

        self.assertContains(tu, child_url)
        self.assertContains(response, self.rival.name)
        self.assertNotContains(response, reverse('rosters:person_detail', args=[other_child.id]))

    def test_la_trayectoria_de_un_menor_que_no_es_tu_hijo_da_404(self):
        self.member('socio')

        response = self.client.get(
            reverse('rosters:child_profile', args=[self.person.id]), HTTP_HOST='testclub.ilovevoley.es',
        )

        self.assertEqual(response.status_code, 404)

    def test_no_se_puede_usar_una_foto_donde_no_esta_etiquetado(self):
        # El id de la foto viene por URL: sin este filtro saldría la foto de otro menor.
        user = self.member('padre')
        user.children.add(self.person)
        other = Image.objects.create(
            image=SimpleUploadedFile('x.png', _png(), content_type='image/png'),
            title='Otro', status='approved', uploaded_by=user, organization=self.org,
        )

        response = self.client.get(f'{self.url}?foto={other.id}', HTTP_HOST='testclub.ilovevoley.es')

        self.assertEqual(response.status_code, 404)


class PlayerCardConsentTests(PlayerCardTestBase):
    """El cromo es para redes: la foto depende del consentimiento y de quién lo genera (#122)."""

    def test_foto_segun_consentimiento_y_quien_genera(self):
        User = get_user_model()
        parent = User.objects.create_user(username='padre')
        parent.children.add(self.person)
        manager = User.objects.create_user(username='gestor')
        consent = Person.ImageConsent
        cases = [
            (consent.FULL_PUBLIC, manager, True),
            (consent.INTERNAL_ONLY, parent, True),
            (consent.INTERNAL_ONLY, manager, False),
            (consent.NONE, parent, False),
        ]
        for value, user, expected in cases:
            with self.subTest(consent=value, user=user.username):
                self.person.image_consent = value
                self.assertIs(card_photo_allowed(user, self.person), expected)


@override_settings(ALLOWED_HOSTS=['testclub.ilovevoley.es', 'localhost'])
class SeasonSummaryTests(PlayerCardTestBase):
    """Cifras en «Tú» (#472): segunda persona para uno mismo, tercera para el hijo, y nada sin actas."""

    def visit(self, name, **kwargs):
        return self.client.get(reverse(name, kwargs=kwargs), HTTP_HOST='testclub.ilovevoley.es')

    def test_tu_habla_en_segunda_persona_y_el_hijo_en_tercera(self):
        self.play([(25, 20, _lineup())] * 3)
        user = get_user_model().objects.create_user(username='jugador', password='pass')
        Membership.objects.create(user=user, organization=self.org, is_approved=True)
        self.client.force_login(user)
        self.person.user = user
        self.person.save()
        self.assertContains(self.visit('rosters:my_profile'), 'Has jugado 1 partido y 3 sets; titular en 1.')

        self.person.user = None
        self.person.save()
        user.children.add(self.person)
        self.assertContains(self.visit('rosters:child_profile', person_id=self.person.id), 'Ha jugado 1 partido')

    def test_rol_sin_actas_no_muestra_cifras_ni_perfil(self):
        user = get_user_model().objects.create_user(username='jugador', password='pass')
        Membership.objects.create(user=user, organization=self.org, is_approved=True)
        self.client.force_login(user)
        self.person.user = user
        self.person.save()

        response = self.visit('rosters:my_profile')

        self.assertNotContains(response, 'Has jugado')
        self.assertNotContains(response, 'Momento')

    def test_pestana_activa_es_la_pedida_o_la_ultima_y_solo_hay_de_temporadas_con_rol(self):
        old = Season.objects.resolve('2024-25')
        PlayerRole.objects.create(
            person=self.person, identity=identity_of(self.team), season=old, jersey_number=JERSEY, is_active=False,
        )
        user = get_user_model().objects.create_user(username='jugador', password='pass')
        Membership.objects.create(user=user, organization=self.org, is_approved=True)
        self.client.force_login(user)
        self.person.user = user
        self.person.save()

        def active(query=''):
            response = self.client.get(reverse('rosters:my_profile') + query, HTTP_HOST='testclub.ilovevoley.es')
            return response.context['active_entry']['season'].name

        self.assertEqual(active(), '2025-26')
        self.assertEqual(active(f'?season={old.pk}'), '2024-25')
        self.assertEqual(active('?season=999999'), '2025-26')
        self.assertEqual(self.visit('rosters:my_profile').context['seasons'].__len__(), 2)

    def test_cifras_de_una_temporada_en_otro_club_salen_entrando_por_este_tenant(self):
        # «Tú» es universal: el rol está en el club rival y el usuario entra por testclub.
        other = Person.objects.create(first_name='Pau', last_name='Ferrer', birth_year=2012)
        PlayerRole.objects.create(
            person=other, identity=identity_of(self.rival), season=self.season, jersey_number=JERSEY, is_active=True,
        )
        match = Match.objects.create(
            league=self.league, home_team=self.rival, away_team=self.team, round_number=1,
            match_date=timezone.now() - timedelta(days=5), status='finished', home_score=3, away_score=0,
        )
        store_match_lineups(match, {
            'home_team': self.rival.name, 'away_team': self.team.name,
            'home_convocados': [f'{JERSEY} Pau Ferrer'], 'away_convocados': [],
            'sets': [
                {'title': f'Set {i}', 'teams': [
                    {'name': self.rival.name, 'points': 25, 'lineup': _lineup()},
                    {'name': self.team.name, 'points': 20, 'lineup': _lineup(False)},
                ]}
                for i in range(1, 4)
            ],
        })
        user = get_user_model().objects.create_user(username='pau', password='pass')
        Membership.objects.create(user=user, organization=self.org, is_approved=True)
        self.client.force_login(user)
        other.user = user
        other.save()

        response = self.visit('rosters:my_profile')

        self.assertContains(response, 'Has jugado 1 partido y 3 sets; titular en 1.')


class CardNarrativeTestBase(PlayerCardTestBase):
    """Redacción con LLM del cromo (#551): talismán de manual y un cromo con su perfil de reglas."""

    def make_talisman(self):
        for _ in range(5):
            self.play([(25, 23, _lineup())] * 3)
        for _ in range(3):
            self.play([(15, 25, _lineup(False))] * 3)

    def narrative_row(self, key='talisman', language='es', text='{nombre} es el talismán.'):
        return CardNarrative.objects.create(
            person=self.person, season=self.season, highlight_key=key, language=language, text=text,
        )


@override_settings(ALLOWED_HOSTS=['testclub.ilovevoley.es', 'localhost'], MEDIA_ROOT=tempfile.mkdtemp())
class CardNarrativeViewTests(CardNarrativeTestBase):
    def test_usa_el_texto_redactado_solo_si_es_del_perfil_y_idioma_actuales(self):
        self.make_talisman()
        rules_text = self.highlight()['text']
        self.narrative_row()
        self.narrative_row(language='ca', text='{nombre} és el talismà.')
        self.narrative_row(key='fijo', text='{nombre} fijo.')

        with translation.override('es'):
            narrated = narrated_highlight(self.highlight(), self.person, self.season)
        with translation.override('ca'):
            narrated_ca = narrated_highlight(self.highlight(), self.person, self.season)
        self.assertEqual(narrated['text'], 'Marc es el talismán.')
        self.assertEqual(narrated_ca['text'], 'Marc és el talismà.')
        self.assertEqual(narrated['title'], self.highlight()['title'])  # título e icono siguen siendo de reglas

        CardNarrative.objects.filter(highlight_key='talisman').update(text='')
        with translation.override('es'):
            self.assertEqual(narrated_highlight(self.highlight(), self.person, self.season)['text'], rules_text)
        CardNarrative.objects.all().delete()
        self.narrative_row(key='fijo')
        with translation.override('es'):
            self.assertEqual(narrated_highlight(self.highlight(), self.person, self.season)['text'], rules_text)

    def test_la_vista_del_cromo_pinta_el_texto_redactado(self):
        self.make_talisman()
        self.narrative_row()
        user = get_user_model().objects.create_user(username='padre', password='pass')
        Membership.objects.create(user=user, organization=self.org, is_approved=True)
        user.children.add(self.person)
        self.client.force_login(user)

        with mock.patch('ilovevoley.rosters.views.render_player_card', return_value=_png()) as render:
            self.client.get(reverse('rosters:person_card', args=[self.person.id]), HTTP_HOST='testclub.ilovevoley.es')

        self.assertEqual(render.call_args.kwargs['highlight']['text'], 'Marc es el talismán.')


@override_settings(LLM_NARRATIVE_ENABLED=True, LLM_NARRATIVE_API_KEY='k')
class RedactPendingCardNarrativesTests(CardNarrativeTestBase):
    def close_season(self):
        Season.objects.filter(pk=self.season.pk).update(is_current=False)

    def run_task(self, side_effect='{nombre} lo da todo.'):
        kwargs = {'side_effect': side_effect} if callable(side_effect) or isinstance(side_effect, Exception) \
            else {'return_value': side_effect}
        with mock.patch.object(narrative, 'redact', **kwargs) as redact:
            saved = redact_pending_card_narratives_task()
        return saved, redact

    def test_solo_redacta_perfiles_de_temporadas_cerradas(self):
        self.make_talisman()
        Season.objects.filter(pk=self.season.pk).update(is_current=True)
        saved, redact = self.run_task()
        self.assertEqual((saved, redact.call_count), (0, 0))  # temporada abierta: sus cifras aún cambian

        self.close_season()
        saved, redact = self.run_task()
        self.assertEqual(saved, 2)
        self.assertEqual(
            set(CardNarrative.objects.values_list('highlight_key', 'language', 'text')),
            {('talisman', 'es', '{nombre} lo da todo.'), ('talisman', 'ca', '{nombre} lo da todo.')},
        )

    def test_el_momento_de_temporada_sigue_por_reglas(self):
        # Titular en todo lo que jugó, pero solo 1 de 4 partidos: sin perfil, solo momento (D4).
        self.play([(25, 15, _lineup())] * 3)
        for _ in range(3):
            self.play([(25, 15, _lineup(False))] * 3)
        self.close_season()
        saved, redact = self.run_task()
        self.assertEqual((saved, redact.call_count, CardNarrative.objects.count()), (0, 0, 0))

    def test_descarte_deja_fila_vacia_y_no_se_reintenta_pero_la_api_caida_no_escribe(self):
        self.make_talisman()
        self.close_season()
        saved, _redact = self.run_task(narrative.NarrativeTransientError('429'))
        self.assertEqual((saved, CardNarrative.objects.count()), (0, 0))

        saved, _redact = self.run_task(narrative.NarrativeDiscarded('cifras'))
        self.assertEqual(saved, 2)
        self.assertEqual(set(CardNarrative.objects.values_list('text', flat=True)), {''})
        saved, redact = self.run_task()
        self.assertEqual((saved, redact.call_count), (0, 0))

    def test_los_hechos_enviados_no_llevan_datos_personales(self):
        self.make_talisman()
        facts = season_facts(self.person, [self.team], self.season)
        sent = card_narrative_facts(identity_of(self.team), self.season, 'Talismán', facts)
        text = ' '.join(f'{key} {value}' for key, value in sent.items())
        for forbidden in (self.person.first_name, self.person.last_name, str(self.person.birth_year)):
            self.assertNotIn(forbidden, text)
        self.assertNotIn(self.person.id, sent.values())
        self.assertEqual((sent['perfil'], sent['sets']), ('Talismán', facts['sets']))
