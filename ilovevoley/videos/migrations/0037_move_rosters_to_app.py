from django.db import migrations


def update_contenttypes(apps, schema_editor):
    ContentType = apps.get_model('contenttypes', 'ContentType')
    ContentType.objects.filter(
        app_label='videos',
        model__in=['person', 'playerrole', 'staffrole', 'player', 'staff']
    ).update(app_label='rosters')


def revert_contenttypes(apps, schema_editor):
    ContentType = apps.get_model('contenttypes', 'ContentType')
    ContentType.objects.filter(
        app_label='rosters',
        model__in=['person', 'playerrole', 'staffrole', 'player', 'staff']
    ).update(app_label='videos')


class Migration(migrations.Migration):

    dependencies = [
        ('videos', '0036_set_explicit_db_tables'),
        ('rosters', '0001_initial'),
        ('users', '0009_alter_user_children'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.RemoveIndex(
                    model_name='person',
                    name='videos_pers_last_na_2ba5e4_idx',
                ),
                migrations.RemoveIndex(
                    model_name='person',
                    name='videos_pers_is_acti_a5e18b_idx',
                ),
                migrations.RemoveIndex(
                    model_name='person',
                    name='videos_pers_created_4f369b_idx',
                ),
                migrations.RemoveConstraint(
                    model_name='person',
                    name='unique_person_identity',
                ),
                migrations.AlterUniqueTogether(
                    name='player',
                    unique_together=None,
                ),
                migrations.RemoveIndex(
                    model_name='player',
                    name='videos_play_team_id_22582d_idx',
                ),
                migrations.RemoveIndex(
                    model_name='player',
                    name='videos_play_positio_3227e5_idx',
                ),
                migrations.RemoveIndex(
                    model_name='playerrole',
                    name='videos_play_team_id_b4eaef_idx',
                ),
                migrations.RemoveIndex(
                    model_name='playerrole',
                    name='videos_play_person__7da1a5_idx',
                ),
                migrations.RemoveIndex(
                    model_name='playerrole',
                    name='videos_play_jersey__f60d05_idx',
                ),
                migrations.RemoveIndex(
                    model_name='playerrole',
                    name='videos_play_positio_7dc98c_idx',
                ),
                migrations.RemoveConstraint(
                    model_name='playerrole',
                    name='unique_active_player_role',
                ),
                migrations.RemoveConstraint(
                    model_name='playerrole',
                    name='unique_jersey_number_per_team',
                ),
                migrations.RemoveIndex(
                    model_name='staff',
                    name='videos_staf_team_id_a6dfe4_idx',
                ),
                migrations.RemoveIndex(
                    model_name='staff',
                    name='videos_staf_role_427190_idx',
                ),
                migrations.RemoveIndex(
                    model_name='staffrole',
                    name='videos_staf_team_id_7ddf73_idx',
                ),
                migrations.RemoveIndex(
                    model_name='staffrole',
                    name='videos_staf_person__d528c0_idx',
                ),
                migrations.RemoveIndex(
                    model_name='staffrole',
                    name='videos_staf_role_2f32b9_idx',
                ),
                migrations.RemoveConstraint(
                    model_name='staffrole',
                    name='unique_active_staff_role',
                ),
                migrations.RemoveField(
                    model_name='person',
                    name='user',
                ),
                migrations.RemoveField(
                    model_name='playerrole',
                    name='person',
                ),
                migrations.RemoveField(
                    model_name='playerrole',
                    name='team',
                ),
                migrations.RemoveField(
                    model_name='staff',
                    name='team',
                ),
                migrations.RemoveField(
                    model_name='staff',
                    name='user',
                ),
                migrations.RemoveField(
                    model_name='staffrole',
                    name='person',
                ),
                migrations.RemoveField(
                    model_name='staffrole',
                    name='team',
                ),
                migrations.DeleteModel(
                    name='Player',
                ),
                migrations.DeleteModel(
                    name='PlayerRole',
                ),
                migrations.DeleteModel(
                    name='Staff',
                ),
                migrations.DeleteModel(
                    name='Person',
                ),
                migrations.DeleteModel(
                    name='StaffRole',
                ),
            ],
            database_operations=[],
        ),
        migrations.RunPython(update_contenttypes, revert_contenttypes),
    ]
