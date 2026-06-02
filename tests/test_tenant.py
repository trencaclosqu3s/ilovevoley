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
