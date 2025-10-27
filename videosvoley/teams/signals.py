from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone
from .models import Team, Club


@receiver(pre_save, sender=Team)
def team_pre_save(sender, instance, **kwargs):
    """Señales que se ejecutan antes de guardar un equipo"""
    # Auto-asignar categoría si no se ha especificado
    if not instance.category and instance.club:
        # Intentar asignar categoría basada en el nombre del equipo
        # Esto es una lógica básica - se puede mejorar
        team_name_lower = instance.name.lower()
        
        if any(keyword in team_name_lower for keyword in ['senior', 'sénior', 'adulto']):
            try:
                from videosvoley.content.models import Category
                category = Category.objects.filter(name__icontains='senior').first()
                if category:
                    instance.category = category
            except:
                pass
        
        elif any(keyword in team_name_lower for keyword in ['juvenil', 'joven']):
            try:
                from videosvoley.content.models import Category
                category = Category.objects.filter(name__icontains='juvenil').first()
                if category:
                    instance.category = category
            except:
                pass
        
        elif any(keyword in team_name_lower for keyword in ['cadete', 'cadet']):
            try:
                from videosvoley.content.models import Category
                category = Category.objects.filter(name__icontains='cadete').first()
                if category:
                    instance.category = category
            except:
                pass


@receiver(post_save, sender=Team)
def team_post_save(sender, instance, created, **kwargs):
    """Señales que se ejecutan después de guardar un equipo"""
    if created:
        # Log de creación de equipo
        print(f'Nuevo equipo creado: {instance.name} (Club: {instance.club})')
        
        # Si es nuestro equipo, actualizar configuración
        if instance.is_our_team:
            update_our_team_configuration(instance)


@receiver(post_save, sender=Club)
def club_post_save(sender, instance, created, **kwargs):
    """Señales que se ejecutan después de guardar un club"""
    if created:
        # Log de creación de club
        print(f'Nuevo club creado: {instance.official_name}')
        
        # Crear equipos por defecto si es necesario
        create_default_teams_for_club(instance)


def update_our_team_configuration(team):
    """Actualiza la configuración de nuestros equipos"""
    try:
        from django.conf import settings
        
        # Obtener configuración actual
        club_team_names = getattr(settings, 'CLUB_TEAM_NAMES', {})
        
        # Agregar nuevo equipo si no existe
        if team.name not in club_team_names.values():
            # En un entorno real, esto requeriría modificar settings.py
            # Por ahora solo log
            print(f'Equipo {team.name} debería agregarse a CLUB_TEAM_NAMES')
            
    except Exception as e:
        print(f'Error actualizando configuración de equipo: {e}')


def create_default_teams_for_club(club):
    """Crea equipos por defecto para un club nuevo"""
    try:
        # Solo crear si el club no tiene equipos
        if club.teams.count() == 0:
            # Crear equipo senior por defecto
            Team.objects.create(
                name=f"{club.official_name} Senior",
                federation_id=f"{club.federation_id}_senior",
                club=club,
                is_active=True
            )
            
            print(f'Equipo senior creado para {club.official_name}')
            
    except Exception as e:
        print(f'Error creando equipos por defecto: {e}')


@receiver(pre_save, sender=Club)
def club_pre_save(sender, instance, **kwargs):
    """Señales que se ejecutan antes de guardar un club"""
    # Normalizar nombre del club
    if instance.official_name:
        instance.official_name = instance.official_name.strip().title()
    
    # Normalizar provincia
    if instance.province:
        instance.province = instance.province.strip().title()
    
    # Normalizar nombre del presidente
    if instance.president:
        instance.president = instance.president.strip().title()


@receiver(pre_save, sender=Team)
def team_pre_save_normalize(sender, instance, **kwargs):
    """Normalizar datos del equipo antes de guardar"""
    # Normalizar nombre del equipo
    if instance.name:
        instance.name = instance.name.strip()
    
    # Normalizar nombre del patrocinador
    if instance.sponsor_name:
        instance.sponsor_name = instance.sponsor_name.strip()