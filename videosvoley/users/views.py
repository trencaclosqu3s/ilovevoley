from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.urls import reverse
from django.views.decorators.http import require_POST
from .forms import UserProfileForm, ParentInfoForm
from .signals import send_new_user_notification


@login_required
def pending_approval(request):
    """Vista para usuarios que están pendientes de aprobación"""
    # Si el usuario ya está aprobado, redirigir a perfil
    if request.user.is_approved:
        print('is approved')
        return redirect('profile')
    print('pos no')
    
    # Si el usuario no tiene parent_info, mostrar formulario para completarlo
    if not request.user.parent_info:
        if request.method == 'POST':
            form = ParentInfoForm(request.POST, instance=request.user)
            if form.is_valid():
                user = form.save()
                
                # Determinar si es usuario OAuth (tiene cuenta social asociada)
                is_oauth = user.socialaccount_set.exists()
                
                # Enviar correo de notificación a admins ahora que tiene parent_info
                send_new_user_notification(user, request, is_oauth=is_oauth)
                
                messages.success(request, 'Información familiar guardada correctamente. Tu cuenta será revisada pronto.')
                return redirect('pending_approval')
        else:
            form = ParentInfoForm(instance=request.user)
        
        return render(request, 'users/pending_approval.html', {
            'user': request.user,
            'form': form,
            'needs_parent_info': True
        })
    
    # Si ya tiene parent_info, solo mostrar mensaje de espera
    return render(request, 'users/pending_approval.html', {
        'user': request.user,
        'needs_parent_info': False
    })


@login_required
def profile_view(request):
    """Vista para visualizar el perfil del usuario"""
    return render(request, 'users/profile.html', {
        'user': request.user
    })


@login_required
def profile_edit(request):
    """Vista para editar el perfil del usuario"""
    if request.method == 'POST':
        form = UserProfileForm(request.POST, request.FILES, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, 'Tu perfil ha sido actualizado correctamente.')
            return redirect('profile')
        else:
            messages.error(request, 'Por favor corrige los errores en el formulario.')
    else:
        form = UserProfileForm(instance=request.user)
    
    return render(request, 'users/profile_edit.html', {
        'form': form
    })


@login_required
@require_POST
def get_calendar_token(request):
    """Vista AJAX para generar y obtener el token de calendario del usuario"""
    try:
        # Generar el token si no existe
        token = request.user.get_or_create_calendar_token()
        
        # Construir la URL completa
        calendar_path = reverse('videos:calendar_feed', args=[token])
        calendar_url = request.build_absolute_uri(calendar_path)
        
        return JsonResponse({
            'success': True,
            'calendar_url': calendar_url,
            'token': token
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@require_POST
def regenerate_calendar_token(request):
    """Vista AJAX para regenerar el token de calendario del usuario"""
    try:
        # Forzar la regeneración del token
        import secrets
        request.user.calendar_token = secrets.token_urlsafe(32)
        request.user.save(update_fields=['calendar_token'])
        
        # Construir la URL completa con el nuevo token
        calendar_path = reverse('videos:calendar_feed', args=[request.user.calendar_token])
        calendar_url = request.build_absolute_uri(calendar_path)
        
        return JsonResponse({
            'success': True,
            'calendar_url': calendar_url,
            'token': request.user.calendar_token
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)