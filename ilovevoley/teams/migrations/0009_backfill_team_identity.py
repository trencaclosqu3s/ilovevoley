from django.db import migrations


def forwards(apps, schema_editor):
    from ilovevoley.teams.identity import backfill_team_identities

    backfill_team_identities(
        team_model=apps.get_model('teams', 'Team'),
        identity_model=apps.get_model('teams', 'TeamIdentity'),
        candidate_model=apps.get_model('teams', 'TeamIdentityCandidate'),
        category_model=apps.get_model('core', 'Category'),
    )


class Migration(migrations.Migration):

    dependencies = [
        ('teams', '0008_team_identity'),
        ('core', '0014_backfill_santjosep_gradient_color'),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
