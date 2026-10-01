import pytest
from datetime import date
from django.utils import timezone
from ilovevoley.competitions.models import FederationCallUp, CallUpPlayer
from ilovevoley.core.models import Season, Organization
from ilovevoley.rosters.models import Person

@pytest.mark.django_db
def test_create_federation_callup_and_player():
    season = Season.objects.create(name='2025-26', start_year=2025, end_year=2026, is_current=True)
    org = Organization.objects.create(name='Sant Josep', slug='sant-josep')
    person = Person.objects.create(first_name='Lluc Aleix', last_name='Riera Martín', organization=org, birth_date=date(2013, 5, 10))

    callup = FederationCallUp.objects.create(
        season=season,
        title='3ª CONVOCATORIA SELECCIO BALEAR VP INF MASC',
        circular_date=date(2026, 7, 29),
        source_url='1785324870_3735.pdf',
        modality='beach',
        category_name='Infantil',
        gender='M',
        callup_number='3ª',
    )
    assert callup.pk is not None
    assert str(callup) == '3ª CONVOCATORIA SELECCIO BALEAR VP INF MASC'

    player = CallUpPlayer.objects.create(
        callup=callup,
        raw_club='CV SANT JOSEP',
        raw_last_name='RIERA MARTÍN',
        raw_first_name='LLUC',
        raw_birth_year=2013,
        organization=org,
        person=person,
        match_status='confirmed',
        match_score=1.0,
    )
    assert player.pk is not None
    assert player.raw_full_name == 'LLUC RIERA MARTÍN'
    assert player.match_status == 'confirmed'
    assert str(player) == 'LLUC RIERA MARTÍN (CV SANT JOSEP)'
