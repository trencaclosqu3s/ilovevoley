from django.db import migrations


def update_contenttypes(apps, schema_editor):
    ContentType = apps.get_model('contenttypes', 'ContentType')
    ContentType.objects.filter(
        app_label='videos',
        model__in=['league', 'match', 'standing', 'scrapingendpoint']
    ).update(app_label='competitions')


def revert_contenttypes(apps, schema_editor):
    ContentType = apps.get_model('contenttypes', 'ContentType')
    ContentType.objects.filter(
        app_label='competitions',
        model__in=['league', 'match', 'standing', 'scrapingendpoint']
    ).update(app_label='videos')


class Migration(migrations.Migration):

    dependencies = [
        ('content', '0002_alter_image_match_alter_video_match'),
        ('competitions', '0001_initial'),
        ('videos', '0039_move_teams_to_app'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.RemoveField(
                    model_name='standing',
                    name='league',
                ),
                migrations.RemoveField(
                    model_name='match',
                    name='league',
                ),
                migrations.RemoveField(
                    model_name='scrapingendpoint',
                    name='league',
                ),
                migrations.RemoveField(
                    model_name='match',
                    name='away_team',
                ),
                migrations.RemoveField(
                    model_name='match',
                    name='home_team',
                ),
                migrations.AlterUniqueTogether(
                    name='scrapingendpoint',
                    unique_together=None,
                ),
                migrations.AlterUniqueTogether(
                    name='standing',
                    unique_together=None,
                ),
                migrations.RemoveField(
                    model_name='standing',
                    name='team',
                ),
                migrations.DeleteModel(
                    name='League',
                ),
                migrations.DeleteModel(
                    name='ScrapingEndpoint',
                ),
                migrations.DeleteModel(
                    name='Match',
                ),
                migrations.DeleteModel(
                    name='Standing',
                ),
            ],
            database_operations=[],
        ),
        migrations.RunPython(update_contenttypes, revert_contenttypes),
    ]
