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