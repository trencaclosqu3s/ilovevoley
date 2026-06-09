from django.db import migrations


def disable_friendly_endpoints(apps, schema_editor):
    ScrapingEndpoint = apps.get_model('videos', 'ScrapingEndpoint')
    updated = ScrapingEndpoint.objects.filter(
        league__competition_type='friendly',
        is_active=True,
    ).update(is_active=False)
    if updated:
        print(f'  Desactivados {updated} endpoints de ligas amistosas')


class Migration(migrations.Migration):

    dependencies = [
        ('videos', '0034_data_balears'),
    ]

    operations = [
        migrations.RunPython(disable_friendly_endpoints, migrations.RunPython.noop),
    ]
