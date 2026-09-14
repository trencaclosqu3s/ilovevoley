"""
Custom error handlers.
"""
from django.shortcuts import render


# Custom error handlers
def custom_400(request, exception=None):
    """
    Custom 400 Bad Request error page.
    """
    return render(request, '400.html', status=400)


def custom_403(request, exception=None):
    """
    Custom 403 Forbidden error page.
    """
    return render(request, '403.html', status=403)


def custom_404(request, exception=None):
    """
    Custom 404 Not Found error page.
    """
    return render(request, '404.html', status=404)


def custom_500(request):
    """
    Custom 500 Internal Server Error page.
    """
    return render(request, '500.html', status=500)


# Test views for error pages (only for development)
def test_400(request):
    """Test view for 400 error page."""
    return custom_400(request)


def test_403(request):
    """Test view for 403 error page."""
    return custom_403(request)


def test_404(request):
    """Test view for 404 error page."""
    return custom_404(request)


def test_500(request):
    """Test view for 500 error page."""
    return custom_500(request)


def landing(request):
    """
    Landing page for root domain with organization selection.
    On tenant domains: login if anonymous, /videos/ if authenticated.
    """
    from django.shortcuts import redirect
    from django.urls import reverse
    from videosvoley.core.models import Organization

    if request.tenant:
        if request.user.is_authenticated:
            return redirect('/videos/')
        login_url = reverse('account_login')
        return redirect(f'{login_url}?next=/videos/')

    organizations = Organization.objects.filter(is_active=True).order_by('name')

    user_org_ids = set()
    if request.user.is_authenticated:
        from videosvoley.users.models import Membership
        user_org_ids = set(
            Membership.objects.filter(
                user=request.user, is_approved=True
            ).values_list('organization_id', flat=True)
        )

    return render(request, 'landing.html', {
        'organizations': organizations,
        'user_org_ids': user_org_ids,
    })