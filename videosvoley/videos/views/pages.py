from django.shortcuts import render
from django.utils import timezone


def about(request):
    """Página 'Acerca de' con información del proyecto y del club"""
    context = {
        'title': 'Acerca de - Voleibol Sant Josep',
        'current_year': timezone.now().year,
    }
    return render(request, 'videos/about.html', context)


__all__ = ['about']
