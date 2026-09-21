from django.db import migrations


def create_sant_josep_and_migrate(apps, schema_editor):
    Organization = apps.get_model('core', 'Organization')
    Video = apps.get_model('videos', 'Video')
    Image = apps.get_model('videos', 'Image')
    User = apps.get_model('users', 'User')
    Membership = apps.get_model('users', 'Membership')
    Group = apps.get_model('auth', 'Group')

    org, _ = Organization.objects.get_or_create(
        slug='santjosep',
        defaults={
            'name': 'Club Sant Josep',
            'primary_color': '#9B7FBF',
            'secondary_color': '#7B5FA0',
            'club_team_names': {'Senior': 'SANT JOSEP'},
            'is_active': True,
        }
    )

    Video.objects.filter(organization__isnull=True).update(organization=org)
    Image.objects.filter(organization__isnull=True).update(organization=org)

    try:
        managers_group = Group.objects.get(name='VideoManagers')
        manager_ids = set(managers_group.user_set.values_list('id', flat=True))
    except Group.DoesNotExist:
        manager_ids = set()

    for user in User.objects.all():
        role = 'manager' if user.id in manager_ids else 'member'
        Membership.objects.get_or_create(
            user=user,
            organization=org,
            defaults={'role': role, 'is_approved': user.is_approved},
        )


def reverse_migration(apps, schema_editor):
    Organization = apps.get_model('core', 'Organization')
    Membership = apps.get_model('users', 'Membership')
    Video = apps.get_model('videos', 'Video')
    Image = apps.get_model('videos', 'Image')
    try:
        org = Organization.objects.get(slug='santjosep')
        Video.objects.filter(organization=org).update(organization=None)
        Image.objects.filter(organization=org).update(organization=None)
        Membership.objects.filter(organization=org).delete()
        org.delete()
    except Organization.DoesNotExist:
        pass


class Migration(migrations.Migration):

    dependencies = [
        ('videos', '0032_video_image_organization'),
        ('core', '0002_alter_organization_options_and_more'),
        ('users', '0008_membership'),
    ]

    operations = [
        migrations.RunPython(create_sant_josep_and_migrate, reverse_migration),
    ]
