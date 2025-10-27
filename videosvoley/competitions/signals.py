from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone
from .models import Match, Standing


@receiver(pre_save, sender=Match)
def match_pre_save(sender, instance, **kwargs):
    """Señales que se ejecutan antes de guardar un partido"""
    # Auto-asignar estado según la fecha
    if instance.match_date and not instance.pk:
        now = timezone.now()
        if instance.match_date < now:
            if instance.home_score is not None and instance.away_score is not None:
                instance.status = 'finished'
            else:
                instance.status = 'scheduled'  # Partido pasado sin resultado


@receiver(post_save, sender=Match)
def match_post_save(sender, instance, created, **kwargs):
    """Señales que se ejecutan después de guardar un partido"""
    if instance.league and instance.status == 'finished':
        # Actualizar clasificación cuando se finaliza un partido
        update_standings_for_match(instance)


def update_standings_for_match(match):
    """Actualiza la clasificación de la liga después de un partido"""
    if not match.league or not match.home_team or not match.away_team:
        return
    
    if match.home_score is None or match.away_score is None:
        return
    
    # Obtener o crear clasificaciones para ambos equipos
    home_standing, _ = Standing.objects.get_or_create(
        league=match.league,
        team=match.home_team,
        defaults={'position': 0, 'played': 0, 'won': 0, 'lost': 0}
    )
    
    away_standing, _ = Standing.objects.get_or_create(
        league=match.league,
        team=match.away_team,
        defaults={'position': 0, 'played': 0, 'won': 0, 'lost': 0}
    )
    
    # Actualizar estadísticas del equipo local
    home_standing.played += 1
    if match.home_score > match.away_score:
        home_standing.won += 1
        # Aquí se podrían actualizar más estadísticas detalladas
    else:
        home_standing.lost += 1
    
    home_standing.save()
    
    # Actualizar estadísticas del equipo visitante
    away_standing.played += 1
    if match.away_score > match.home_score:
        away_standing.won += 1
    else:
        away_standing.lost += 1
    
    away_standing.save()
    
    # Recalcular posiciones
    recalculate_standings_positions(match.league)


def recalculate_standings_positions(league):
    """Recalcula las posiciones en la clasificación"""
    standings = Standing.objects.filter(league=league).order_by('-won', '-total_points')
    
    for position, standing in enumerate(standings, 1):
        standing.position = position
        standing.save()