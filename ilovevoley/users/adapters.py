from allauth.account.adapter import DefaultAccountAdapter
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter



class CustomAccountAdapter(DefaultAccountAdapter):
    def add_message(self, request, level, message_template=None, message_context=None, extra_tags="", message=None):
        """
        Suprimir mensajes automáticos de login/logout
        """
        # Lista de mensajes que queremos suprimir
        suppressed_messages = [
            'signed in as',
            'signed out',
            'successfully signed in',
            'successfully signed out',
        ]

        # Si el mensaje contiene alguna frase suprimida, no lo mostramos
        if message:
            message_str = str(message).lower()
            for suppressed in suppressed_messages:
                if suppressed in message_str:
                    return

        # Para el resto de mensajes, usar el comportamiento por defecto
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
    def add_message(self, request, level, message_template=None, message_context=None, extra_tags="", message=None):
        """
        Suprimir mensajes automáticos de login/logout para cuentas sociales
        """
        # Lista de mensajes que queremos suprimir
        suppressed_messages = [
            'signed in as',
            'signed out', 
            'successfully signed in',
            'successfully signed out',
            'account connected',
            'account disconnected',
        ]
        
        # Si el mensaje contiene alguna frase suprimida, no lo mostramos
        if message:
            message_str = str(message).lower()
            for suppressed in suppressed_messages:
                if suppressed in message_str:
                    return
        
        # Para el resto de mensajes, usar el comportamiento por defecto
        super().add_message(request, level, message_template, message_context, extra_tags, message)
    
    def is_auto_signup_allowed(self, request, sociallogin):
        """
        Permitir auto-signup para usuarios de Google
        """
        return True
    
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