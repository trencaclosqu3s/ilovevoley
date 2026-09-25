from django.conf import settings


def environment_callback(request):
    if settings.DEBUG:
        return ['Desarrollo', 'warning']
    return ['Producción', 'info']


def pending_images_badge(request):
    from ilovevoley.videos.models import Image
    count = Image.objects.filter(status='pending').count()
    return count or None


def pending_users_badge(request):
    from ilovevoley.users.models import User
    count = User.objects.filter(is_approved=False, is_active=True).count()
    return count or None


def pending_memberships_badge(request):
    from ilovevoley.users.models import Membership
    count = Membership.objects.filter(is_approved=False).count()
    return count or None


def is_superuser(request):
    return request.user.is_superuser


def is_staff(request):
    return request.user.is_staff
