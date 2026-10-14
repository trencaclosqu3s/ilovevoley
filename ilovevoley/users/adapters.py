from datetime import timedelta

from allauth.account.adapter import DefaultAccountAdapter
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.conf import settings
from django.http import HttpResponseRedirect
from django.shortcuts import resolve_url
from django.urls import reverse
from django.utils import timezone


# Plantillas de allauth cuyos mensajes informativos no queremos mostrar. La
# ruta de la plantilla es estable entre idiomas; el texto renderizado no.
SUPPRESSED_MESSAGE_TEMPLATES = frozenset({
    "account/messages/logged_in.txt",
    "account/messages/logged_out.txt",
    "socialaccount/messages/account_connected.txt",
    "socialaccount/messages/account_connected_updated.txt",
    "socialaccount/messages/account_disconnected.txt",
})

# Marca en sesión de que el login anterior quedó por debajo del umbral de
# inactividad y conviene repasar el perfil (#544). Se fija en `pre_login`, antes
# de que `django.contrib.auth.login` sobrescriba `last_login`, y se consume en
# `post_login`. Va en sesión y no en el objeto `user` para sobrevivir cuando un
# *stage* de allauth parte el login en más de una petición.
PROFILE_REVIEW_SESSION_KEY = 'profile_review_due_to_inactivity'


class CustomAccountAdapter(DefaultAccountAdapter):
    def add_message(self, request, level, message_template=None, message_context=None, extra_tags="", message=None):
        """
        Suprimir los mensajes automáticos de login/logout y conexión de cuentas.

        La comprobación se hace por la plantilla de origen, no por el texto
        renderizado: el contenido está traducido (LANGUAGE_CODE = 'es-es') y
        comparar cadenas en inglés nunca coincidía.
        """
        if message_template in SUPPRESSED_MESSAGE_TEMPLATES:
            return

        super().add_message(request, level, message_template, message_context, extra_tags, message)

    def pre_login(self, request, user, *, email_verification, signal_kwargs, email, signup, redirect_url):
        """Anota si toca repasar el perfil por haber estado tiempo sin entrar (#544).

        ``django.contrib.auth.login`` sobrescribe ``last_login`` con la marca
        actual antes de que se calcule la redirección, así que el valor anterior
        solo está disponible aquí. El registro en sesión lo consume
        ``post_login``.
        """
        response = super().pre_login(
            request,
            user,
            email_verification=email_verification,
            signal_kwargs=signal_kwargs,
            email=email,
            signup=signup,
            redirect_url=redirect_url,
        )
        if response is None:
            request.session[PROFILE_REVIEW_SESSION_KEY] = self._inactive_since_last_login(user)
        return response

    def post_login(self, request, user, *, email_verification, signal_kwargs, email, signup, redirect_url):
        """Aterriza en el perfil el primer login tras la aprobación o una larga ausencia (#544).

        El perfil solo sustituye al destino cuando este era la home del club; un
        ``next`` explícito (venir de un enlace protegido) manda. En ese caso la
        revisión por aprobación queda pendiente para un login posterior.
        """
        response = super().post_login(
            request,
            user,
            email_verification=email_verification,
            signal_kwargs=signal_kwargs,
            email=email,
            signup=signup,
            redirect_url=redirect_url,
        )
        overdue_review = request.session.pop(PROFILE_REVIEW_SESSION_KEY, False)
        if signup:
            return response
        if not self._is_default_home_destination(request, redirect_url):
            return response
        if not (user.pending_profile_review or overdue_review):
            return response
        if user.pending_profile_review:
            self._consume_pending_profile_review(user)
        return HttpResponseRedirect(reverse('profile'))

    @staticmethod
    def _inactive_since_last_login(user):
        """Si el login anterior queda a umbral o más de distancia (0 lo desactiva)."""
        days = getattr(settings, 'LOGIN_PROFILE_REVIEW_INACTIVITY_DAYS', 0) or 0
        if days <= 0 or user.last_login is None:
            return False
        return timezone.now() - user.last_login >= timedelta(days=days)

    @staticmethod
    def _is_default_home_destination(request, redirect_url):
        """Si allauth iba a mandar al usuario a la home del club.

        Se aceptan tanto la home configurada del tenant como el
        ``LOGIN_REDIRECT_URL`` global (que sin ``next`` es el destino por
        defecto en cualquier club y en el dominio raíz). Así se le respeta una
        ruta explícita a quien llega desde un enlace protegido.
        """
        from allauth.account.utils import get_login_redirect_url

        destination = get_login_redirect_url(request, redirect_url)
        default_homes = {resolve_url(settings.LOGIN_REDIRECT_URL)}
        tenant = getattr(request, 'tenant', None)
        if tenant is not None:
            default_homes.add(reverse(tenant.home_url_name))
        return destination in default_homes

    @staticmethod
    def _consume_pending_profile_review(user):
        from django.contrib.auth import get_user_model

        get_user_model().objects.filter(pk=user.pk).update(pending_profile_review=False)
        user.pending_profile_review = False

    def save_user(self, request, user, form, commit=True):
        """
        Guardar usuario y crear Membership para el tenant actual
        """
        user = super().save_user(request, user, form, commit=commit)
        if commit and getattr(request, 'tenant', None):
            from ilovevoley.users.models import Membership
            Membership.objects.get_or_create(
                user=user,
                organization=request.tenant,
                defaults={'role': 'member', 'is_approved': False},
            )
        return user


