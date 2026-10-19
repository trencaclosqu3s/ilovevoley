"""Checklist de bienvenida familiar (#533).

Justificación (docs/ai-guidelines/testing-guidelines.md): protege la regla de
producto de qué cuenta como hecho —cada paso se marca solo con el dato real que
ya existe en la cuenta, las preferencias valen por club y la guía desaparece al
completarse o descartarse— y el efecto persistente del descarte, que es el
único escrito de la feature. No se testea el HTML ni el banner.
"""
from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from ilovevoley.core.models import Category, Organization
from ilovevoley.rosters.models import Person
from ilovevoley.users.models import CategoryPreference, WebPushSubscription
from ilovevoley.users.onboarding import welcome_checklist

User = get_user_model()

STEP_KEYS = ['categories', 'push', 'profile', 'calendar']


class WelcomeChecklistStateTest(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name='CV Sant Just', slug='onboarding')
        self.other_org = Organization.objects.create(name='Otro Club', slug='otro-club')
        self.user = User.objects.create_user(username='familiar', password='contrasena')
        self.category = Category.objects.create(name='Infantil', is_active=True)

    def _done_keys(self):
        # `has_my_profile` es cached_property: se re-lee la cuenta para que cada
        # mutación del test se refleje en la siguiente consulta.
        user = User.objects.get(pk=self.user.pk)
        steps = welcome_checklist(user, self.org)
        return {step['key'] for step in steps or [] if step['done']}

    def test_sin_club_no_hay_guia(self):
        self.assertIsNone(welcome_checklist(self.user, None))

    def test_recien_llegado_ve_los_cuatro_pasos_pendientes(self):
        steps = welcome_checklist(self.user, self.org)
        self.assertEqual([step['key'] for step in steps], STEP_KEYS)
        self.assertEqual(
            {step['key'] for step in steps if step['done']}, set(), steps,
        )

    def test_el_paso_de_categorias_solo_cuenta_con_las_preferencias_del_club(self):
        CategoryPreference.objects.create(
            user=self.user, organization=self.other_org,
        ).categories.add(self.category)
        self.assertNotIn('categories', self._done_keys())

        CategoryPreference.objects.create(
            user=self.user, organization=self.org,
        ).categories.add(self.category)
        self.assertIn('categories', self._done_keys())

    def test_el_paso_de_avisos_cuenta_con_la_suscripcion_push_del_club(self):
        WebPushSubscription.objects.create(
            user=self.user, organization=self.org,
            endpoint='https://fcm.googleapis.com/fcm/send/onboarding',
            p256dh='clave-publica', auth='secreto',
        )
        self.assertIn('push', self._done_keys())

    def test_el_paso_de_ficha_cuenta_con_la_propia_o_la_de_un_hijo(self):
        own = Person.objects.create(
            first_name='Familiar', last_name='Uno', birth_year=1980, user=self.user,
        )
        self.assertIn('profile', self._done_keys())

        own.user = None
        own.save(update_fields=['user'])
        self.assertNotIn('profile', self._done_keys())

        child = Person.objects.create(first_name='Hija', last_name='Uno', birth_year=2015)
        self.user.children.add(child)
        self.assertIn('profile', self._done_keys())

    def test_completar_la_ficha_solo_se_pide_cuando_hay_una_provisional(self):
        """El paso aparece con la ficha vinculada y se cierra al completarla (#569)."""
        self.assertNotIn(
            'complete_profile', [step['key'] for step in welcome_checklist(self.user, self.org)],
        )

        own = Person.objects.create(
            first_name='', last_name='García', is_provisional=True, user=self.user,
        )
        user = User.objects.get(pk=self.user.pk)
        steps = {step['key']: step['done'] for step in welcome_checklist(user, self.org)}
        self.assertFalse(steps['complete_profile'])

        own.first_name = 'Familiar'
        own.birth_year = 1980
        own.save(update_fields=['first_name', 'birth_year'])
        user = User.objects.get(pk=self.user.pk)
        steps = {step['key']: step['done'] for step in welcome_checklist(user, self.org)}
        self.assertTrue(steps['complete_profile'])

    def test_el_paso_de_calendario_cuenta_con_el_token_de_suscripcion(self):
        self.assertNotIn('calendar', self._done_keys())

        self.user.calendar_token = 'token-de-suscripcion'
        self.user.save(update_fields=['calendar_token'])
        self.assertIn('calendar', self._done_keys())

    def test_completar_los_cuatro_pasos_esconde_la_guia(self):
        CategoryPreference.objects.create(
            user=self.user, organization=self.org,
        ).categories.add(self.category)
        WebPushSubscription.objects.create(
            user=self.user, organization=self.org,
            endpoint='https://fcm.googleapis.com/fcm/send/completa',
            p256dh='clave-publica', auth='secreto',
        )
        Person.objects.create(
            first_name='Familiar', last_name='Uno', birth_year=1980, user=self.user,
        )
        self.user.calendar_token = 'token-de-suscripcion'
        self.user.save(update_fields=['calendar_token'])

        self.assertIsNone(welcome_checklist(self.user, self.org))

    def test_descartarla_la_esconde_aunque_falte_todo(self):
        self.user.onboarding_dismissed_at = timezone.now()
        self.user.save(update_fields=['onboarding_dismissed_at'])

        self.assertIsNone(welcome_checklist(self.user, self.org))


@override_settings(ALLOWED_HOSTS=['onboarding.ilovevoley.es', 'localhost', 'testserver'])
class DismissOnboardingViewTest(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name='CV Sant Just', slug='onboarding')
        self.user = User.objects.create_user(username='familiar', password='contrasena')
        self.client = Client()

    def test_descartar_lo_guarda_en_la_cuenta(self):
        """El descarte persiste por cuenta, no por dispositivo (#533)."""
        self.client.login(username='familiar', password='contrasena')

        response = self.client.post(
            reverse('dismiss_onboarding'), HTTP_HOST='onboarding.ilovevoley.es',
        )

        self.assertRedirects(response, reverse('profile'))
        self.user.refresh_from_db()
        self.assertIsNotNone(self.user.onboarding_dismissed_at)
