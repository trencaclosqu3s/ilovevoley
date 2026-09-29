from django.test import SimpleTestCase, TestCase, override_settings
from django.contrib.auth import get_user_model
from django.core.cache import cache


class HexToRgbChannelsTest(SimpleTestCase):
    def test_expands_shorthand_and_full_hex(self):
        from ilovevoley.core.tenant_utils import hex_to_rgb_channels

        self.assertEqual(hex_to_rgb_channels('#112233'), '17 34 51')
        self.assertEqual(hex_to_rgb_channels('#aBc'), '170 187 204')

    def test_falls_back_on_missing_or_invalid_value(self):
        from ilovevoley.core.tenant_utils import hex_to_rgb_channels

        self.assertEqual(hex_to_rgb_channels(''), '155 127 191')
        self.assertEqual(hex_to_rgb_channels('not-a-color'), '155 127 191')
        self.assertEqual(hex_to_rgb_channels('#12345', '1 2 3'), '1 2 3')


class TenantUtilsTest(TestCase):
    def setUp(self):
        from ilovevoley.core.models import Organization
        cache.clear()
        self.org = Organization.objects.create(slug='club', name='Club')
        User = get_user_model()
        self.user = User.objects.create_user(username='member', password='pass')
        from ilovevoley.users.models import Membership
        Membership.objects.create(user=self.user, organization=self.org, is_approved=False)

    def test_user_has_approved_membership(self):
        from ilovevoley.core.tenant_utils import user_has_approved_membership, approve_user_membership
        self.assertFalse(user_has_approved_membership(self.user, self.org))
        approve_user_membership(self.user, self.org)
        self.assertTrue(user_has_approved_membership(self.user, self.org))

    @override_settings(TENANT_BASE_DOMAIN='localhost:8000', DEBUG=True)
    def test_build_tenant_url(self):
        from ilovevoley.core.tenant_utils import build_tenant_url
        self.assertEqual(build_tenant_url('santjosep'), 'http://santjosep.localhost:8000/')

    def test_organization_cache(self):
        from ilovevoley.core.tenant_utils import get_organization_by_slug, invalidate_organization_cache
        org = get_organization_by_slug('club')
        self.assertEqual(org, self.org)
        self.org.is_active = False
        self.org.save()
        invalidate_organization_cache('club')
        self.assertIsNone(get_organization_by_slug('club'))

    def test_videomanagers_group_member_without_membership_has_no_tenant_permissions(self):
        from django.contrib.auth.models import Group
        from ilovevoley.core.models import Organization
        from ilovevoley.core.tenant_utils import user_is_tenant_manager, user_is_tenant_staff

        org_b = Organization.objects.create(slug='club-b', name='Club B')
        User = get_user_model()
        vm_user = User.objects.create_user(username='vm_user', password='pass')
        group, _ = Group.objects.get_or_create(name='VideoManagers')
        vm_user.groups.add(group)

        self.assertFalse(user_is_tenant_manager(vm_user, org_b))
        self.assertFalse(user_is_tenant_staff(vm_user, org_b))

    def test_videomanagers_member_with_regular_membership_is_not_manager(self):
        from django.contrib.auth.models import Group
        from ilovevoley.core.models import Organization
        from ilovevoley.core.tenant_utils import user_is_tenant_manager, user_is_tenant_staff
        from ilovevoley.users.models import Membership

        org_b = Organization.objects.create(slug='club-b', name='Club B')
        User = get_user_model()
        vm_user = User.objects.create_user(username='vm_regular', password='pass')
        group, _ = Group.objects.get_or_create(name='VideoManagers')
        vm_user.groups.add(group)
        Membership.objects.create(user=vm_user, organization=org_b, role='member', is_approved=True)

        self.assertFalse(user_is_tenant_manager(vm_user, org_b))
        self.assertFalse(user_is_tenant_staff(vm_user, org_b))

    def test_is_staff_user_with_regular_membership_is_not_tenant_staff(self):
        from ilovevoley.core.tenant_utils import user_is_tenant_manager, user_is_tenant_staff
        from ilovevoley.users.models import Membership

        User = get_user_model()
        staff_user = User.objects.create_user(username='django_staff', password='pass', is_staff=True)
        Membership.objects.create(user=staff_user, organization=self.org, role='member', is_approved=True)

        self.assertFalse(user_is_tenant_staff(staff_user, self.org))
        self.assertFalse(user_is_tenant_manager(staff_user, self.org))

    def test_tenant_manager_has_manager_access_only_in_their_tenant(self):
        from ilovevoley.core.models import Organization
        from ilovevoley.core.tenant_utils import user_is_tenant_manager, user_is_tenant_staff
        from ilovevoley.users.models import Membership

        org_b = Organization.objects.create(slug='club-b', name='Club B')
        User = get_user_model()
        mgr_user = User.objects.create_user(username='mgr_user', password='pass')
        Membership.objects.create(user=mgr_user, organization=self.org, role='manager', is_approved=True)

        self.assertTrue(user_is_tenant_manager(mgr_user, self.org))
        self.assertFalse(user_is_tenant_staff(mgr_user, self.org))
        self.assertFalse(user_is_tenant_manager(mgr_user, org_b))

    def test_tenant_admin_has_both_manager_and_staff_access(self):
        from ilovevoley.core.models import Organization
        from ilovevoley.core.tenant_utils import user_is_tenant_manager, user_is_tenant_staff
        from ilovevoley.users.models import Membership

        org_b = Organization.objects.create(slug='club-b', name='Club B')
        User = get_user_model()
        admin_user = User.objects.create_user(username='admin_user', password='pass')
        Membership.objects.create(user=admin_user, organization=self.org, role='admin', is_approved=True)

        self.assertTrue(user_is_tenant_manager(admin_user, self.org))
        self.assertTrue(user_is_tenant_staff(admin_user, self.org))
        self.assertFalse(user_is_tenant_manager(admin_user, org_b))
        self.assertFalse(user_is_tenant_staff(admin_user, org_b))

    def test_image_is_allowed_permits_tenant_manager_for_pending_image(self):
        from ilovevoley.core.protected_media import _image_is_allowed
        from ilovevoley.content.models import Image
        from ilovevoley.core.models import Season
        from ilovevoley.users.models import Membership

        User = get_user_model()
        mgr = User.objects.create_user(username='mgr_img', password='pass')
        Membership.objects.create(user=mgr, organization=self.org, role='manager', is_approved=True)

        season = Season.objects.resolve('2026-2027')
        image = Image(
            title='Pending test',
            uploaded_by=self.user,
            organization=self.org,
            status='pending',
            season=season,
        )
        self.assertTrue(_image_is_allowed(image, mgr, self.org))


