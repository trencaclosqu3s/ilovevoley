from django.db.models import Q

from ilovevoley.core.models import GENDER_FEMALE, GENDER_MALE, GENDER_MIXED


def match_branches(match):
    """Ramas (géneros) implicadas en un partido.

    Toma el género de las categorías de la liga y el ``effective_gender`` de
    ambos equipos. Devuelve conjunto vacío si nada está clasificado.
    """
    branches = set()
    if match.league_id:
        for category in match.league.categories.all():
            if category.gender:
                branches.add(category.gender)
    for team in (match.home_team, match.away_team):
        if team:
            gender = team.effective_gender
            if gender:
                branches.add(gender)
    return branches


def organization_branch_q(branches):
    """``Q`` que casa organizaciones con alguna de las ramas dadas.

    Devuelve ``None`` si ``branches`` está vacío: sin género conocido no se
    filtra (regla permisiva).
    """
    branches = set(branches)
    if not branches:
        return None
    q = Q()
    if GENDER_MALE in branches:
        q |= Q(has_male_branch=True)
    if GENDER_FEMALE in branches:
        q |= Q(has_female_branch=True)
    if GENDER_MIXED in branches:
        q |= Q(has_mixed_branch=True)
    return q
