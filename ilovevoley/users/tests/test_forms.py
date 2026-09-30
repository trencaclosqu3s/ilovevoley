from django.contrib.auth import get_user_model
from django.test import TestCase

from ilovevoley.core.models import Category, Organization
from ilovevoley.users.forms import UserProfileForm


class UserProfileFormTest(TestCase):
    """El email no se edita desde el perfil: el cambio pasa por la verificación
    de allauth. Con el campo 'readonly' en el widget un POST manipulado
    bastaba para dejar el email de otra persona en la cuenta.
    """

    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username='jugador', email='mio@example.com', password='contrasena'
        )

    def test_posted_email_is_ignored(self):
        form = UserProfileForm(
            data={
                'username': 'jugador',
                'email': 'victima@example.com',
                'first_name': 'Jugador',
                'last_name': 'Uno',
            },
            instance=self.user,
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertNotIn('email', form.fields)
        form.save()

        self.user.refresh_from_db()
        self.assertEqual(self.user.email, 'mio@example.com')


class UserProfileFormOrganizationTest(TestCase):
    """Las categorías de interés son independientes por club: guardarlas en uno
    no debe afectar a las del resto.
    """

    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username='socio', password='contrasena')
        self.org1 = Organization.objects.create(slug='pref-club-uno', name='Club Uno', is_active=True)
        self.org2 = Organization.objects.create(slug='pref-club-dos', name='Club Dos', is_active=True)
        self.infantil = Category.objects.create(name='Infantil', is_active=True)
        self.cadete = Category.objects.create(name='Cadete', is_active=True)

    def _save(self, organization, categories):
        form = UserProfileForm(
            data={
                'username': 'socio',
                'first_name': 'Socio',
                'last_name': 'Uno',
                'preferred_categories': [category.pk for category in categories],
            },
            instance=self.user,
            organization=organization,
        )
        self.assertTrue(form.is_valid(), form.errors)
        form.save()

    def test_preferences_are_independent_per_organization(self):
        self._save(self.org1, [self.infantil])
        self._save(self.org2, [self.cadete])

        self.assertEqual(
            list(self.user.preferred_categories_for(self.org1)), [self.infantil]
        )
        self.assertEqual(
            list(self.user.preferred_categories_for(self.org2)), [self.cadete]
        )

    def test_empty_organization_has_no_preferences(self):
        self._save(self.org1, [self.infantil])

        self.assertFalse(self.user.has_preferred_categories(self.org2))
        self.assertFalse(self.user.preferred_categories_for(self.org2).exists())

    def test_initial_categories_are_scoped_to_organization(self):
        self._save(self.org1, [self.infantil])

        form = UserProfileForm(instance=self.user, organization=self.org1)
        self.assertEqual(list(form.initial[f'preferred_categories_{self.org1.id}']), [self.infantil])

    def test_form_exposes_category_fields_for_all_user_memberships(self):
        from ilovevoley.users.models import Membership
        Membership.objects.create(user=self.user, organization=self.org1, is_approved=True)
        Membership.objects.create(user=self.user, organization=self.org2, is_approved=False)

        form = UserProfileForm(instance=self.user)
        org_ids = [org.id for org, _ in form.organization_category_fields]
        self.assertIn(self.org1.id, org_ids)
        self.assertIn(self.org2.id, org_ids)

    def test_form_saves_preferences_for_multiple_organizations_at_once(self):
        from ilovevoley.users.models import Membership
        Membership.objects.create(user=self.user, organization=self.org1)
        Membership.objects.create(user=self.user, organization=self.org2)

        form = UserProfileForm(
            data={
                'username': 'socio',
                'first_name': 'Socio',
                'last_name': 'Uno',
                f'preferred_categories_{self.org1.id}': [self.infantil.pk],
                f'preferred_categories_{self.org2.id}': [self.cadete.pk],
            },
            instance=self.user,
        )
        self.assertTrue(form.is_valid(), form.errors)
        form.save()

        self.assertEqual(list(self.user.preferred_categories_for(self.org1)), [self.infantil])
        self.assertEqual(list(self.user.preferred_categories_for(self.org2)), [self.cadete])

    def test_form_superuser_without_memberships_includes_active_organizations(self):
        superuser = get_user_model().objects.create_superuser(username='super', password='pass')
        form = UserProfileForm(instance=superuser)
        org_ids = [org.id for org, _ in form.organization_category_fields]
        self.assertIn(self.org1.id, org_ids)
        self.assertIn(self.org2.id, org_ids)

