"""Solicitudes de vínculo cuenta ↔ ficha (#531).

Solo se cubre lo que protege una decisión propia: una ficha ↔ un usuario,
el efecto persistente de aprobar, el aislamiento entre clubes y la
idempotencia/anti-abuso de las solicitudes. La búsqueda decorativa no se prueba.
"""
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from ilovevoley.core.models import Organization
from ilovevoley.rosters.link_requests import (
    MAX_PENDING_REQUESTS,
    create_link_request,
    create_link_request_for_person,
)
from ilovevoley.rosters.models import Person, PersonLinkRequest
from ilovevoley.users.models import Membership


HOST_A = 'club-a.ilovevoley.es'
HOST_B = 'club-b.ilovevoley.es'


@override_settings(ALLOWED_HOSTS=[HOST_A, HOST_B, 'localhost'])
class PersonLinkRequestTests(TestCase):
    def setUp(self):
        cache.clear()
        self.org_a = Organization.objects.create(
            slug='club-a', name='Club A', club_team_names={'1': 'Club A'}, is_active=True,
        )
        self.org_b = Organization.objects.create(
            slug='club-b', name='Club B', club_team_names={'1': 'Club B'}, is_active=True,
        )
        User = get_user_model()
        self.user = User.objects.create_user(username='member', password='pass', email='member@example.com')
        Membership.objects.create(user=self.user, organization=self.org_a, is_approved=True)
        self.manager = User.objects.create_user(username='manager', password='pass')
        Membership.objects.create(
            user=self.manager, organization=self.org_a, is_approved=True, role='manager',
        )
        self.person = Person.objects.create(first_name='Ana', last_name='Propia', birth_year=2012)
        self.person.organizations.add(self.org_a)

    def _request_link(self, host=HOST_A, kind='self', person=None, **overrides):
        person = person or self.person
        data = {
            'first_name': person.first_name, 'last_name': person.last_name,
            'birth_year': person.birth_year, 'kind': kind,
        }
        data.update(overrides)
        return self.client.post(reverse('rosters:person_link_request'), data, HTTP_HOST=host)

    def test_solicitar_mi_ficha_crea_solicitud_pendiente_sin_vincular(self):
        self.client.force_login(self.user)
        response = self._request_link()
        self.assertEqual(response.status_code, 302)
        link = PersonLinkRequest.objects.get()
        self.assertEqual(link.status, PersonLinkRequest.Status.PENDING)
        self.assertEqual(link.kind, PersonLinkRequest.Kind.SELF)
        self.assertEqual(link.organization, self.org_a)
        # Solicitar no escribe el vínculo: eso es lo que hace el moderador.
        self.person.refresh_from_db()
        self.assertIsNone(self.person.user_id)

    def test_aprobar_mi_ficha_fija_el_usuario(self):
        self.client.force_login(self.user)
        self._request_link()
        link = PersonLinkRequest.objects.get()

        self.client.force_login(self.manager)
        response = self.client.post(
            reverse('core:approve_person_link_api', args=[link.id]), HTTP_HOST=HOST_A,
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['success'])
        link.refresh_from_db()
        self.person.refresh_from_db()
        self.assertEqual(link.status, PersonLinkRequest.Status.APPROVED)
        self.assertEqual(link.resolved_by, self.manager)
        self.assertEqual(self.person.user_id, self.user.id)

    def test_una_ficha_solo_pertenece_a_un_usuario(self):
        # La solicitud se crea a mano para saltarse la validación de alta y
        # comprobar el guardarraíl de aprobación: otra cuenta ya tiene la ficha.
        otro = get_user_model().objects.create_user(username='otro', password='pass')
        self.person.user = otro
        self.person.save(update_fields=['user'])
        link = PersonLinkRequest.objects.create(
            user=self.user, person=self.person, organization=self.org_a,
            kind=PersonLinkRequest.Kind.SELF,
        )

        self.client.force_login(self.manager)
        response = self.client.post(
            reverse('core:approve_person_link_api', args=[link.id]), HTTP_HOST=HOST_A,
        )
        self.assertEqual(response.status_code, 409)
        link.refresh_from_db()
        self.person.refresh_from_db()
        self.assertEqual(link.status, PersonLinkRequest.Status.PENDING)
        self.assertEqual(self.person.user_id, otro.id)

    def test_aprobar_ficha_de_hijo_la_anade_a_children_y_a_tu(self):
        child = Person.objects.create(first_name='Hijo', last_name='Propia', birth_year=2015)
        child.organizations.add(self.org_a)

        self.client.force_login(self.user)
        self._request_link(kind='child', person=child)
        link = PersonLinkRequest.objects.get()

        self.client.force_login(self.manager)
        self.client.post(
            reverse('core:approve_person_link_api', args=[link.id]), HTTP_HOST=HOST_A,
        )
        self.assertIn(child, self.user.children.all())

        self.client.force_login(self.user)
        response = self.client.get(reverse('rosters:my_profile'), HTTP_HOST=HOST_A)
        self.assertContains(response, 'Hijo Propia')

    def test_my_profile_sin_vinculos_muestra_la_tarjeta_desplegada(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('rosters:my_profile'), HTTP_HOST=HOST_A)
        self.assertIsNotNone(response.context['link_form'])
        self.assertFalse(response.context['has_links'])

    def test_my_profile_con_ficha_propia_mantiene_la_tarjeta_plegada(self):
        # Antes desaparecía: con ficha propia no se podía añadir la de un hijo/a (#553).
        self.person.user = self.user
        self.person.save(update_fields=['user'])

        self.client.force_login(self.user)
        response = self.client.get(reverse('rosters:my_profile'), HTTP_HOST=HOST_A)
        self.assertIsNotNone(response.context['link_form'])
        self.assertTrue(response.context['has_links'])
        self.assertTrue(response.context['has_own_person'])
        self.assertEqual(response.context['children_count'], 0)

    def test_my_profile_con_hijos_sin_ficha_propia_mantiene_la_tarjeta_plegada(self):
        # Caso familia roto antes: hijos vinculados y sin ficha propia (#553).
        child = Person.objects.create(first_name='Hijo', last_name='Propia', birth_year=2015)
        child.organizations.add(self.org_a)
        self.user.children.add(child)

        self.client.force_login(self.user)
        response = self.client.get(reverse('rosters:my_profile'), HTTP_HOST=HOST_A)
        self.assertIsNotNone(response.context['link_form'])
        self.assertTrue(response.context['has_links'])
        self.assertFalse(response.context['has_own_person'])
        self.assertEqual(response.context['children_count'], 1)

    def test_no_se_puede_solicitar_una_ficha_de_otro_club(self):
        ajena = Person.objects.create(first_name='Bea', last_name='Ajena', birth_year=2010)
        ajena.organizations.add(self.org_b)

        self.client.force_login(self.user)
        response = self._request_link(person=ajena)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(PersonLinkRequest.objects.filter(person=ajena).exists())

    def test_solicitudes_duplicadas_no_se_duplican(self):
        first, error = create_link_request(
            self.user, self.org_a, self.person.first_name, self.person.last_name,
            self.person.birth_year, PersonLinkRequest.Kind.SELF,
        )
        second, error2 = create_link_request(
            self.user, self.org_a, self.person.first_name, self.person.last_name,
            self.person.birth_year, PersonLinkRequest.Kind.SELF,
        )
        self.assertIsNone(error)
        self.assertIsNone(error2)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(PersonLinkRequest.objects.count(), 1)

    def test_limite_de_solicitudes_pendientes(self):
        for i in range(MAX_PENDING_REQUESTS):
            person = Person.objects.create(first_name=f'P{i}', last_name='Pendiente', birth_year=2010)
            person.organizations.add(self.org_a)
            PersonLinkRequest.objects.create(
                user=self.user, person=person, organization=self.org_a,
                kind=PersonLinkRequest.Kind.CHILD,
            )
        extra = Person.objects.create(first_name='Extra', last_name='Pendiente', birth_year=2011)
        extra.organizations.add(self.org_a)
        link, error = create_link_request(
            self.user, self.org_a, extra.first_name, extra.last_name,
            extra.birth_year, PersonLinkRequest.Kind.CHILD,
        )
        self.assertIsNone(link)
        self.assertIsNotNone(error)

    def test_el_panel_muestra_la_solicitud_solo_a_su_club(self):
        self.client.force_login(self.user)
        self._request_link()

        self.client.force_login(self.manager)
        response = self.client.get(reverse('core:moderation_panel'), HTTP_HOST=HOST_A)
        self.assertContains(response, self.person.full_name)

        manager_b = get_user_model().objects.create_user(username='manager-b', password='pass')
        Membership.objects.create(
            user=manager_b, organization=self.org_b, is_approved=True, role='manager',
        )
        self.client.force_login(manager_b)
        response = self.client.get(reverse('core:moderation_panel'), HTTP_HOST=HOST_B)
        self.assertNotContains(response, self.person.full_name)


