from django.db import migrations


def migrate_category_to_categories(apps, schema_editor):
    League = apps.get_model('competitions', 'League')
    for league in League.objects.filter(category__isnull=False):
        league.categories.add(league.category)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('competitions', '0002_alter_league_categories_alter_league_category'),
    ]

    operations = [
        migrations.RunPython(migrate_category_to_categories, noop_reverse),
    ]
