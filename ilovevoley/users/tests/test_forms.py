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
                f'preferred_categories_{organization.id}': [category.pk for category in categories],
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

        other = UserProfileForm(instance=self.user, organization=self.org2)
        self.assertNotIn(f'preferred_categories_{self.org2.id}', other.initial)

    def test_unselecting_all_categories_clears_preference(self):
        self._save(self.org1, [self.infantil])
        self.assertTrue(self.user.has_preferred_categories(self.org1))

        form = UserProfileForm(
            data={
                'username': 'socio',
                'first_name': 'Socio',
                'last_name': 'Uno',
                f'preferred_categories_{self.org1.id}': [],
            },
            instance=self.user,
            organization=self.org1,
        )
        self.assertTrue(form.is_valid(), form.errors)
        form.save()

        self.assertFalse(self.user.has_preferred_categories(self.org1))

    def test_save_with_commit_false_and_save_m2m_persists_preferences(self):
        form = UserProfileForm(
            data={
                'username': 'socio',
                'first_name': 'Socio',
                'last_name': 'Uno',
                f'preferred_categories_{self.org1.id}': [self.infantil.pk],
            },
            instance=self.user,
            organization=self.org1,
        )
        self.assertTrue(form.is_valid(), form.errors)
        user = form.save(commit=False)
        user.save()
        form.save_m2m()

        self.assertEqual(list(self.user.preferred_categories_for(self.org1)), [self.infantil])

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


class UserProfileFormNotificationPreferenceTest(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username='socio', password='contrasena')
        self.org1 = Organization.objects.create(slug='pref-club-uno', name='Club Uno', is_active=True)
        self.org2 = Organization.objects.create(slug='pref-club-dos', name='Club Dos', is_active=True)

    def test_initial_has_all_types_enabled_by_default(self):
        from ilovevoley.users.models import NotificationType
        form = UserProfileForm(instance=self.user, organization=self.org1)
        field_name = f'notification_types_{self.org1.id}'
        self.assertIn(field_name, form.fields)
        self.assertEqual(
            set(form.initial.get(field_name, [])),
            set(NotificationType.values),
        )

    def test_initial_reflects_disabled_types(self):
        from ilovevoley.users.models import NotificationPreference, NotificationType
        NotificationPreference.objects.create(
            user=self.user,
            organization=self.org1,
            notification_type=NotificationType.MATCH_RESULT,
            is_enabled=False,
        )
        form = UserProfileForm(instance=self.user, organization=self.org1)
        field_name = f'notification_types_{self.org1.id}'
        self.assertEqual(
            set(form.initial.get(field_name, [])),
            set(NotificationType.values) - {NotificationType.MATCH_RESULT},
        )

    def test_save_notification_preferences_disables_unselected(self):
        from ilovevoley.users.models import NotificationPreference, NotificationType
        form = UserProfileForm(
            data={
                'username': 'socio',
                'first_name': 'Socio',
                'last_name': 'Uno',
                f'notification_types_{self.org1.id}': [NotificationType.MATCH_RESULT],
            },
            instance=self.user,
            organization=self.org1,
        )
        self.assertTrue(form.is_valid(), form.errors)
        form.save()

        pref_result = NotificationPreference.objects.filter(
            user=self.user, organization=self.org1, notification_type=NotificationType.MATCH_RESULT
        ).first()
        self.assertTrue(pref_result is None or pref_result.is_enabled)

        pref_album = NotificationPreference.objects.get(
            user=self.user, organization=self.org1, notification_type=NotificationType.NEW_ALBUM
        )
        self.assertFalse(pref_album.is_enabled)

    def test_save_re_enables_previously_disabled_type(self):
        from ilovevoley.users.models import NotificationPreference, NotificationType
        NotificationPreference.objects.create(
            user=self.user,
            organization=self.org1,
            notification_type=NotificationType.MATCH_RESULT,
            is_enabled=False,
        )

        form = UserProfileForm(
            data={
                'username': 'socio',
                'first_name': 'Socio',
                'last_name': 'Uno',
                f'notification_types_{self.org1.id}': [NotificationType.MATCH_RESULT, NotificationType.NEW_ALBUM],
            },
            instance=self.user,
            organization=self.org1,
        )
        self.assertTrue(form.is_valid(), form.errors)
        form.save()

        pref_result = NotificationPreference.objects.get(
            user=self.user, organization=self.org1, notification_type=NotificationType.MATCH_RESULT
        )
        self.assertTrue(pref_result.is_enabled)


