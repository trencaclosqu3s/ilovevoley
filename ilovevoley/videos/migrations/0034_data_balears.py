from django.db import migrations


def create_balears(apps, schema_editor):
    Organization = apps.get_model('core', 'Organization')
    Organization.objects.get_or_create(
        slug='balears',
        defaults={
            'name': 'Selecció Balear',
            'primary_color': '#C8102E',
            'secondary_color': '#003DA5',
            'club_team_names': {},
            'is_active': True,
        }
    )


def reverse_migration(apps, schema_editor):
    Organization = apps.get_model('core', 'Organization')
    Organization.objects.filter(slug='balears').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('videos', '0033_data_sant_josep'),
        ('core', '0002_alter_organization_options_and_more'),
    ]

    operations = [
        migrations.RunPython(create_balears, reverse_migration),
    ]
