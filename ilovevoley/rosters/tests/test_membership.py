from datetime import date

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from ilovevoley.core.models import Category, Organization, Season
from ilovevoley.rosters.models import Person, PersonOrganization, PlayerRole
from ilovevoley.teams.models import Club, Team
from ilovevoley.teams.tests.helpers import identity_of
from ilovevoley.users.models import Membership


def _org(slug, name, club):
    return Organization.objects.create(
        slug=slug, name=name, club=club,
        club_team_names={'1': name}, is_active=True,
    )


@override_settings(ALLOWED_HOSTS=['club-a.rostertest.es', 'club-b.rostertest.es', 'testserver'])
class ActiveForTenantTests(TestCase):
    """#478: la baja deportiva es por club, no global.

    Regla bajo prueba: los listados y selectores de un tenant incluyen una
    ficha si tiene alta activa en ese club o si tiene un rol activo en la
    temporada actual, y las excluyen si su pertenencia está dada de baja.
    El acceso histórico (``for_tenant``) no se estrecha: la ficha dada de
    baja sigue accesible por URL y en los históricos de plantillas.
    """

    def setUp(self):
        cache.clear()
        self.club_a = Club.objects.create(official_name='Club A', federation_id='CLUB-A')
        self.club_b = Club.objects.create(official_name='Club B', federation_id='CLUB-B')
        self.org_a = _org('club-a', 'Club A Tenant', self.club_a)
        self.org_b = _org('club-b', 'Club B Tenant', self.club_b)
        self.category = Category.objects.create(name='Senior', is_active=True)
        # La temporada actual la fija el propio sistema (corte 1 de
        # septiembre); la anterior no queda marcada y no cuenta como actual.
        self.season = Season.objects.current()
        self.season_prev = Season.objects.resolve('2024-25')
        self.team_a = identity_of(Team.objects.create(
            name='Club A Senior', category=self.category,
            club=self.club_a, federation_id='TEAM-A1', is_active=True,
        ))
        self.team_b = identity_of(Team.objects.create(
            name='Club B Senior', category=self.category,
            club=self.club_b, federation_id='TEAM-B1', is_active=True,
        ))
        User = get_user_model()
        self.member = User.objects.create_user(username='member', password='pass')
        Membership.objects.create(
            user=self.member, organization=self.org_a, is_approved=True,
        )

    def _person(self, first_name, last_name):
        return Person.objects.create(
            first_name=first_name, last_name=last_name, birth_year=2000,
        )

    @staticmethod
    def _give_alta(person, org):
        person.organizations.add(org)

    @staticmethod
    def _dar_de_baja(person, org):
        membership = person.club_memberships.get(organization=org)
        membership.is_active = False
        membership.save(update_fields=['is_active'])
        return membership

    def test_alta_activa_aparece_solo_en_su_club(self):
        person = self._person('Ana', 'Alta')
        self._give_alta(person, self.org_a)
        self.assertIn(person, Person.objects.active_for_tenant(self.org_a))
        self.assertNotIn(person, Person.objects.active_for_tenant(self.org_b))

    def test_baja_no_aparece_en_los_listados_de_su_club(self):
        person = self._person('Berta', 'Baja')
        self._give_alta(person, self.org_a)
        self._dar_de_baja(person, self.org_a)
        self.assertNotIn(person, Person.objects.active_for_tenant(self.org_a))

    def test_baja_se_mantiene_accesible_por_historico(self):
        """La baja quita de listados, no el acceso: `for_tenant` la mantiene."""
        person = self._person('Carla', 'BajaHistorica')
        self._give_alta(person, self.org_a)
        self._dar_de_baja(person, self.org_a)
        self.assertIn(person, Person.objects.for_tenant(self.org_a))

    def test_rol_temporada_actual_mete_a_la_ficha(self):
        """Un jugador de plantilla de la temporada actual sale aunque no esté dado de alta."""
        person = self._person('David', 'Plantilla')
        PlayerRole.objects.create(
            person=person, identity=self.team_a, season=self.season,
            jersey_number=9, is_active=True,
        )
        self.assertIn(person, Person.objects.active_for_tenant(self.org_a))

    def test_rol_temporada_anterior_no_mete_a_la_ficha(self):
        person = self._person('Elena', 'Retrograda')
        PlayerRole.objects.create(
            person=person, identity=self.team_a, season=self.season_prev,
            jersey_number=5, is_active=True,
        )
        self.assertNotIn(person, Person.objects.active_for_tenant(self.org_a))

    def test_rol_de_otro_club_no_mete_a_la_ficha_en_este(self):
        person = self._person('Fernando', 'Ajeno')
        PlayerRole.objects.create(
            person=person, identity=self.team_b, season=self.season,
            jersey_number=2, is_active=True,
        )
        self.assertNotIn(person, Person.objects.active_for_tenant(self.org_a))

    def test_cambio_de_club(self):
        """El caso tipo: baja en A y se alista en B.

        En A desaparece de los listados (baja) pero su ficha sigue
        alcanzable; en B sale sin necesitar otra cosa que su rol actual
        (o su alta). Así se evita el flag global que lo ocultaría de ambos.
        """
        person = self._person('Marc', 'Puig')
        self._give_alta(person, self.org_a)
        self._dar_de_baja(person, self.org_a)
        # En B lo alistan de dos formas posibles: alta o rol de temporada.
        with_alta = person
        self._give_alta(with_alta, self.org_b)
        self.assertNotIn(with_alta, Person.objects.active_for_tenant(self.org_a))
        self.assertIn(with_alta, Person.objects.for_tenant(self.org_a))
        self.assertIn(with_alta, Person.objects.active_for_tenant(self.org_b))

        only_role = self._person('Marc', 'Rolon')
        PlayerRole.objects.create(
            person=only_role, identity=self.team_b, season=self.season,
            jersey_number=7, is_active=True,
        )
        self.assertIn(only_role, Person.objects.active_for_tenant(self.org_b))

    def test_person_list_excluye_las_bajas(self):
        """El listado visible del tenant respeta la baja (#478)."""
        baja = self._person('Fabian', 'BajaListado')
        alta = self._person('Gloria', 'AltaListado')
        self._give_alta(baja, self.org_a)
        self._give_alta(alta, self.org_a)
        self._dar_de_baja(baja, self.org_a)

        url = reverse('rosters:person_list')
        self.client.force_login(self.member)
        response = self.client.get(url, HTTP_HOST='club-a.rostertest.es')
        self.assertNotContains(response, baja.full_name)
        self.assertContains(response, alta.full_name)


