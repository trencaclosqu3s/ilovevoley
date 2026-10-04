"""Contrato de ``for_tenant`` y ``get_tenant_object_or_404``.

Protege la decisión de diseño: cada forma de pertenencia (FK ``organization``
o club) resuelve dentro del queryset, y sin tenant no se expone nada.
"""

from django.contrib.auth import get_user_model
from django.http import Http404
from django.test import TestCase
from django.utils import timezone

from ilovevoley.competitions.models import League, Match, Standing
from ilovevoley.content.models import Image, Video
from ilovevoley.core.models import Category, Organization, Season
from ilovevoley.core.tenancy import get_tenant_object_or_404
from ilovevoley.rosters.models import Person, PlayerRole
from ilovevoley.teams.models import Club, Team


class TenantQuerysetTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        season = Season.objects.resolve('2026-2027')
        cls.category = Category.objects.create(name='Senior', is_active=True)

        cls.club_a = Club.objects.create(federation_id='club-a', official_name='Club A')
        cls.club_b = Club.objects.create(federation_id='club-b', official_name='Club B')
        cls.org_a = Organization.objects.create(
            slug='tenant-a', name='Tenant A', club=cls.club_a,
            club_team_names={'Senior': 'Team A'}, is_active=True,
        )
        cls.org_b = Organization.objects.create(
            slug='tenant-b', name='Tenant B', club=cls.club_b,
            club_team_names={'Senior': 'Team B'}, is_active=True,
        )

        cls.team_a = Team.objects.create(
            name='Team A Senior', federation_id='team-a', club=cls.club_a, category=cls.category,
        )
        cls.team_b = Team.objects.create(
            name='Team B Senior', federation_id='team-b', club=cls.club_b, category=cls.category,
        )
        cls.neutral_team = Team.objects.create(
            name='Neutral FC', federation_id='team-neutral', club=None, category=cls.category,
        )

        cls.league_a = League.objects.create(
            name='Liga A', federation_id='liga-a', season=season,
            is_active=True, visibility_type='main', is_our_team_related=True,
        )
        cls.league_b = League.objects.create(
            name='Liga B', federation_id='liga-b', season=season,
            is_active=True, visibility_type='main', is_our_team_related=True,
        )
        cls.match_a = Match.objects.create(
            league=cls.league_a, home_team=cls.team_a, away_team=cls.neutral_team,
            match_date=timezone.now(), status='scheduled',
        )
        cls.match_b = Match.objects.create(
            league=cls.league_b, home_team=cls.team_b, away_team=cls.neutral_team,
            match_date=timezone.now(), status='scheduled',
        )
        cls.withdrawn_a = Match.objects.create(
            league=cls.league_a, home_team=cls.team_a, away_team=cls.neutral_team,
            match_date=timezone.now(), status='withdrawn',
        )
        cls.standing_a = Standing.objects.create(league=cls.league_a, team=cls.team_a, position=1)
        cls.standing_b = Standing.objects.create(league=cls.league_b, team=cls.team_b, position=1)


        cls.user = User.objects.create_user(username='member', password='pass')
        cls.superuser = User.objects.create_superuser(username='root', password='pass')
        cls.video_a = Video.objects.create(
            title='Video A', youtube_url='https://youtu.be/a',
            created_by=cls.user, organization=cls.org_a, season=season,
        )
        cls.video_b = Video.objects.create(
            title='Video B', youtube_url='https://youtu.be/b',
            created_by=cls.user, organization=cls.org_b, season=season,
        )
        cls.video_orphan = Video.objects.create(
            title='Video huérfano', youtube_url='https://youtu.be/c',
            created_by=cls.user, organization=None, season=season,
        )
        cls.image_a = Image.objects.create(
            image='images/a.jpg', title='image-a', uploaded_by=cls.user,
            organization=cls.org_a, season=season,
        )
        cls.image_b = Image.objects.create(
            image='images/b.jpg', title='image-b', uploaded_by=cls.user,
            organization=cls.org_b, season=season,
        )

        cls.person_a = Person.objects.create(
            first_name='Ana', last_name='A',
        )
        cls.person_a.organizations.add(cls.org_a)
        cls.person_b = Person.objects.create(
            first_name='Bea', last_name='B',
        )
        cls.person_b.organizations.add(cls.org_b)
        cls.player_role_a = PlayerRole.objects.create(
            person=cls.person_a, team=cls.team_a, season=season, jersey_number=1,
        )
        cls.player_role_b = PlayerRole.objects.create(
            person=cls.person_b, team=cls.team_b, season=season, jersey_number=1,
        )

    def test_match_for_tenant_includes_own_and_excludes_other(self):
        self.assertEqual(list(Match.objects.for_tenant(self.org_a)), [self.match_a])
        self.assertNotIn(self.match_b, Match.objects.for_tenant(self.org_a))

    def test_match_for_tenant_hides_withdrawn_unless_all_objects(self):
        self.assertNotIn(self.withdrawn_a, Match.objects.for_tenant(self.org_a))
        self.assertIn(self.withdrawn_a, Match.all_objects.for_tenant(self.org_a))

    def test_league_for_tenant_only_returns_own_club_leagues(self):
        self.assertEqual(list(League.objects.for_tenant(self.org_a)), [self.league_a])
        self.assertNotIn(self.league_b, League.objects.for_tenant(self.org_a))

    def test_team_for_tenant_only_returns_own_club_teams(self):
        self.assertEqual(list(Team.objects.for_tenant(self.org_a)), [self.team_a])

    def test_organization_scoped_models_filter_by_fk(self):
        self.assertEqual(list(Video.objects.for_tenant(self.org_a)), [self.video_a])
        self.assertEqual(list(Image.objects.for_tenant(self.org_a)), [self.image_a])
        self.assertEqual(list(Person.objects.for_tenant(self.org_a)), [self.person_a])

    def test_person_roles_inherit_person_tenant(self):
        self.assertEqual(list(PlayerRole.objects.for_tenant(self.org_a)), [self.player_role_a])
        self.assertNotIn(self.player_role_b, PlayerRole.objects.for_tenant(self.org_a))

    def test_person_without_organization_is_hidden(self):
        orphan = Person.objects.create(first_name='Sin', last_name='Club')
        self.assertNotIn(orphan, Person.objects.for_tenant(self.org_a))

    def test_standing_for_tenant_only_returns_own_club_standings(self):
        self.assertEqual(list(Standing.objects.for_tenant(self.org_a)), [self.standing_a])
        self.assertNotIn(self.standing_b, Standing.objects.for_tenant(self.org_a))

    def test_for_tenant_without_tenant_returns_nothing(self):
        self.assertFalse(Match.objects.for_tenant(None).exists())
        self.assertFalse(League.objects.for_tenant(None).exists())
        self.assertFalse(Standing.objects.for_tenant(None).exists())
        self.assertFalse(Video.objects.for_tenant(None).exists())
        self.assertFalse(Team.objects.for_tenant(None).exists())


    def test_object_or_404_returns_own_object(self):
        obj = get_tenant_object_or_404(Video.objects, self.org_a, user=self.user, id=self.video_a.id)
        self.assertEqual(obj, self.video_a)

    def test_object_or_404_raises_for_other_tenant(self):
        with self.assertRaises(Http404):
            get_tenant_object_or_404(
                Video.objects, self.org_a, user=self.user, id=self.video_b.id,
            )

    def test_object_or_404_accepts_model_class(self):
        obj = get_tenant_object_or_404(Video, self.org_a, user=self.user, id=self.video_a.id)
        self.assertEqual(obj, self.video_a)

    def test_object_or_404_bypasses_for_superuser(self):
        obj = get_tenant_object_or_404(
            Video.objects, self.org_a, user=self.superuser, id=self.video_b.id,
        )
        self.assertEqual(obj, self.video_b)
