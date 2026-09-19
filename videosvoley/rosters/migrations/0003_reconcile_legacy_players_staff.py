from django.db import migrations


def reconcile_players_and_staff(apps, schema_editor):
    Person = apps.get_model('rosters', 'Person')
    PlayerRole = apps.get_model('rosters', 'PlayerRole')
    StaffRole = apps.get_model('rosters', 'StaffRole')
    Player = apps.get_model('rosters', 'Player')
    Staff = apps.get_model('rosters', 'Staff')

    # Reconciliar Players
    for player in Player.objects.all():
        first_name = (player.first_name or '').strip()
        last_name = (player.last_name or '').strip()

        # Buscar Person por identidad única o por nombre y apellidos
        person = None
        if player.birth_date:
            person = Person.objects.filter(
                first_name__iexact=first_name,
                last_name__iexact=last_name,
                birth_date=player.birth_date,
            ).first()
        if not person:
            person = Person.objects.filter(
                first_name__iexact=first_name,
                last_name__iexact=last_name,
            ).first()

        if not person:
            person = Person.objects.create(
                first_name=first_name,
                last_name=last_name,
                birth_date=player.birth_date,
                photo=player.photo,
                user=player.user,
                notes=player.notes or '',
                is_active=player.is_active,
                created_at=player.created_at,
            )

        # Crear PlayerRole si no existe para ese equipo
        if not PlayerRole.objects.filter(person=person, team=player.team).exists():
            PlayerRole.objects.create(
                person=person,
                team=player.team,
                jersey_number=player.jersey_number,
                position=player.position,
                is_active=player.is_active,
                notes=player.notes or '',
                created_at=player.created_at,
            )

    # Reconciliar Staff
    for staff in Staff.objects.all():
        first_name = (staff.first_name or '').strip()
        last_name = (staff.last_name or '').strip()

        person = Person.objects.filter(
            first_name__iexact=first_name,
            last_name__iexact=last_name,
        ).first()

        if not person:
            person = Person.objects.create(
                first_name=first_name,
                last_name=last_name,
                birth_date=None,
                photo=staff.photo,
                email=staff.email or '',
                phone=staff.phone or '',
                user=staff.user,
                notes=staff.notes or '',
                is_active=staff.is_active,
                created_at=staff.created_at,
            )
        else:
            updated = False
            if not person.email and staff.email:
                person.email = staff.email
                updated = True
            if not person.phone and staff.phone:
                person.phone = staff.phone
                updated = True
            if not person.photo and staff.photo:
                person.photo = staff.photo
                updated = True
            if updated:
                person.save()

        # Crear StaffRole si no existe
        if not StaffRole.objects.filter(person=person, team=staff.team, role=staff.role).exists():
            StaffRole.objects.create(
                person=person,
                team=staff.team,
                role=staff.role,
                is_active=staff.is_active,
                notes=staff.notes or '',
                created_at=staff.created_at,
            )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('rosters', '0002_alter_player_team_alter_playerrole_team_and_more'),
    ]

    operations = [
        migrations.RunPython(reconcile_players_and_staff, noop_reverse),
    ]
