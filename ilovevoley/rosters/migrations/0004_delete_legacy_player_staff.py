from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('rosters', '0003_reconcile_legacy_players_staff'),
    ]

    operations = [
        migrations.DeleteModel(
            name='Player',
        ),
        migrations.DeleteModel(
            name='Staff',
        ),
    ]
