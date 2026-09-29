from django.test import SimpleTestCase, TestCase, override_settings
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from datetime import datetime, timedelta
from email.utils import parseaddr

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
        self.assertIn('--brand-rgb: 17 34 51', content)
        self.assertIn('--brand-dark-rgb: 68 85 102', content)
        self.assertIn('css/app.css', content)
        css_idx = content.find('css/app.css')
        style_idx = content.find('--brand: #112233')
        self.assertLess(css_idx, style_idx, "app.css debe cargarse antes del <style> del tenant")


class CoreReExportCompatibilityTest(SimpleTestCase):
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

    def test_navbar_brand_links_to_configured_home(self):
        self.org.default_home = 'competitions'
        self.org.save()
        response = self.client.get(reverse('core:about'), HTTP_HOST='testclub.ilovevoley.es')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'href="/competitions/ligas/"')

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

    def test_panel_loads_each_script_once_for_manager(self):
        self.client.force_login(self.manager)
        response = self.client.get(
            reverse('core:moderation_panel'), HTTP_HOST='cluba.ilovevoley.es'
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content.count(b'js/lightbox.js'), 1)
        self.assertEqual(response.content.count(b'js/moderation.js'), 1)

    def test_panel_loads_each_script_once_for_superuser(self):
        """base.html ya carga ambos scripts para superusers; el panel no debe
        volver a incluirlos (#209)."""
        superuser = get_user_model().objects.create_superuser(
            username='root', password='pass'
        )
        self.client.force_login(superuser)
        response = self.client.get(
            reverse('core:moderation_panel'), HTTP_HOST='cluba.ilovevoley.es'
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content.count(b'js/lightbox.js'), 1)
        self.assertEqual(response.content.count(b'js/moderation.js'), 1)

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


@override_settings(ALLOWED_HOSTS=['ilovevoley.es', 'localhost'])
class GlobalSuperuserModerationTest(TestCase):
    """Superuser sin subdominio: el rechazo desactiva la cuenta y persiste.

    Un usuario rechazado queda con is_active=False e is_approved=False; el panel
    global debe excluirlo de pendientes para que el rechazo se refleje al
    refrescar (issue #242).
    """

    def setUp(self):
        from ilovevoley.core.models import Organization
        from ilovevoley.users.models import Membership

        cache.clear()
        self.org = Organization.objects.create(
            slug='globalclub', name='Global Club', is_active=True
        )
        User = get_user_model()
        self.superuser = User.objects.create_superuser(
            username='global_root', password='pass', is_approved=True
        )
        self.pending = User.objects.create_user(
            username='global_pending', password='pass', is_approved=False
        )
        Membership.objects.create(
            user=self.pending, organization=self.org, is_approved=False
        )

    def test_reject_persists_and_removes_user_from_pending_panel(self):
        self.client.force_login(self.superuser)

        before = self.client.get(reverse('core:moderation_panel'), HTTP_HOST='localhost')
        self.assertContains(before, 'global_pending')

        url = reverse('core:reject_user_api', args=[self.pending.id])
        response = self.client.post(url, HTTP_HOST='localhost')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['success'])

        self.pending.refresh_from_db()
        self.assertFalse(self.pending.is_active)
        self.assertFalse(self.pending.is_approved)

        panel = self.client.get(reverse('core:moderation_panel'), HTTP_HOST='localhost')
        self.assertEqual(panel.status_code, 200)
        self.assertNotContains(panel, 'global_pending')

        counts = self.client.get(
            reverse('core:moderation_counts_api'), HTTP_HOST='localhost'
        )
        self.assertEqual(counts.json()['pending_users'], 0)


