from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model
from django.core.cache import cache


class TenantUtilsTest(TestCase):
    def setUp(self):
        from videosvoley.core.models import Organization
        cache.clear()
        self.org = Organization.objects.create(slug='club', name='Club')
        User = get_user_model()
        self.user = User.objects.create_user(username='member', password='pass')
        from videosvoley.users.models import Membership
        Membership.objects.create(user=self.user, organization=self.org, is_approved=False)

    def test_user_has_approved_membership(self):
        from videosvoley.core.tenant_utils import user_has_approved_membership, approve_user_membership
        self.assertFalse(user_has_approved_membership(self.user, self.org))
        approve_user_membership(self.user, self.org)
        self.assertTrue(user_has_approved_membership(self.user, self.org))

    @override_settings(TENANT_BASE_DOMAIN='localhost:8000', DEBUG=True)
    def test_build_tenant_url(self):
        from videosvoley.core.tenant_utils import build_tenant_url
        self.assertEqual(build_tenant_url('santjosep'), 'http://santjosep.localhost:8000/')

    def test_organization_cache(self):
        from videosvoley.core.tenant_utils import get_organization_by_slug, invalidate_organization_cache
        org = get_organization_by_slug('club')
        self.assertEqual(org, self.org)
        self.org.is_active = False
        self.org.save()
        invalidate_organization_cache('club')
        self.assertIsNone(get_organization_by_slug('club'))