@override_settings(ALLOWED_HOSTS=[HOST_A, HOST_B, 'localhost'])
class ProvisionalPersonClaimTests(TestCase):
    """Reclamar por id una ficha provisional del acta (#569).

    Justificación: protege que el id solo valga mientras la ficha sea provisional
    (una completa sigue exigiendo la verificación por nombre y año) y que no
    cruce clubes. Es la regla que impide pedir el vínculo enumerando ids.
    """

    def setUp(self):
        cache.clear()
        self.org_a = Organization.objects.create(
            slug='club-a', name='Club A', club_team_names={'1': 'Club A'}, is_active=True,
        )
        self.org_b = Organization.objects.create(
            slug='club-b', name='Club B', club_team_names={'1': 'Club B'}, is_active=True,
        )
        self.user = get_user_model().objects.create_user(username='member', password='pass')
        Membership.objects.create(user=self.user, organization=self.org_a, is_approved=True)
        self.provisional = Person.objects.create(
            first_name='', last_name='García', is_provisional=True,
        )
        self.provisional.organizations.add(self.org_a)

    def test_reclama_una_provisional_del_club_sin_escribir_el_vinculo(self):
        link, error = create_link_request_for_person(
            self.user, self.org_a, self.provisional, PersonLinkRequest.Kind.CHILD,
        )

        self.assertIsNone(error)
        self.assertEqual(link.person, self.provisional)
        self.assertEqual(link.status, PersonLinkRequest.Status.PENDING)
        self.provisional.refresh_from_db()
        self.assertIsNone(self.provisional.user_id)

    def test_una_ficha_completa_no_se_reclama_por_id(self):
        completa = Person.objects.create(first_name='Ana', last_name='Ruiz', birth_year=2012)
        completa.organizations.add(self.org_a)

        link, error = create_link_request_for_person(
            self.user, self.org_a, completa, PersonLinkRequest.Kind.SELF,
        )

        self.assertIsNone(link)
        self.assertIsNotNone(error)
        self.assertFalse(PersonLinkRequest.objects.exists())

    def test_no_se_reclama_una_provisional_de_otro_club(self):
        ajena = Person.objects.create(first_name='', last_name='García', is_provisional=True)
        ajena.organizations.add(self.org_b)

        link, error = create_link_request_for_person(
            self.user, self.org_a, ajena, PersonLinkRequest.Kind.SELF,
        )

        self.assertIsNone(link)
        self.assertIsNotNone(error)
        self.assertFalse(PersonLinkRequest.objects.exists())

    def test_no_reclama_como_propia_si_la_cuenta_ya_tiene_ficha(self):
        """El botón se oculta en la UI, pero la regla se aplica en servidor."""
        Person.objects.create(
            first_name='Ana', last_name='Ruiz', birth_year=2012, user=self.user,
        )

        link, error = create_link_request_for_person(
            self.user, self.org_a, self.provisional, PersonLinkRequest.Kind.SELF,
        )

        self.assertIsNone(link)
        self.assertIsNotNone(error)
        self.assertFalse(PersonLinkRequest.objects.exists())

    def test_el_endpoint_de_reclamo_crea_la_solicitud(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse('rosters:person_link_claim'),
            {'person_id': self.provisional.id, 'kind': 'self'},
            HTTP_HOST=HOST_A,
        )

        self.assertEqual(response.status_code, 302)
        link = PersonLinkRequest.objects.get()
        self.assertEqual(link.person, self.provisional)
        self.provisional.refresh_from_db()
        self.assertIsNone(self.provisional.user_id)
