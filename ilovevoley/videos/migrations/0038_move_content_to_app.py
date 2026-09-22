from django.db import migrations


def update_contenttypes(apps, schema_editor):
    ContentType = apps.get_model('contenttypes', 'ContentType')
    ContentType.objects.filter(
        app_label='videos',
        model__in=['video', 'comment', 'image']
    ).update(app_label='content')


def revert_contenttypes(apps, schema_editor):
    ContentType = apps.get_model('contenttypes', 'ContentType')
    ContentType.objects.filter(
        app_label='content',
        model__in=['video', 'comment', 'image']
    ).update(app_label='videos')


class Migration(migrations.Migration):

    dependencies = [
        ('videos', '0037_move_rosters_to_app'),
        ('content', '0001_initial'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.RemoveField(
                    model_name='comment',
                    name='user',
                ),
                migrations.RemoveField(
                    model_name='comment',
                    name='video',
                ),
                migrations.RemoveIndex(
                    model_name='image',
                    name='videos_imag_status_4a5f9f_idx',
                ),
                migrations.RemoveIndex(
                    model_name='image',
                    name='videos_imag_match_i_ad5ca3_idx',
                ),
                migrations.RemoveIndex(
                    model_name='image',
                    name='videos_imag_year_e48770_idx',
                ),
                migrations.RemoveIndex(
                    model_name='image',
                    name='videos_imag_upload__b5adc6_idx',
                ),
                migrations.RemoveIndex(
                    model_name='image',
                    name='videos_imag_image_t_6f0bde_idx',
                ),
                migrations.RemoveIndex(
                    model_name='image',
                    name='videos_imag_album_g_2185c3_idx',
                ),
                migrations.RemoveField(
                    model_name='video',
                    name='category',
                ),
                migrations.RemoveField(
                    model_name='video',
                    name='created_by',
                ),
                migrations.RemoveField(
                    model_name='video',
                    name='match',
                ),
                migrations.RemoveField(
                    model_name='video',
                    name='organization',
                ),
                migrations.DeleteModel(
                    name='Comment',
                ),
                migrations.RemoveField(
                    model_name='image',
                    name='categories',
                ),
                migrations.RemoveField(
                    model_name='image',
                    name='match',
                ),
                migrations.RemoveField(
                    model_name='image',
                    name='moderated_by',
                ),
                migrations.RemoveField(
                    model_name='image',
                    name='organization',
                ),
                migrations.RemoveField(
                    model_name='image',
                    name='uploaded_by',
                ),
                migrations.DeleteModel(
                    name='Video',
                ),
                migrations.DeleteModel(
                    name='Image',
                ),
            ],
            database_operations=[],
        ),
        migrations.RunPython(update_contenttypes, revert_contenttypes),
    ]
