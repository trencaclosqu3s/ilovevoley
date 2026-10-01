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


@pytest.mark.django_db
def test_match_callup_player_gender_conflict():
    season = Season.objects.create(name='2025-26', start_year=2025, end_year=2026, is_current=True)
    club = Club.objects.create(official_name='C.V. Sant Josep', federation_id='102')
    org = Organization.objects.create(name='Sant Josep', slug='sant-josep-2', club=club)
    team = Team.objects.create(name='Cadete Masculino', club=club, federation_id='T102')
    person = Person.objects.create(
        first_name='Marc',
        last_name='Buades Sepulveda',
        birth_date=date(2012, 3, 15),
        organization=org
    )
    PlayerRole.objects.create(person=person, team=team, season=season, is_active=True)

    from ilovevoley.competitions.models import FederationCallUp
    female_callup = FederationCallUp(gender='F', category_name='Cadete')

    # Si la convocatoria es femenina, el jugador masculino no debe coincidir
    res = match_callup_player({
        'club': 'CV SANT JOSEP',
        'first_name': 'MARC',
        'last_name': 'BUADES SEPULVEDA',
        'birth_year': 2012,
    }, season, callup=female_callup)
    assert res['match_status'] == 'unmatched'
    assert res['person'] is None


@pytest.mark.django_db
def test_match_callup_player_name_variants_and_single_surname():
    season = Season.objects.create(name='2025-26', start_year=2025, end_year=2026, is_current=True)
    club = Club.objects.create(official_name='C.V. Sant Josep Obrer', federation_id='103')
    org = Organization.objects.create(name='Sant Josep', slug='sant-josep-3', club=club)
    team = Team.objects.create(name='Infantil Masculino', club=club, federation_id='T103')

    # Ficha dada de alta como "Javi Roca" (1 solo apellido)
    javi = Person.objects.create(
        first_name='Javi',
        last_name='Roca',
        birth_date=date(2012, 5, 10),
        organization=org,
    )
    PlayerRole.objects.create(person=javi, team=team, season=season, is_active=True)

    # Ficha dada de alta como "Joan Pérez"
    joan = Person.objects.create(
        first_name='Joan',
        last_name='Pérez',
        birth_date=date(2012, 1, 1),
        organization=org,
    )
    PlayerRole.objects.create(person=joan, team=team, season=season, is_active=True)

    # 1. PDF con variante Javier y 2 apellidos: JAVIER ROCA PUJOL
    res1 = match_callup_player({
        'club': 'CV SANT JOSEP',
        'first_name': 'JAVIER',
        'last_name': 'ROCA PUJOL',
        'birth_year': 2012,
    }, season)
    assert res1['match_status'] == 'confirmed'
    assert res1['person'] == javi
    assert res1['match_score'] >= 0.85

    # 2. PDF con variante Juan: JUAN PEREZ SASTRE
    res2 = match_callup_player({
        'club': 'CV SANT JOSEP',
        'first_name': 'JUAN',
        'last_name': 'PÉREZ SASTRE',
        'birth_year': 2012,
    }, season)
    assert res2['match_status'] == 'confirmed'
    assert res2['person'] == joan
    assert res2['match_score'] >= 0.85


@pytest.mark.django_db
def test_match_callup_player_club_match_no_roster_card():
    """Un jugador convocado de CV Sant Josep que NO está en la app debe quedar suspected con person=None."""
    season = Season.objects.create(name='2025-26', start_year=2025, end_year=2026, is_current=True)
    club = Club.objects.create(official_name='C.V. Sant Josep Obrer', federation_id='104')
    org = Organization.objects.create(name='Sant Josep', slug='sant-josep-4', club=club)
    team = Team.objects.create(name='Cadete Masculino', club=club, federation_id='T104')

    # Solo existe Marc Buades en el club
    marc = Person.objects.create(
        first_name='Marc',
        last_name='Buades Sepulveda',
        birth_date=date(2012, 3, 15),
        organization=org,
    )
    PlayerRole.objects.create(person=marc, team=team, season=season, is_active=True)

    from ilovevoley.competitions.models import FederationCallUp
    callup = FederationCallUp(gender='M', category_name='Cadete')

    # Llega un convocado de CV SANT JOSEP pero que no existe en el club
    res = match_callup_player({
        'club': 'CV SANT JOSEP',
        'first_name': 'ALEX',
        'last_name': 'SASTRE GOMILA',
        'birth_year': 2012,
    }, season, callup=callup)

    # Debe ser suspected para alertar al manager, pero NUNCA vincular a Marc Buades
    assert res['match_status'] == 'suspected'
    assert res['person'] is None
    assert res['match_score'] == 0.0
    assert res['organization'] == org
    assert 'no tiene ficha' in res['match_notes']

