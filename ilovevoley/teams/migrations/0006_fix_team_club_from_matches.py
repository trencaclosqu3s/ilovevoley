from django.db import migrations

from ilovevoley.teams.services import resolve_team_clubs


def fix_team_club_from_matches(apps, schema_editor):
    """Corrige ``Team.club`` con los ids de club federativo de sus partidos (#380).

    Sobrescribe los clubes que asignó el matching difuso por nombre (p. ej. CV
    Mataró → Club Mayurqa). Los equipos sin ids de club en sus partidos (RFEVB) o
    con ids contradictorios no se tocan. Idempotente.
    """
    Team = apps.get_model('teams', 'Team')
    team_clubs = resolve_team_clubs(apps.get_model('competitions', 'Match'), apps.get_model('teams', 'Club'))

    to_fix = []
    for team in Team.objects.filter(pk__in=team_clubs).iterator():
        club = team_clubs[team.pk]
        if team.club_id != club.pk:
            team.club = club
            to_fix.append(team)
    Team.objects.bulk_update(to_fix, ['club'], batch_size=500)


class Migration(migrations.Migration):

    dependencies = [
        ('competitions', '0021_backfill_acta_urls'),
        ('teams', '0005_team_gender'),
    ]

    operations = [
        migrations.RunPython(fix_team_club_from_matches, migrations.RunPython.noop),
    ]
