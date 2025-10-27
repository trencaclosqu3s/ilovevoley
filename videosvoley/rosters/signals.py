from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone
from .models import Person, PlayerRole, StaffRole


@receiver(pre_save, sender=Person)
def person_pre_save(sender, instance, **kwargs):
    """Señales que se ejecutan antes de guardar una persona"""
    # Normalizar nombres
    if instance.first_name:
        instance.first_name = instance.first_name.strip().title()
    
    if instance.last_name:
        instance.last_name = instance.last_name.strip().title()
    
    # Normalizar email
    if instance.email:
        instance.email = instance.email.strip().lower()
    
    # Normalizar teléfono
    if instance.phone:
        # Remover espacios y caracteres especiales
        instance.phone = ''.join(filter(str.isdigit, instance.phone))


@receiver(post_save, sender=Person)
def person_post_save(sender, instance, created, **kwargs):
    """Señales que se ejecutan después de guardar una persona"""
    if created:
        # Log de creación de persona
        print(f'Nueva persona creada: {instance.full_name}')
        
        # Crear usuario vinculado si es necesario
        create_linked_user_if_needed(instance)


@receiver(pre_save, sender=PlayerRole)
def player_role_pre_save(sender, instance, **kwargs):
    """Señales que se ejecutan antes de guardar un rol de jugador"""
    # Validar número de dorsal
    if instance.jersey_number and (instance.jersey_number < 1 or instance.jersey_number > 99):
        raise ValueError('El número de dorsal debe estar entre 1 y 99')
    
    # Normalizar posición
    if instance.position:
        instance.position = instance.position.strip().lower()


@receiver(post_save, sender=PlayerRole)
def player_role_post_save(sender, instance, created, **kwargs):
    """Señales que se ejecutan después de guardar un rol de jugador"""
    if created:
        # Log de creación de rol de jugador
        print(f'Nuevo rol de jugador creado: {instance.person.full_name} en {instance.team.name}')
        
        # Actualizar estadísticas del equipo si es necesario
        update_team_roster_stats(instance.team)
    
    elif instance.is_active:
        # Si se activa un rol, actualizar estadísticas
        update_team_roster_stats(instance.team)


@receiver(pre_save, sender=StaffRole)
def staff_role_pre_save(sender, instance, **kwargs):
    """Señales que se ejecutan antes de guardar un rol de staff"""
    # Normalizar rol
    if instance.role:
        instance.role = instance.role.strip().lower()


@receiver(post_save, sender=StaffRole)
def staff_role_post_save(sender, instance, created, **kwargs):
    """Señales que se ejecutan después de guardar un rol de staff"""
    if created:
        # Log de creación de rol de staff
        print(f'Nuevo rol de staff creado: {instance.person.full_name} en {instance.team.name}')
        
        # Actualizar estadísticas del equipo si es necesario
        update_team_roster_stats(instance.team)
    
    elif instance.is_active:
        # Si se activa un rol, actualizar estadísticas
        update_team_roster_stats(instance.team)


def create_linked_user_if_needed(person):
    """Crea un usuario vinculado si es necesario"""
    try:
        if not person.user and person.email:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            
            # Verificar si ya existe un usuario con este email
            existing_user = User.objects.filter(email=person.email).first()
            if existing_user:
                person.user = existing_user
                person.save()
                print(f'Usuario existente vinculado: {existing_user.username}')
            else:
                # Crear nuevo usuario
                username = f"{person.first_name.lower()}.{person.last_name.lower()}"
                # Asegurar que el username sea único
                counter = 1
                original_username = username
                while User.objects.filter(username=username).exists():
                    username = f"{original_username}{counter}"
                    counter += 1
                
                user = User.objects.create_user(
                    username=username,
                    email=person.email,
                    first_name=person.first_name,
                    last_name=person.last_name,
                    is_approved=False  # Requiere aprobación
                )
                
                person.user = user
                person.save()
                print(f'Nuevo usuario creado: {username}')
                
    except Exception as e:
        print(f'Error creando usuario vinculado: {e}')


def update_team_roster_stats(team):
    """Actualiza estadísticas de la plantilla del equipo"""
    try:
        # Esta función se puede extender para actualizar estadísticas
        # como número de jugadores, staff, etc.
        active_players = PlayerRole.objects.filter(team=team, is_active=True).count()
        active_staff = StaffRole.objects.filter(team=team, is_active=True).count()
        
        print(f'Estadísticas actualizadas para {team.name}: {active_players} jugadores, {active_staff} staff')
        
    except Exception as e:
        print(f'Error actualizando estadísticas del equipo: {e}')


@receiver(pre_save, sender=Person)
def person_pre_save_validation(sender, instance, **kwargs):
    """Validaciones adicionales antes de guardar una persona"""
    # Validar edad mínima
    if instance.birth_date:
        from datetime import date
        today = date.today()
        age = today.year - instance.birth_date.year - ((today.month, today.day) < (instance.birth_date.month, instance.birth_date.day))
        
        if age < 5:
            raise ValueError('La edad mínima es 5 años')
        if age > 100:
            raise ValueError('La edad máxima es 100 años')


@receiver(pre_save, sender=PlayerRole)
def player_role_pre_save_validation(sender, instance, **kwargs):
    """Validaciones adicionales antes de guardar un rol de jugador"""
    # Validar que no haya duplicados de persona-equipo activos
    if instance.is_active and instance.person_id and instance.team_id:
        existing = PlayerRole.objects.filter(
            person=instance.person,
            team=instance.team,
            is_active=True
        ).exclude(pk=instance.pk)
        
        if existing.exists():
            raise ValueError(f'{instance.person.full_name} ya tiene un rol activo en {instance.team.name}')
    
    # Validar número de dorsal único en el equipo
    if instance.jersey_number and instance.is_active and instance.team_id:
        existing = PlayerRole.objects.filter(
            team=instance.team,
            jersey_number=instance.jersey_number,
            is_active=True
        ).exclude(pk=instance.pk)
        
        if existing.exists():
            raise ValueError(f'El número {instance.jersey_number} ya está en uso en {instance.team.name}')


@receiver(pre_save, sender=StaffRole)
def staff_role_pre_save_validation(sender, instance, **kwargs):
    """Validaciones adicionales antes de guardar un rol de staff"""
    # Validar que no haya duplicados de persona-equipo-rol activos
    if instance.is_active and instance.person_id and instance.team_id and instance.role:
        existing = StaffRole.objects.filter(
            person=instance.person,
            team=instance.team,
            role=instance.role,
            is_active=True
        ).exclude(pk=instance.pk)
        
        if existing.exists():
            raise ValueError(f'{instance.person.full_name} ya tiene el rol de {instance.get_role_display()} activo en {instance.team.name}')