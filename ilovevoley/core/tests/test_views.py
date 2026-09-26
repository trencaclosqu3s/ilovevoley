from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from ilovevoley.content.models import Image
from ilovevoley.core import views as core_views
from ilovevoley.videos.views import moderation as vid_moderation
from ilovevoley.videos.views import pages as vid_pages

TINY_GIF = (
    b'GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!'
    b'\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00'
    b'\x00\x02\x02D\x01\x00;'
)



@override_settings(ALLOWED_HOSTS=['ilovevoley.es', 'testclub.ilovevoley.es', 'localhost'])
class LandingViewTest(TestCase):
    def setUp(self):
        from ilovevoley.core.models import Organization
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

    def test_tenant_root_respects_configured_home(self):
        User = get_user_model()
        user = User.objects.create_user(username='member2', password='pass')
        self.client.force_login(user)
        self.org.default_home = 'images'
        self.org.save()

        response = self.client.get('/', HTTP_HOST='testclub.ilovevoley.es')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/content/imagenes/')

        self.org.default_home = 'competitions'
        self.org.save()
        response = self.client.get('/', HTTP_HOST='testclub.ilovevoley.es')
        self.assertEqual(response.url, '/competitions/ligas/')

    def test_tenant_root_anonymous_next_uses_configured_home(self):
        self.org.default_home = 'images'
        self.org.save()
        response = self.client.get('/', HTTP_HOST='testclub.ilovevoley.es')
        self.assertEqual(response.status_code, 302)
        self.assertIn('next=/content/imagenes/', response.url)

    def test_login_page_uses_tenant_brand_color(self):
        self.org.primary_color = '#112233'
        self.org.secondary_color = '#445566'
        self.org.save()
        response = self.client.get('/accounts/login/', HTTP_HOST='testclub.ilovevoley.es')
        self.assertEqual(response.status_code, 200)
        content = response.content.decode('utf-8')
        self.assertIn('--brand: #112233', content)
        self.assertIn('--brand-dark: #445566', content)
        self.assertIn('css/app.css', content)
        css_idx = content.find('css/app.css')
        style_idx = content.find('--brand: #112233')
        self.assertLess(css_idx, style_idx, "app.css debe cargarse antes del <style> del tenant")


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
        from ilovevoley.core.models import Organization
        from ilovevoley.users.models import Membership
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

    def test_navbar_brand_links_to_configured_home(self):
        self.org.default_home = 'competitions'
        self.org.save()
        response = self.client.get(reverse('core:about'), HTTP_HOST='testclub.ilovevoley.es')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'href="/competitions/ligas/"')

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
        from ilovevoley.core.models import Organization
        from ilovevoley.users.models import Membership

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
        from ilovevoley.users.models import Membership
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
        from ilovevoley.users.models import Membership
        self.assertFalse(Membership.objects.filter(
            user=self.pending_a, organization=self.org_a
        ).exists())

    def test_manager_cannot_reject_membership_of_other_org(self):
        self.client.force_login(self.manager)
        url = reverse('core:reject_user_api', args=[self.pending_b.id])
        response = self.client.post(url, HTTP_HOST='cluba.ilovevoley.es')
        self.assertEqual(response.status_code, 404)
        from ilovevoley.users.models import Membership
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

    def test_manager_panel_scopes_pending_images_to_tenant(self):
        img_a = Image.objects.create(
            image=SimpleUploadedFile('a.jpg', TINY_GIF, content_type='image/jpeg'),
            title='Imagen A',
            uploaded_by=self.manager,
            organization=self.org_a,
            status='pending',
        )
        img_b = Image.objects.create(
            image=SimpleUploadedFile('b.jpg', TINY_GIF, content_type='image/jpeg'),
            title='Imagen B',
            uploaded_by=self.pending_b,
            organization=self.org_b,
            status='pending',
        )
        self.client.force_login(self.manager)
        url = reverse('core:moderation_panel')
        response = self.client.get(url, HTTP_HOST='cluba.ilovevoley.es')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['can_moderate_images'])
        pending_images = list(response.context['pending_images'])
        self.assertIn(img_a, pending_images)
        self.assertNotIn(img_b, pending_images)
        self.assertEqual(response.context['pending_images_count'], 1)

    def test_manager_counts_api_scopes_pending_images_to_tenant(self):
        Image.objects.create(
            image=SimpleUploadedFile('a.jpg', TINY_GIF, content_type='image/jpeg'),
            title='Imagen A',
            uploaded_by=self.manager,
            organization=self.org_a,
            status='pending',
        )
        Image.objects.create(
            image=SimpleUploadedFile('b.jpg', TINY_GIF, content_type='image/jpeg'),
            title='Imagen B',
            uploaded_by=self.pending_b,
            organization=self.org_b,
            status='pending',
        )
        self.client.force_login(self.manager)
        url = reverse('core:moderation_counts_api')
        response = self.client.get(url, HTTP_HOST='cluba.ilovevoley.es')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['pending_images'], 1)
        self.assertEqual(data['pending_users'], 1)
        self.assertEqual(data['total_pending'], 2)

    def test_superuser_on_tenant_subdomain_scopes_pending_images_to_tenant(self):
        User = get_user_model()
        superuser = User.objects.create_superuser(username='super_admin', password='pass')
        img_a = Image.objects.create(
            image=SimpleUploadedFile('a.jpg', TINY_GIF, content_type='image/jpeg'),
            title='Imagen A',
            uploaded_by=self.manager,
            organization=self.org_a,
            status='pending',
        )
        img_b = Image.objects.create(
            image=SimpleUploadedFile('b.jpg', TINY_GIF, content_type='image/jpeg'),
            title='Imagen B',
            uploaded_by=self.pending_b,
            organization=self.org_b,
            status='pending',
        )
        self.client.force_login(superuser)
        url = reverse('core:moderation_panel')
        response = self.client.get(url, HTTP_HOST='cluba.ilovevoley.es')
        self.assertEqual(response.status_code, 200)
        pending_images = list(response.context['pending_images'])
        self.assertIn(img_a, pending_images)
        self.assertNotIn(img_b, pending_images)


