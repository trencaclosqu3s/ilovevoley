import json
import logging

from django.conf import settings
from django.db.models import Q
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponseBadRequest, JsonResponse
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST
from ilovevoley.core.image_utils import InvalidImageError, decode_cropped_image
from ilovevoley.core.models import Organization
from ilovevoley.core.tenant_utils import ensure_pending_membership, user_has_approved_membership
from .forms import UserProfileForm, ParentInfoForm
from .models import WebPushSubscription


@login_required
def pending_approval(request):
    """Vista para usuarios que están pendientes de aprobación"""
    tenant = getattr(request, 'tenant', None)
    if tenant and user_has_approved_membership(request.user, tenant):
        return redirect('profile')
    if not tenant and request.user.is_approved:
        return redirect('profile')

    # Usuario autenticado sin membresía en este club: registra la solicitud para
    # que el admin del tenant tenga algo que aprobar (miembro de otro club o
    # alta con Google resuelta en el dominio raíz).
    if tenant:
        ensure_pending_membership(request.user, tenant)

    # Una cuenta ya activada que entra en un club nuevo "solicita unirse"; una
    # cuenta recién creada simplemente espera su aprobación.
    joining_club = request.user.is_approved

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
            'needs_parent_info': True,
            'joining_club': joining_club,
        })
    
    # Si ya tiene parent_info, solo mostrar mensaje de espera
    return render(request, 'users/pending_approval.html', {
        'user': request.user,
        'needs_parent_info': False,
        'joining_club': joining_club,
    })


@login_required
def profile_view(request):
    """Vista para visualizar el perfil del usuario"""
    user = request.user
    tenant = getattr(request, 'tenant', None)
    orgs = user.profile_organizations(tenant=tenant)

    preferences_by_org = {
        pref.organization_id: list(pref.categories.all())
        for pref in (
            user.category_preferences.filter(organization__in=orgs)
            .prefetch_related('categories')
        )
    }

    from .forms import AVAILABLE_NOTIFICATION_TYPES
    from collections import defaultdict
    disabled_notifications = defaultdict(set)
    for notif_pref in user.notification_preferences.filter(organization__in=orgs, is_enabled=False):
        disabled_notifications[notif_pref.organization_id].add(notif_pref.notification_type)

    organization_preferences = []
    has_any_preferences = False
    for org in orgs:
        categories = preferences_by_org.get(org.id, [])
        disabled = disabled_notifications.get(org.id, set())
        active_notifs = [label for val, label in AVAILABLE_NOTIFICATION_TYPES if val not in disabled]
        if categories:
            has_any_preferences = True
        organization_preferences.append({
            'organization': org,
            'categories': categories,
            'notification_types': active_notifs,
        })


    return render(request, 'users/profile.html', {
        'user': user,
        'organization_preferences': organization_preferences,
        'has_any_preferences': has_any_preferences,
        'preferred_categories': user.preferred_categories_for(tenant),
    })


@login_required
def profile_edit(request):
    """Vista para editar el perfil del usuario"""
    tenant = getattr(request, 'tenant', None)
    if request.method == 'POST':
        form = UserProfileForm(
            request.POST, request.FILES, instance=request.user, organization=tenant
        )
        
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
        form = UserProfileForm(instance=request.user, organization=tenant)
    
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


# ==============================================================================
# Vistas de autenticación protegidas por rate limiting
# ==============================================================================
from allauth.account import views as allauth_views
from django.utils.decorators import method_decorator
from django_ratelimit.decorators import ratelimit
from django_ratelimit.exceptions import Ratelimited
from ilovevoley.core.ratelimit_utils import (
    credential_fingerprint,
    normalize_credential,
    ratelimit_post_email_key,
    ratelimit_post_login_key,
    record_global_failure,
    reset_global_failures,
)
from ilovevoley.core.views import custom_429

logger = logging.getLogger(__name__)


@method_decorator(ratelimit(key='ip', rate='5/m', method='POST', block=True), name='post')
@method_decorator(ratelimit(key=ratelimit_post_login_key, rate='5/m', method='POST', block=True), name='post')
class RatelimitedLoginView(allauth_views.LoginView):
    """
    Inicio de sesión protegido contra fuerza bruta por IP y por usuario/credencial.

    Además del límite per-IP + credencial (PR #200, que evita el DoS de cuenta),
    un contador global por credencial acota la fuerza bruta distribuida desde
    muchas IPs (#202). El contador solo se alimenta de intentos fallidos y se
    resetea con un login correcto: un tercero nunca puede dejar sin acceso a la
    cuenta, por mucho que reparta fallos entre IPs.
    """

    def form_invalid(self, form):
        credential = normalize_credential(self.request.POST.get('login'))
        if credential:
            count = record_global_failure('login', credential)
            # Se toleran hasta AUTH_GLOBAL_LOGIN_FAILURE_THRESHOLD fallos; a
            # partir del siguiente (N+1) los intentos fallidos reciben 429.
            if count > settings.AUTH_GLOBAL_LOGIN_FAILURE_THRESHOLD:
                logger.warning(
                    "auth.global_login_threshold_exceeded credential_fp=%s count=%s",
                    credential_fingerprint(credential),
                    count,
                )
                return custom_429(self.request, exception=Ratelimited())
        return super().form_invalid(form)

    def form_valid(self, form):
        credential = normalize_credential(self.request.POST.get('login'))
        if credential:
            reset_global_failures('login', credential)
        return super().form_valid(form)


