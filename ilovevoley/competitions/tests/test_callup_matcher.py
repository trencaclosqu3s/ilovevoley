import pytest
from datetime import date
from ilovevoley.core.models import Season, Organization
from ilovevoley.teams.models import Club, Team
from ilovevoley.rosters.models import Person, PlayerRole
from ilovevoley.competitions.services.callup_matcher import match_callup_player


@pytest.mark.django_db
def test_match_callup_player_lluc_variations():
    season = Season.objects.create(name='2025-26', start_year=2025, end_year=2026, is_current=True)
    club = Club.objects.create(official_name='C.V. Sant Josep Obrer', federation_id='101')
    org = Organization.objects.create(name='Sant Josep', slug='sant-josep', club=club, club_team_names={'Infantil': 'SANT JOSEP'})
    team = Team.objects.create(name='Infantil Masculino', club=club, federation_id='T101')
    person = Person.objects.create(
        first_name='Lluc Aleix',
        last_name='Riera Martín',
        birth_date=date(2013, 3, 15),
        organization=org
    )
    PlayerRole.objects.create(person=person, team=team, season=season, is_active=True)

    # 1. Caso real foto: LLUC / RIERA MARTÍN / 2013 / CV SANT JOSEP
    res1 = match_callup_player({
        'club': 'CV SANT JOSEP',
        'first_name': 'LLUC',
        'last_name': 'RIERA MARTÍN',
        'birth_year': 2013
    }, season)
    assert res1['match_status'] == 'confirmed'
    assert res1['person'] == person
    assert res1['organization'] == org
    assert res1['match_score'] >= 0.85

    # 2. Caso solo un apellido: LLUC / RIERA / 2013 / CV SANT JOSEP
    res2 = match_callup_player({
        'club': 'CV SANT JOSEP',
        'first_name': 'LLUC',
        'last_name': 'RIERA',
        'birth_year': 2013
    }, season)
    assert res2['match_status'] == 'confirmed'
    assert res2['person'] == person

    # 3. Caso con errata tipográfica menor: LLUCH / RIERA MARTI con año 2013
    res3 = match_callup_player({
        'club': 'CV SANT JOSEP',
        'first_name': 'LLUCH',
        'last_name': 'RIERA MARTI',
        'birth_year': 2013
    }, season)
    assert res3['match_status'] == 'confirmed'
    assert res3['person'] == person

    # 4. Caso jugador de otro club sin coincidencia
    res4 = match_callup_player({
        'club': 'CV ALGAIDA',
        'first_name': 'ESTER',
        'last_name': 'CARBALLAL',
        'birth_year': 2010
    }, season)
    assert res4['match_status'] == 'unmatched'
    assert res4['person'] is None

    # 5. Caso homónimo de otro club con coincidencia exacta de nombre y año (posible cesión / sospechoso)
    res5 = match_callup_player({
        'club': 'CV ALGAIDA',
        'first_name': 'LLUC ALEIX',
        'last_name': 'RIERA MARTÍN',
        'birth_year': 2013
    }, season)
    assert res5['match_status'] == 'suspected'
    assert res5['person'] == person

    # 6. Caso descuadre de año de nacimiento (>1 año)
    res6 = match_callup_player({
        'club': 'CV SANT JOSEP',
        'first_name': 'LLUC',
        'last_name': 'RIERA',
        'birth_year': 2008  # Ficha es 2013 -> diferencia de 5 años
    }, season)
    assert res6['match_status'] == 'suspected'
    assert 'Descuadre año' in res6['match_notes']
