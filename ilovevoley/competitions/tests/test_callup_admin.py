import pytest
from django.contrib.admin.sites import AdminSite
from ilovevoley.competitions.models import FederationCallUp, CallUpPlayer
from ilovevoley.competitions.admin.callups import CallUpPlayerAdmin
from ilovevoley.core.models import Season


@pytest.mark.django_db
@pytest.mark.parametrize('action_name, expected_status', [
    ('confirm_matches', 'confirmed'),
    ('reject_matches', 'rejected'),
])
def test_callup_player_admin_action_updates_status(action_name, expected_status):
    season = Season.objects.create(name='2025-26', start_year=2025, end_year=2026, is_current=True)
    callup = FederationCallUp.objects.create(season=season, title='Cir', source_url='1.pdf')
    player = CallUpPlayer.objects.create(callup=callup, match_status='suspected')
    admin = CallUpPlayerAdmin(CallUpPlayer, AdminSite())

    getattr(admin, action_name)(None, CallUpPlayer.objects.filter(pk=player.pk))

    player.refresh_from_db()
    assert player.match_status == expected_status