class EnsurePendingMembershipTest(TestCase):
    """Solicitud de acceso de un usuario sin membresía en el tenant (#244)."""

    def setUp(self):
        from ilovevoley.core.models import Organization

        cache.clear()
        self.org = Organization.objects.create(slug='club-x', name='Club X')
        self.user = get_user_model().objects.create_user(username='outsider', password='pass')

    def test_creates_pending_membership_when_missing(self):
        from ilovevoley.core.tenant_utils import ensure_pending_membership

        membership = ensure_pending_membership(self.user, self.org)

        self.assertIsNotNone(membership)
        self.assertEqual(membership.role, 'member')
        self.assertFalse(membership.is_approved)

    def test_returns_none_when_membership_already_exists(self):
        from ilovevoley.core.tenant_utils import ensure_pending_membership
        from ilovevoley.users.models import Membership

        Membership.objects.create(user=self.user, organization=self.org)

        self.assertIsNone(ensure_pending_membership(self.user, self.org))

    def test_skips_superuser_and_missing_tenant(self):
        from ilovevoley.core.tenant_utils import ensure_pending_membership

        root = get_user_model().objects.create_superuser(username='root-x', password='pass')

        self.assertIsNone(ensure_pending_membership(root, self.org))
        self.assertIsNone(ensure_pending_membership(self.user, None))


