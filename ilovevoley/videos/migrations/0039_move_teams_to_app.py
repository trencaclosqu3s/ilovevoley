from django.db import migrations, models
import django.db.models.deletion


def update_contenttypes(apps, schema_editor):
    ContentType = apps.get_model('contenttypes', 'ContentType')
    ContentType.objects.filter(
        app_label='videos',
        model__in=['club', 'team']
    ).update(app_label='teams')


def revert_contenttypes(apps, schema_editor):
    ContentType = apps.get_model('contenttypes', 'ContentType')
    ContentType.objects.filter(
        app_label='teams',
        model__in=['club', 'team']
    ).update(app_label='videos')


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0005_alter_organization_club'),
        ('rosters', '0002_alter_player_team_alter_playerrole_team_and_more'),
        ('teams', '0001_initial'),
        ('videos', '0038_move_content_to_app'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.RemoveField(
                    model_name='team',
                    name='club',
                ),
                migrations.RemoveField(
                    model_name='team',
                    name='category',
                ),
                migrations.RemoveField(
                    model_name='team',
                    name='parent_team',
                ),
                migrations.AlterField(
                    model_name='match',
                    name='away_team',
                    field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='away_matches', to='teams.team'),
                ),
                migrations.AlterField(
                    model_name='standing',
                    name='team',
                    field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='standings', to='teams.team'),
                ),
                migrations.AlterField(
                    model_name='match',
                    name='home_team',
                    field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='home_matches', to='teams.team'),
                ),
                migrations.DeleteModel(
                    name='Club',
                ),
                migrations.DeleteModel(
                    name='Team',
                ),
            ],
            database_operations=[],
        ),
        migrations.RunPython(update_contenttypes, revert_contenttypes),
    ]