@method_decorator(ratelimit(key='ip', rate='3/m', method='POST', block=True), name='post')
class RatelimitedSignupView(allauth_views.SignupView):
    """Registro de usuarios protegido contra creación masiva de cuentas por IP."""
    pass


@method_decorator(ratelimit(key='ip', rate='3/m', method='POST', block=True), name='post')
@method_decorator(ratelimit(key=ratelimit_post_email_key, rate='3/m', method='POST', block=True), name='post')
class RatelimitedPasswordResetView(allauth_views.PasswordResetView):
    """
    Solicitud de recuperación de contraseña limitada por IP y por email destino.

    Un tope global por email (#202) frena el flood distribuido de emails de reset
    desde muchas IPs. Al no existir señal de "acierto" en este flujo, toda
    petición cuenta: se prioriza acotar el envío masivo de correos
    (AUTH_GLOBAL_RESET_THRESHOLD por AUTH_GLOBAL_FAILURE_WINDOW_SECONDS, más
    estricto en volumen que el umbral de login) aunque el coste sea que un
    tercero pueda retrasar el reset de una víctima durante la ventana.
    """

    def form_valid(self, form):
        # La comprobación debe preceder SIEMPRE a super(): allauth dispara el
        # envío del email dentro de su form_valid, así que solo interceptando
        # antes se evita enviar correo en las peticiones bloqueadas.
        email = normalize_credential(form.cleaned_data.get('email'))
        if email:
            # En reset no hay señal de acierto: TODA petición válida cuenta
            # (también las legítimas), por eso el umbral es bajo en volumen.
            count = record_global_failure('reset', email)
            if count > settings.AUTH_GLOBAL_RESET_THRESHOLD:
                logger.warning(
                    "auth.global_reset_threshold_exceeded email_fp=%s count=%s",
                    credential_fingerprint(email),
                    count,
                )
                return custom_429(self.request, exception=Ratelimited())
        return super().form_valid(form)


@method_decorator(ratelimit(key='ip', rate='3/m', method='POST', block=True), name='post')
class RatelimitedPasswordResetFromKeyView(allauth_views.PasswordResetFromKeyView):
    """Establecimiento de contraseña desde enlace firmado protegido por IP."""
    pass


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


@require_GET
def webpush_vapid_key(request):
    """Devuelve la clave pública VAPID para suscripción Web Push en el cliente."""
    public_key = getattr(settings, 'VAPID_PUBLIC_KEY', '')
    return JsonResponse({'public_key': public_key})


@require_POST
def webpush_subscribe(request):
    """Registra o renueva una suscripción de navegador a notificaciones Web Push."""
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return HttpResponseBadRequest('JSON inválido')

    endpoint = (data.get('endpoint') or '').strip()
    raw_keys = data.get('keys')
    keys = raw_keys if isinstance(raw_keys, dict) else {}
    p256dh = (keys.get('p256dh') or '').strip()
    auth = (keys.get('auth') or '').strip()
    user_agent = (data.get('user_agent') or request.META.get('HTTP_USER_AGENT', ''))[:500]

    if not endpoint or not p256dh or not auth:
        return HttpResponseBadRequest('Faltan parámetros obligatorios de la suscripción (endpoint, p256dh, auth)')

    # Determinar tenant: del middleware de organización o fallback al default
    organization = getattr(request, 'tenant', None)
    if not organization:
        organization = Organization.objects.filter(is_active=True).first()

    if not organization:
        return JsonResponse({'success': False, 'error': 'No hay club activo'}, status=400)

    user = request.user if request.user.is_authenticated else None

    # Una suscripción con dueño solo la renueva su dueño; las anónimas pueden reclamarse al iniciar sesión.
    existing = WebPushSubscription.objects.filter(endpoint=endpoint).first()
    if existing and existing.user_id and existing.user_id != getattr(user, 'id', None):
        return JsonResponse({'success': False, 'error': 'Suscripción de otro usuario'}, status=403)

    WebPushSubscription.objects.update_or_create(
        endpoint=endpoint,
        defaults={
            'user': user,
            'organization': organization,
            'p256dh': p256dh,
            'auth': auth,
            'user_agent': user_agent,
        },
    )
    return JsonResponse({'success': True})


@require_POST
def webpush_unsubscribe(request):
    """Elimina una suscripción de navegador."""
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return HttpResponseBadRequest('JSON inválido')

    endpoint = (data.get('endpoint') or '').strip()
    if endpoint:
        qs = WebPushSubscription.objects.filter(endpoint=endpoint)
        if request.user.is_authenticated:
            qs = qs.filter(Q(user=request.user) | Q(user__isnull=True))
        else:
            qs = qs.filter(user__isnull=True)
        qs.delete()

    return JsonResponse({'success': True})