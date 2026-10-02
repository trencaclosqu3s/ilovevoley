import pytest
from django.contrib.admin.sites import AdminSite
from ilovevoley.competitions.models import FederationCallUp, CallUpPlayer
from ilovevoley.competitions.admin.callups import CallUpPlayerAdmin
from ilovevoley.core.models import Season


@pytest.mark.django_db
def test_callup_player_admin_confirm_action():
    season = Season.objects.create(name='2025-26', start_year=2025, end_year=2026, is_current=True)
    callup = FederationCallUp.objects.create(season=season, title='Cir', source_url='1.pdf')
    player = CallUpPlayer.objects.create(callup=callup, match_status='suspected')
    admin = CallUpPlayerAdmin(CallUpPlayer, AdminSite())

    admin.confirm_matches(None, CallUpPlayer.objects.filter(pk=player.pk))
    player.refresh_from_db()
    assert player.match_status == 'confirmed'


@pytest.mark.django_db
def test_callup_player_admin_reject_action():
    season = Season.objects.create(name='2025-26', start_year=2025, end_year=2026, is_current=True)
    callup = FederationCallUp.objects.create(season=season, title='Cir', source_url='1.pdf')
    player = CallUpPlayer.objects.create(callup=callup, match_status='suspected')
    admin = CallUpPlayerAdmin(CallUpPlayer, AdminSite())

    admin.reject_matches(None, CallUpPlayer.objects.filter(pk=player.pk))
    player.refresh_from_db()
    assert player.match_status == 'rejected'
