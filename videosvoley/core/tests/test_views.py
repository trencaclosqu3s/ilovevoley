from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.urls import reverse

from videosvoley.core import views as core_views
from videosvoley.videos.views import moderation as vid_moderation
from videosvoley.videos.views import pages as vid_pages


@override_settings(ALLOWED_HOSTS=['ilovevoley.es', 'testclub.ilovevoley.es', 'localhost'])
class LandingViewTest(TestCase):
    def setUp(self):
        from videosvoley.core.models import Organization
        cache.clear()
        self.org = Organization.objects.create(
            slug='testclub', name='Test Club', is_active=True
        )

    def test_tenant_root_redirects_anonymous_to_login(self):
        response = self.client.get('/', HTTP_HOST='testclub.ilovevoley.es')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login/', response.url)
        self.assertIn('next=/content/', response.url)

    def test_root_domain_shows_landing_for_anonymous(self):
        response = self.client.get('/', HTTP_HOST='ilovevoley.es')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Selecciona tu club')

    def test_tenant_root_redirects_authenticated_to_videos(self):
        User = get_user_model()
        user = User.objects.create_user(username='member', password='pass')
        self.client.force_login(user)
        response = self.client.get('/', HTTP_HOST='testclub.ilovevoley.es')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/content/')

    def test_login_page_uses_tenant_brand_color(self):
        self.org.primary_color = '#112233'
        self.org.secondary_color = '#445566'
        self.org.save()
        response = self.client.get('/accounts/login/', HTTP_HOST='testclub.ilovevoley.es')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '--brand: #112233')
        self.assertContains(response, '--brand-dark: #445566')
        self.assertContains(response, "'csj-purple': 'var(--brand)'")


class CoreReExportCompatibilityTest(TestCase):
    """Verifica que las importaciones históricas desde videos sigan funcionando."""

    def test_views_are_reexported(self):
        self.assertIs(vid_pages.about, core_views.about)
        self.assertIs(vid_moderation.moderation_panel, core_views.moderation_panel)
        self.assertIs(vid_moderation.moderation_counts_api, core_views.moderation_counts_api)
        self.assertIs(vid_moderation.approve_user_api, core_views.approve_user_api)
        self.assertIs(vid_moderation.reject_user_api, core_views.reject_user_api)


@override_settings(ALLOWED_HOSTS=['testclub.ilovevoley.es', 'localhost'])
class CoreViewUrlTests(TestCase):
    def setUp(self):
        from videosvoley.core.models import Organization
        from videosvoley.users.models import Membership
        cache.clear()
        self.org = Organization.objects.create(
            slug='testclub', name='Test Club', is_active=True
        )
        User = get_user_model()
        self.superuser = User.objects.create_superuser(
            username='admin_user', password='pass', email='admin@test.com'
        )
        Membership.objects.create(
            user=self.superuser, organization=self.org, is_approved=True, role='admin'
        )
        self.unapproved_user = User.objects.create_user(
            username='pending_user', password='pass', is_approved=False
        )
        Membership.objects.create(
            user=self.unapproved_user, organization=self.org, is_approved=False
        )

    def test_core_about_url_resolves_and_renders(self):
        url = reverse('core:about')
        self.assertEqual(url, '/core/quienes-somos/')
        response = self.client.get(url, HTTP_HOST='testclub.ilovevoley.es')
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'core/about.html')

    def test_core_moderation_panel_url_resolves_and_renders(self):
        self.client.force_login(self.superuser)
        url = reverse('core:moderation_panel')
        self.assertEqual(url, '/core/moderacion/')
        response = self.client.get(url, HTTP_HOST='testclub.ilovevoley.es')
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'core/moderation_panel.html')

    def test_core_moderation_counts_api(self):
        self.client.force_login(self.superuser)
        url = reverse('core:moderation_counts_api')
        self.assertEqual(url, '/core/api/moderation/counts/')
        response = self.client.get(url, HTTP_HOST='testclub.ilovevoley.es')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertIn('total_pending', data)

        # Anónimo recibe 401
        self.client.logout()
        anon_resp = self.client.get(url, HTTP_HOST='testclub.ilovevoley.es')
        self.assertEqual(anon_resp.status_code, 401)

        # Usuario normal recibe 403
        self.client.force_login(self.unapproved_user)
        user_resp = self.client.get(url, HTTP_HOST='testclub.ilovevoley.es')
        self.assertEqual(user_resp.status_code, 403)

    def test_core_approve_user_api(self):
        self.client.force_login(self.superuser)
        url = reverse('core:approve_user_api', args=[self.unapproved_user.id])
        self.assertEqual(url, f'/core/api/users/{self.unapproved_user.id}/approve/')
        response = self.client.post(url, HTTP_HOST='testclub.ilovevoley.es')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['success'])
        self.unapproved_user.refresh_from_db()
        self.assertTrue(self.unapproved_user.is_approved)

    def test_core_reject_user_api(self):
        self.client.force_login(self.superuser)
        url = reverse('core:reject_user_api', args=[self.unapproved_user.id])
        self.assertEqual(url, f'/core/api/users/{self.unapproved_user.id}/reject/')
        response = self.client.post(url, HTTP_HOST='testclub.ilovevoley.es')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['success'])
        self.unapproved_user.refresh_from_db()
        self.assertFalse(self.unapproved_user.is_active)


