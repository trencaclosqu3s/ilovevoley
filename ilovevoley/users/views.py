from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.urls import reverse
from django.views.decorators.http import require_POST
from ilovevoley.core.image_utils import InvalidImageError, decode_cropped_image
from ilovevoley.core.tenant_utils import user_has_approved_membership
from .forms import UserProfileForm, ParentInfoForm


@login_required
def pending_approval(request):
    """Vista para usuarios que están pendientes de aprobación"""
    tenant = getattr(request, 'tenant', None)
    if tenant and user_has_approved_membership(request.user, tenant):
        return redirect('profile')
    if not tenant and request.user.is_approved:
        return redirect('profile')
    
    # Si el usuario no tiene parent_info, mostrar formulario para completarlo
    if not request.user.parent_info:
        if request.method == 'POST':
            form = ParentInfoForm(request.POST, instance=request.user)
            if form.is_valid():
                form.save()

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
            # Procesar imagen recortada si está presente
            cropped_avatar_data = request.POST.get('cropped_avatar_data')
            if cropped_avatar_data:
                try:
                    request.user.avatar = decode_cropped_image(cropped_avatar_data)
                except InvalidImageError as e:
                    messages.error(request, str(e))
                    return render(request, 'users/profile_edit.html', {'form': form})
            
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
        calendar_path = reverse('competitions:calendar_feed', args=[token])
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
        calendar_path = reverse('competitions:calendar_feed', args=[request.user.calendar_token])
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