from django.test import TestCase


class OrganizationModelTest(TestCase):
    def test_create_organization(self):
        from videosvoley.core.models import Organization
        org = Organization.objects.create(
            slug='testclub',
            name='Test Club',
            primary_color='#ff0000',
            club_team_names={'Senior': 'TEST CLUB'},
        )
        self.assertEqual(org.slug, 'testclub')
        self.assertEqual(org.club_team_names['Senior'], 'TEST CLUB')
        self.assertTrue(org.is_active)

    def test_slug_unique(self):
        from videosvoley.core.models import Organization
        from django.db import IntegrityError
        Organization.objects.create(slug='unique', name='A')
        with self.assertRaises(IntegrityError):
            Organization.objects.create(slug='unique', name='B')


class MembershipModelTest(TestCase):
    def setUp(self):
        from videosvoley.core.models import Organization
        from django.contrib.auth import get_user_model
        User = get_user_model()
        self.org = Organization.objects.create(slug='club1', name='Club 1')
        self.user = User.objects.create_user(username='testuser', password='pass')

    def test_create_membership(self):
        from videosvoley.users.models import Membership
        m = Membership.objects.create(
            user=self.user,
            organization=self.org,
            role='member',
            is_approved=False,
        )
        self.assertEqual(m.role, 'member')
        self.assertFalse(m.is_approved)

    def test_unique_user_organization(self):
        from videosvoley.users.models import Membership
        from django.db import IntegrityError
        Membership.objects.create(user=self.user, organization=self.org)
        with self.assertRaises(IntegrityError):
            Membership.objects.create(user=self.user, organization=self.org)
