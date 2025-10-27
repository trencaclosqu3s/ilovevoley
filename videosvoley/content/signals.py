from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone
from .models import Image


@receiver(pre_save, sender=Image)
def image_pre_save(sender, instance, **kwargs):
    """Señales que se ejecutan antes de guardar una imagen"""
    # Auto-asignar año si no está especificado
    if not instance.year:
        instance.year = timezone.now().year


@receiver(post_save, sender=Image)
def image_post_save(sender, instance, created, **kwargs):
    """Señales que se ejecutan después de guardar una imagen"""
    if created and instance.match:
        # Auto-asignar categorías desde el partido si es nueva imagen
        if not instance.categories.exists():
            # Importar el modelo de categoría correcto
            from .models import Category as ContentCategory
            
            if instance.match.league and instance.match.league.category:
                # Buscar la categoría correspondiente en el nuevo modelo
                try:
                    new_category = ContentCategory.objects.get(
                        name=instance.match.league.category.name
                    )
                    instance.categories.add(new_category)
                except ContentCategory.DoesNotExist:
                    pass
            
            # También agregar categorías de los equipos si las tienen
            if instance.match.home_team and instance.match.home_team.category:
                try:
                    new_category = ContentCategory.objects.get(
                        name=instance.match.home_team.category.name
                    )
                    instance.categories.add(new_category)
                except ContentCategory.DoesNotExist:
                    pass
                    
            if instance.match.away_team and instance.match.away_team.category:
                try:
                    new_category = ContentCategory.objects.get(
                        name=instance.match.away_team.category.name
                    )
                    instance.categories.add(new_category)
                except ContentCategory.DoesNotExist:
                    pass