from django.db import migrations

from videosvoley.teams.services import MATCH_THRESHOLD, find_best_club


def backfill_team_club(apps, schema_editor):
    """Asigna Club a los equipos huérfanos por coincidencia de nombre.

    Idempotente: solo toca equipos con ``club`` nulo y reutiliza el mismo
    matcher que el scraping (``scrape_clubs --match-teams``).
    """
    Team = apps.get_model('teams', 'Team')
    Club = apps.get_model('teams', 'Club')

    clubs = list(Club.objects.all())
    if not clubs:
        return

    for team in Team.objects.filter(club__isnull=True).iterator():
        match = find_best_club(team.name, clubs)
        if match and match[1] >= MATCH_THRESHOLD:
            team.club = match[0]
            team.save(update_fields=['club'])


class Migration(migrations.Migration):

    dependencies = [
        ('teams', '0002_alter_team_category'),
    ]

    operations = [
        migrations.RunPython(backfill_team_club, migrations.RunPython.noop),
    ]
