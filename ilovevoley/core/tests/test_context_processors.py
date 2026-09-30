from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase

from ilovevoley.core.context_processors import tenant_context


class TenantContextTest(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def _context(self, user=None, tenant=None):
        request = self.factory.get('/')
        request.user = user
        request.tenant = tenant
        return tenant_context(request)

    def test_superuser_without_tenant_keeps_manager_and_admin_flags(self):
        root = get_user_model().objects.create_superuser(username='root', password='pass')

        context = self._context(user=root, tenant=None)

        self.assertTrue(context['is_tenant_manager'])
        self.assertTrue(context['is_tenant_admin'])
        self.assertFalse(context['can_switch_club'])
