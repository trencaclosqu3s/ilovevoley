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

    def test_form_exposes_category_fields_for_user_memberships_and_superuser(self):
        from ilovevoley.users.models import Membership
        Membership.objects.create(user=self.user, organization=self.org1, is_approved=True)
        Membership.objects.create(user=self.user, organization=self.org2, is_approved=False)

        form = UserProfileForm(instance=self.user)
        org_ids = [org.id for org, _ in form.organization_category_fields]
        self.assertIn(self.org1.id, org_ids)
        self.assertIn(self.org2.id, org_ids)

        # Un superusuario sin membresías ve todas las organizaciones activas.
        superuser = get_user_model().objects.create_superuser(username='super', password='pass')
        super_form = UserProfileForm(instance=superuser)
        super_org_ids = [org.id for org, _ in super_form.organization_category_fields]
        self.assertIn(self.org1.id, super_org_ids)
        self.assertIn(self.org2.id, super_org_ids)

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


class UserProfileFormNotificationPreferenceTest(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username='socio', password='contrasena')
        self.org1 = Organization.objects.create(slug='pref-club-uno', name='Club Uno', is_active=True)
        self.org2 = Organization.objects.create(slug='pref-club-dos', name='Club Dos', is_active=True)

    def test_initial_notification_types_reflect_enabled_state(self):
        from ilovevoley.users.models import NotificationPreference, NotificationType
        field_name = f'notification_types_{self.org1.id}'

        form = UserProfileForm(instance=self.user, organization=self.org1)
        self.assertIn(field_name, form.fields)
        # Por defecto todos los tipos están activos.
        self.assertEqual(
            set(form.initial.get(field_name, [])),
            set(NotificationType.values),
        )

        NotificationPreference.objects.create(
            user=self.user,
            organization=self.org1,
            notification_type=NotificationType.MATCH_RESULT,
            is_enabled=False,
        )
        form = UserProfileForm(instance=self.user, organization=self.org1)
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




class UserProfileFormFollowedTeamsTest(TestCase):
    """Los equipos seguidos (#363) se guardan en la misma preferencia del club que
    las categorías: elegir solo equipos debe crearla y vaciarlos no toca las categorías.
    """

    def setUp(self):
        from ilovevoley.teams.models import Club, Team
        User = get_user_model()
        self.user = User.objects.create_user(username='socio', password='contrasena')
        club = Club.objects.create(federation_id='c-uno', official_name='Club Uno')
        self.org = Organization.objects.create(slug='club-uno', name='Club Uno', is_active=True, club=club)
        self.team = Team.objects.create(name='Cadete B', federation_id='t-b', club=club)
        self.cadete = Category.objects.create(name='Cadete', is_active=True)

    def _save(self, categories=(), teams=()):
        form = UserProfileForm(
            data={
                'username': 'socio',
                'first_name': 'Socio',
                'last_name': 'Uno',
                f'preferred_categories_{self.org.id}': [c.pk for c in categories],
                f'followed_teams_{self.org.id}': [t.pk for t in teams],
            },
            instance=self.user,
            organization=self.org,
        )
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        return self.user.category_preferences.get(organization=self.org)

    def test_teams_alone_create_preference_and_clearing_them_keeps_categories(self):
        pref = self._save(teams=[self.team])
        self.assertEqual(list(pref.teams.all()), [self.team])
        form = UserProfileForm(instance=self.user, organization=self.org)
        self.assertEqual(list(form.initial[f'followed_teams_{self.org.id}']), [self.team])

        self._save(categories=[self.cadete], teams=[self.team])
        pref = self._save(categories=[self.cadete])
        self.assertFalse(pref.teams.exists())
        self.assertEqual(list(pref.categories.all()), [self.cadete])


class FollowedTeamsCurrentSeasonChoicesTest(TestCase):
    """Preferencias push (#526): una opción por identidad de la temporada actual.

    Sin filtrar, el scrape deja varias filas Team (una por fase/año) con el mismo
    nombre y la UI muestra checkboxes indistingibles; no tiene sentido seguir
    apariciones de temporadas pasadas.
    """

    def setUp(self):
        from ilovevoley.competitions.models import League, Standing
        from ilovevoley.core.models import Season
        from ilovevoley.teams.models import Club, Team, TeamIdentity
        from ilovevoley.teams.tests.helpers import identity_of
        from ilovevoley.users.forms import NotificationPreferencesForm

        User = get_user_model()
        self.NotificationPreferencesForm = NotificationPreferencesForm
        self.user = User.objects.create_user(username='socio', password='contrasena')
        self.club = Club.objects.create(federation_id='c-sj', official_name='CV Sant Josep')
        self.org = Organization.objects.create(
            slug='sant-josep', name='Sant Josep', is_active=True, club=self.club,
        )
        self.infantil = Category.objects.create(name='Infantil', is_active=True)
        Season.objects.filter(is_current=True).update(is_current=False)
        self.current_season = Season.objects.resolve('2026-27')
        Season.objects.filter(pk=self.current_season.pk).update(is_current=True)
        self.past_season = Season.objects.resolve('2025-26')

        self.current_a = Team.objects.create(
            name='CV SANT JOSEP LILA', federation_id='t-cur-a',
            club=self.club, category=self.infantil,
        )
        self.current_b = Team.objects.create(
            name='CV SANT JOSEP LILA', federation_id='t-cur-b',
            club=self.club, category=self.infantil,
        )
        identity = identity_of(self.current_a)
        self.current_b.identity = identity
        self.current_b.save(update_fields=['identity'])

        self.past = Team.objects.create(
            name='CV SANT JOSEP LILA', federation_id='t-past',
            club=self.club, category=self.infantil,
        )
        identity_of(self.past)

        self.entity_team = Team.objects.create(
            name="CVS S&#39;ANGLADA SOLLER", federation_id='t-entity',
            club=self.club, category=self.infantil,
        )
        TeamIdentity.objects.filter(pk=identity_of(self.entity_team).pk).update(
            core_name="CVS S&#39;ANGLADA SOLLER",
            core_name_normalized='cvs sanglada soller',
        )
        self.entity_team.identity.refresh_from_db()

        for team, season in (
            (self.current_a, self.current_season),
            (self.current_b, self.current_season),
            (self.past, self.past_season),
            (self.entity_team, self.current_season),
        ):
            league = League.objects.create(
                name=f'L {team.federation_id}',
                federation_id=f'L-{team.federation_id}',
                season=season,
            )
            Standing.objects.create(league=league, team=team, position=1)

    def _team_field(self):
        form = self.NotificationPreferencesForm(user=self.user, organization=self.org)
        return form.fields[f'followed_teams_{self.org.id}']

    def test_one_choice_per_identity_of_current_season_only(self):
        choices = list(self._team_field().queryset)
        self.assertEqual(len(choices), 2)
        self.assertNotIn(self.past, choices)
        self.assertTrue(
            {self.current_a, self.current_b} & set(choices),
            'debe quedar una de las dos apariciones actuales de la misma identidad',
        )
        self.assertIn(self.entity_team, choices)

    def test_labels_unescape_html_entities_and_stay_distinct(self):
        field = self._team_field()
        labels = {team.pk: field.label_from_instance(team) for team in field.queryset}
        self.assertNotIn('&#39;', labels[self.entity_team.pk])
        self.assertIn("S'ANGLADA", labels[self.entity_team.pk])