@override_settings(ALLOWED_HOSTS=[
    'cluba.ilovevoley.es', 'clubb.ilovevoley.es', 'localhost',
])
class TenantManagerModerationTest(TestCase):
    """Un manager/admin del club aprueba y rechaza solo membresías de su organización."""

    def setUp(self):
        from videosvoley.core.models import Organization
        from videosvoley.users.models import Membership

        cache.clear()
        self.org_a = Organization.objects.create(slug='cluba', name='Club A', is_active=True)
        self.org_b = Organization.objects.create(slug='clubb', name='Club B', is_active=True)

        User = get_user_model()
        self.manager = User.objects.create_user(username='manager_a', password='pass')
        Membership.objects.create(
            user=self.manager, organization=self.org_a, is_approved=True, role='manager'
        )
        self.member = User.objects.create_user(username='member_a', password='pass')
        Membership.objects.create(
            user=self.member, organization=self.org_a, is_approved=True, role='member'
        )

        self.pending_a = User.objects.create_user(
            username='pending_a', password='pass', is_approved=False
        )
        Membership.objects.create(
            user=self.pending_a, organization=self.org_a, is_approved=False
        )
        self.pending_b = User.objects.create_user(
            username='pending_b', password='pass', is_approved=False
        )
        Membership.objects.create(
            user=self.pending_b, organization=self.org_b, is_approved=False
        )

    def test_manager_approves_membership_of_own_org(self):
        self.client.force_login(self.manager)
        url = reverse('core:approve_user_api', args=[self.pending_a.id])
        response = self.client.post(url, HTTP_HOST='cluba.ilovevoley.es')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['success'])
        self.pending_a.refresh_from_db()
        self.assertTrue(self.pending_a.is_approved)
        from videosvoley.users.models import Membership
        self.assertTrue(Membership.objects.get(
            user=self.pending_a, organization=self.org_a
        ).is_approved)

    def test_manager_cannot_approve_membership_of_other_org(self):
        self.client.force_login(self.manager)
        url = reverse('core:approve_user_api', args=[self.pending_b.id])
        response = self.client.post(url, HTTP_HOST='cluba.ilovevoley.es')
        self.assertEqual(response.status_code, 404)
        self.pending_b.refresh_from_db()
        self.assertFalse(self.pending_b.is_approved)

    def test_member_without_role_cannot_approve(self):
        self.client.force_login(self.member)
        url = reverse('core:approve_user_api', args=[self.pending_a.id])
        response = self.client.post(url, HTTP_HOST='cluba.ilovevoley.es')
        self.assertEqual(response.status_code, 403)

    def test_manager_reject_denies_membership_without_deactivating_account(self):
        self.client.force_login(self.manager)
        url = reverse('core:reject_user_api', args=[self.pending_a.id])
        response = self.client.post(url, HTTP_HOST='cluba.ilovevoley.es')
        self.assertEqual(response.status_code, 200)
        self.pending_a.refresh_from_db()
        self.assertTrue(self.pending_a.is_active)
        self.assertFalse(self.pending_a.is_approved)
        from videosvoley.users.models import Membership
        self.assertFalse(Membership.objects.filter(
            user=self.pending_a, organization=self.org_a
        ).exists())

    def test_manager_cannot_reject_membership_of_other_org(self):
        self.client.force_login(self.manager)
        url = reverse('core:reject_user_api', args=[self.pending_b.id])
        response = self.client.post(url, HTTP_HOST='cluba.ilovevoley.es')
        self.assertEqual(response.status_code, 404)
        from videosvoley.users.models import Membership
        self.assertTrue(Membership.objects.filter(
            user=self.pending_b, organization=self.org_b
        ).exists())

    def test_manager_panel_only_lists_own_org_and_no_images(self):
        self.client.force_login(self.manager)
        url = reverse('core:moderation_panel')
        response = self.client.get(url, HTTP_HOST='cluba.ilovevoley.es')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'pending_a')
        self.assertNotContains(response, 'pending_b')

    def test_manager_counts_api_scoped_to_tenant(self):
        self.client.force_login(self.manager)
        url = reverse('core:moderation_counts_api')
        response = self.client.get(url, HTTP_HOST='cluba.ilovevoley.es')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['pending_users'], 1)
        self.assertEqual(data['pending_images'], 0)

    def test_member_without_role_cannot_open_panel(self):
        self.client.force_login(self.member)
        response = self.client.get(
            reverse('core:moderation_panel'), HTTP_HOST='cluba.ilovevoley.es'
        )
        self.assertEqual(response.status_code, 403)
