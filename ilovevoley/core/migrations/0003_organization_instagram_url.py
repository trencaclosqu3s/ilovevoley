from django.db import migrations, models


def set_sant_josep_instagram(apps, schema_editor):
    Organization = apps.get_model('core', 'Organization')
    Organization.objects.filter(slug='santjosep').update(
        instagram_url='https://www.instagram.com/clubvoleisantjosep/',
    )


def clear_sant_josep_instagram(apps, schema_editor):
    Organization = apps.get_model('core', 'Organization')
    Organization.objects.filter(slug='santjosep').update(instagram_url='')


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0002_alter_organization_options_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='organization',
            name='instagram_url',
            field=models.URLField(blank=True, help_text='URL del perfil de Instagram del club'),
        ),
        migrations.RunPython(set_sant_josep_instagram, clear_sant_josep_instagram),
    ]