class CustomSocialAccountAdapter(DefaultSocialAccountAdapter):
    def is_auto_signup_allowed(self, request, sociallogin):
        """
        Permitir auto-signup para usuarios de Google
        """
        return True

    def authenticate_by_email(self, sociallogin):
        """
        Solo autenticar contra una cuenta local si su email está verificado.

        Evita el pre-secuestro: un atacante puede registrar el email de una
        víctima sin verificar y esperar a que la víctima entre con Google para
        absorber ese login. Si el email local no está verificado, no se
        reutiliza esa cuenta y el login social sigue su flujo normal, sin
        vincularse silenciosamente.
        """
        from allauth.account.models import EmailAddress

        result = super().authenticate_by_email(sociallogin)
        if not result:
            return None
        user, email = result
        is_verified = EmailAddress.objects.filter(
            user=user, email__iexact=email, verified=True
        ).exists()
        return result if is_verified else None
    
    def populate_user(self, request, sociallogin, data):
        """
        Poblar datos del usuario desde la cuenta social
        """
        user = super().populate_user(request, sociallogin, data)
        
        # Extraer información adicional de Google
        if sociallogin.account.provider == 'google':
            extra_data = sociallogin.account.extra_data
            
            # Intentar obtener el nombre completo o crear un username
            if not user.username:
                # Usar el email como base para el username
                email = data.get('email', '')
                if email:
                    username_base = email.split('@')[0]
                    # Asegurar que el username es único
                    from django.contrib.auth import get_user_model
                    User = get_user_model()
                    username = username_base
                    counter = 1
                    while User.objects.filter(username=username).exists():
                        username = f"{username_base}{counter}"
                        counter += 1
                    user.username = username
        
        return user
    
    def save_user(self, request, sociallogin, form=None):
        """
        Guardar el usuario con información adicional del formulario de signup
        """
        user = super().save_user(request, sociallogin, form)

        # Si hay un formulario con parent_info, guardarlo
        if form and hasattr(form, 'cleaned_data'):
            parent_info = form.cleaned_data.get('parent_info', '')
            if parent_info:
                user.parent_info = parent_info
                user.save()

        # Crear Membership para el tenant actual
        if getattr(request, 'tenant', None):
            from ilovevoley.users.models import Membership
            Membership.objects.get_or_create(
                user=user,
                organization=request.tenant,
                defaults={'role': 'member', 'is_approved': False},
            )

        return user