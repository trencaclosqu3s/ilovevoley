"""Tests del admin de plantillas con lógica propia."""

from django.contrib.admin.sites import AdminSite
from django.test import TestCase

from ilovevoley.core.models import Organization
from ilovevoley.rosters.admin.rosters import PersonAdmin
from ilovevoley.rosters.models import Person, PersonOrganization
from ilovevoley.teams.models import Club


class PersonAdminMembershipStateTests(TestCase):
    """ILOVEVOLEY-96 / #478: columna Clubes del listado de Person.

    Justificación (testing-guidelines): caso límite que ya falló en producción
    — ``format_html('<br>')`` sin args revienta el changelist al haber
    pertenencias. El contrato es que ``membership_state`` renderiza altas/bajas
    sin TypeError.
    """

    def setUp(self):
        self.admin = PersonAdmin(Person, AdminSite())
        self.club = Club.objects.create(
            official_name='Club Test', federation_id='CLUB-ADM',
        )
        self.org = Organization.objects.create(
            slug='club-adm',
            name='Club Admin Tenant',
            club=self.club,
            club_team_names={'1': 'Club Admin Tenant'},
            is_active=True,
        )
        self.person = Person.objects.create(
            first_name='Joan', last_name='Test', birth_year=2000,
        )

    def test_membership_state_with_memberships_does_not_raise(self):
        PersonOrganization.objects.create(
            person=self.person, organization=self.org, is_active=True,
        )
        html = self.admin.membership_state(self.person)
        self.assertIn('Club Admin Tenant', html)
        self.assertIn('alta', html)

    def test_membership_state_empty_is_em_dash(self):
        html = self.admin.membership_state(self.person)
        self.assertIn('—', html)
