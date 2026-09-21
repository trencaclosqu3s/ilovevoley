from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0006_user_children'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='user',
            name='calendar_sync_enabled',
        ),
        migrations.RemoveField(
            model_name='user',
            name='calendar_last_sync',
        ),
        migrations.RemoveField(
            model_name='user',
            name='google_calendar_id',
        ),
    ]
