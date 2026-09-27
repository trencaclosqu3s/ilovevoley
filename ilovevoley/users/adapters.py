from allauth.account.adapter import DefaultAccountAdapter
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter


# Plantillas de allauth cuyos mensajes informativos no queremos mostrar. La
# ruta de la plantilla es estable entre idiomas; el texto renderizado no.
SUPPRESSED_MESSAGE_TEMPLATES = frozenset({
    "account/messages/logged_in.txt",
    "account/messages/logged_out.txt",
    "socialaccount/messages/account_connected.txt",
    "socialaccount/messages/account_connected_updated.txt",
    "socialaccount/messages/account_disconnected.txt",
})


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