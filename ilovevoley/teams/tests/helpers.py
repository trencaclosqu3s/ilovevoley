from ilovevoley.teams.models import TeamIdentity


def identity_of(team):
    """Identidad del equipo, creándola si no tiene: la plantilla cuelga de ella (#447)."""
    if not team.identity_id:
        team.identity = TeamIdentity.objects.create(
            club=team.club,
            category=team.category,
            core_name=team.name,
            core_name_normalized=f'{team.name.lower()} {team.pk}',
        )
        team.save(update_fields=['identity'])
    return team.identity
