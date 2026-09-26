from django.db import migrations


def purge_social_tokens(apps, schema_editor):
    """Elimina los tokens de Google almacenados hasta ahora.

    Con SOCIALACCOUNT_STORE_TOKENS=False la aplicación deja de guardar
    access/refresh tokens. Los que quedaban en socialaccount_socialtoken no
    los usa nadie (la suscripción a calendario va por feed iCal), así que se
    purgan para no dejar credenciales de terceros en la base de datos.
    """
    SocialToken = apps.get_model('socialaccount', 'SocialToken')
    SocialToken.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('socialaccount', '0001_initial'),
        ('users', '0010_alter_user_preferred_categories'),
    ]

    operations = [
        migrations.RunPython(purge_social_tokens, migrations.RunPython.noop),
    ]