@override_settings(ALLOWED_HOSTS=['club-a.rostertest.es', 'testserver'])
class EnrollTests(TestCase):
    """`enroll()` es el único punto de escritura de pertenencias: reactiva bajas (#478).

    M2M `.add()` no actualiza filas existentes; si la alta volviese a usar
    `.add()` una ficha dada de baja quedaría invisible de por vida.
    """

    def setUp(self):
        cache.clear()
        self.club = Club.objects.create(official_name='Club Enroll', federation_id='CLUB-E')
        self.org = _org('club-enroll', 'Club Enroll', self.club)

    def test_enroll_actualiza_fila_previa_dada_de_baja(self):
        person = Person.objects.create(
            first_name='Hugo', last_name='Naves', birth_year=2005,
        )
        membership = PersonOrganization.objects.create(
            person=person, organization=self.org,
            is_active=False, end_date=date(2025, 12, 31),
        )
        person.enroll(self.org)
        membership.refresh_from_db()
        self.assertTrue(membership.is_active)
        self.assertIsNone(membership.end_date)

    def test_enroll_crea_fila_si_no_existe(self):
        person = Person.objects.create(
            first_name='Iker', last_name='Izaro', birth_year=1999,
        )
        person.enroll(self.org)
        self.assertTrue(
            PersonOrganization.objects.filter(
                person=person, organization=self.org, is_active=True,
            ).exists()
        )


@override_settings(ALLOWED_HOSTS=['club-a.rostertest.es', 'testserver'])
class PersonMembershipToggleTests(TestCase):
    """El toggle de baja/alta de la ficha: efecto persistente y permisos (#478)."""

    def setUp(self):
        cache.clear()
        User = get_user_model()
        self.club = Club.objects.create(official_name='Club Toggle', federation_id='CLUB-T')
        self.org = _org('club-a', 'Club Toggle', self.club)
        self.manager = User.objects.create_user(username='manager', password='pass')
        Membership.objects.create(
            user=self.manager, organization=self.org,
            role='manager', is_approved=True,
        )
        self.member = User.objects.create_user(username='member', password='pass')
        Membership.objects.create(
            user=self.member, organization=self.org,
            role='member', is_approved=True,
        )
        self.person = Person.objects.create(
            first_name='Julia', last_name='Montes', birth_year=2003,
        )
        self.person.enroll(self.org)
        self.url = reverse('rosters:person_membership_toggle', args=[self.person.id])

    def test_manager_da_de_baja_y_reactiva(self):
        self.client.force_login(self.manager)
        response = self.client.post(self.url, HTTP_HOST='club-a.rostertest.es')
        self.assertEqual(response.status_code, 302)
        membership = self.person.club_memberships.get(organization=self.org)
        self.assertFalse(membership.is_active)
        self.assertIsNotNone(membership.end_date)

        self.client.post(self.url, HTTP_HOST='club-a.rostertest.es')
        membership.refresh_from_db()
        self.assertTrue(membership.is_active)
        self.assertIsNone(membership.end_date)

    def test_member_no_puede_dar_de_baja(self):
        self.client.force_login(self.member)
        response = self.client.post(self.url, HTTP_HOST='club-a.rostertest.es')
        self.assertEqual(response.status_code, 403)
        self.assertTrue(self.person.club_memberships.get(organization=self.org).is_active)