@override_settings(
    ALLOWED_HOSTS=['ilovevoley.es', 'testclub.ilovevoley.es', 'localhost'],
    DEBUG=False,
    SECURE_SSL_REDIRECT=False,
    TENANT_BASE_DOMAIN='ilovevoley.es',
    SECURITY_CONTACT_EMAIL='Seguridad <security@example.com>',
)
class SeoEndpointsTest(TestCase):
    """Endpoints estándar de bots, navegadores y seguridad."""

    def test_robots_txt_allows_landing_and_blocks_private_routes(self):
        response = self.client.get('/robots.txt', HTTP_HOST='ilovevoley.es')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response['Content-Type'].startswith('text/plain'))
        body = response.content.decode()
        self.assertIn('User-agent: *', body)
        for path in (
            '/admin/', '/accounts/', '/media/', '/moderate/',
            '/videos/calendario/suscripcion/',
            '/competitions/calendario/suscripcion/',
        ):
            self.assertIn(f'Disallow: {path}', body)
        self.assertIn('Sitemap: https://ilovevoley.es/sitemap.xml', body)

    def test_sitemap_lists_only_public_pages(self):
        response = self.client.get('/sitemap.xml', HTTP_HOST='ilovevoley.es')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response['Content-Type'].startswith('application/xml'))
        body = response.content.decode()
        self.assertIn('<loc>https://ilovevoley.es/</loc>', body)
        self.assertIn('<loc>https://ilovevoley.es/core/quienes-somos/</loc>', body)
        self.assertNotIn('/content/', body)
        self.assertNotIn('/accounts/', body)

    def test_favicon_redirects_to_static_svg(self):
        response = self.client.get('/favicon.ico', HTTP_HOST='ilovevoley.es')
        self.assertEqual(response.status_code, 301)
        self.assertIn('favicon.svg', response.url)

    def test_security_txt_has_contact_and_future_expiry(self):
        response = self.client.get('/.well-known/security.txt', HTTP_HOST='ilovevoley.es')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response['Content-Type'].startswith('text/plain'))
        body = response.content.decode()
        self.assertIn('Contact: mailto:security@example.com', body)
        expires_line = next(l for l in body.splitlines() if l.startswith('Expires:'))
        expires = datetime.strptime(expires_line.split(': ', 1)[1], '%Y-%m-%dT%H:%M:%SZ')
        self.assertGreater(expires, datetime.now() + timedelta(days=300))

    @override_settings(SECURITY_CONTACT_EMAIL='')
    def test_security_txt_falls_back_to_default_from_email_when_empty(self):
        response = self.client.get('/.well-known/security.txt', HTTP_HOST='ilovevoley.es')
        body = response.content.decode()
        default_address = parseaddr(settings.DEFAULT_FROM_EMAIL)[1]
        self.assertIn(f'Contact: mailto:{default_address}', body)


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
            '429.html',
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

    def test_brand_colors_are_alpha_aware_in_compiled_css(self):
        """La marca debe compilarse como ``rgb(var(--brand-rgb) / <alpha-value>)``.

        Con ``var(--brand)`` a secas las utilidades ``bg-opacity-*`` se ignoran:
        el fondo del equipo propio se pinta sólido y el texto de marca queda
        invisible sobre él (#228).
        """
        css_path = settings.BASE_DIR / 'ilovevoley' / 'static' / 'css' / 'app.css'
        css = css_path.read_text(encoding='utf-8')

        self.assertIn('background-color:rgb(var(--brand-rgb,155 127 191)/var(--tw-bg-opacity,1))', css)
        self.assertIn('color:rgb(var(--brand-rgb,155 127 191)/var(--tw-text-opacity,1))', css)

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


class HealthzViewTest(TestCase):
    def test_healthz_success(self):
        for path in ('/healthz', '/healthz/'):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json(), {'status': 'ok'})

    def test_healthz_database_error(self):
        from unittest.mock import patch
        from django.db import OperationalError

        with patch('django.db.connection.cursor', side_effect=OperationalError('connection refused')):
            response = self.client.get('/healthz')
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.json(), {'status': 'error'})

    @override_settings(
        SECURE_SSL_REDIRECT=True,
        SECURE_REDIRECT_EXEMPT=[r'^healthz/?$'],
        ALLOWED_HOSTS=['localhost', '127.0.0.1', 'testserver'],
    )
    def test_healthz_exempt_from_ssl_redirect(self):
        response = self.client.get('/healthz', secure=False)
        self.assertEqual(response.status_code, 200)


