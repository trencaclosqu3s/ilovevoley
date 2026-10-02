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

    def test_base_domain_resolves_to_ilovevoley_brand_colors(self):
        context = self._context(user=None, tenant=None)

        self.assertEqual(context['tenant_color'], '#01696f')
        self.assertEqual(context['tenant_color_dark'], '#004d52')
        self.assertEqual(context['tenant_gradient_from'], '#01696f')
        self.assertEqual(context['tenant_gradient_to'], '#004d52')
        self.assertEqual(context['tenant_gradient_from_rgb'], '1 105 111')
        self.assertEqual(context['tenant_gradient_to_rgb'], '0 77 82')

    def test_sant_josep_tenant_resolves_to_yellow_gradient(self):
        from ilovevoley.core.models import Organization

        org = Organization(
            slug='santjosep',
            name='Club Sant Josep',
            primary_color='#9B7FBF',
            secondary_color='#7B5FA0',
        )

        context = self._context(user=None, tenant=org)

        self.assertEqual(context['tenant_color'], '#9B7FBF')
        self.assertEqual(context['tenant_color_dark'], '#7B5FA0')
        self.assertEqual(context['tenant_gradient_from'], '#9B7FBF')
        self.assertEqual(context['tenant_gradient_to'], '#F4D47C')
        self.assertEqual(context['tenant_gradient_from_rgb'], '155 127 191')
        self.assertEqual(context['tenant_gradient_to_rgb'], '244 212 124')

    def test_generic_tenant_uses_secondary_color_for_gradient(self):
        from ilovevoley.core.models import Organization

        org = Organization(
            slug='balears',
            name='Selecció Balear',
            primary_color='#C8102E',
            secondary_color='#003DA5',
        )

        context = self._context(user=None, tenant=org)

        self.assertEqual(context['tenant_color'], '#C8102E')
        self.assertEqual(context['tenant_color_dark'], '#003DA5')
        self.assertEqual(context['tenant_gradient_from'], '#C8102E')
        self.assertEqual(context['tenant_gradient_to'], '#003DA5')
        self.assertEqual(context['tenant_gradient_from_rgb'], '200 16 46')
        self.assertEqual(context['tenant_gradient_to_rgb'], '0 61 165')