class TailwindStaticCssTest(TestCase):
    """Verifica que las plantillas y páginas de error no usan Tailwind Play CDN y cargan el CSS estático compilado."""

    def test_pages_do_not_load_tailwind_play_cdn(self):
        from django.template.loader import render_to_string

        templates_to_check = [
            'base.html',
            'base_auth.html',
            '400.html',
            '403.html',
            '404.html',
            '500.html',
        ]
        context = {
            'tenant_color': '#9B7FBF',
            'tenant_color_dark': '#7B5FA0',
        }

        for tmpl in templates_to_check:
            with self.subTest(template=tmpl):
                rendered = render_to_string(tmpl, context)
                self.assertNotIn(
                    'cdn.tailwindcss.com',
                    rendered,
                    f'Plantilla {tmpl} todavía referencia cdn.tailwindcss.com',
                )
                self.assertIn(
                    'css/app.css',
                    rendered,
                    f'Plantilla {tmpl} no referencia el CSS estático compilado css/app.css',
                )

    def test_compiled_css_file_exists_and_contains_brand_classes(self):
        import pathlib
        from django.conf import settings

        app_css_path = pathlib.Path(settings.BASE_DIR) / 'ilovevoley' / 'static' / 'css' / 'app.css'
        self.assertTrue(app_css_path.exists(), 'El archivo app.css no existe')
        self.assertGreater(app_css_path.stat().st_size, 1024, 'El archivo app.css está vacío o es demasiado pequeño')

        content = app_css_path.read_text(encoding='utf-8')
        self.assertIn('csj-purple', content)

    def test_management_command_tailwind_build(self):
        import pathlib
        from io import StringIO
        from unittest.mock import MagicMock, patch
        from django.core.management import call_command

        out = StringIO()
        fake_bin = pathlib.Path('/fake/bin/tailwindcss')
        fake_result = MagicMock(returncode=0, stderr='')

        with patch('scripts.build_tailwind.ensure_binary', return_value=fake_bin) as mock_ensure, \
             patch('subprocess.run', return_value=fake_result) as mock_run:
            call_command('tailwind', 'build', stdout=out)
            mock_ensure.assert_called_once()
            mock_run.assert_called_once()
            self.assertIn('Tailwind CSS compilado con éxito', out.getvalue())

