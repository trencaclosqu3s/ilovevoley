from django.db.models.signals import post_save
from django.dispatch import receiver
from allauth.account.signals import user_signed_up
from allauth.socialaccount.signals import social_account_added
from django.contrib.auth import get_user_model

User = get_user_model()


@receiver(user_signed_up)
def user_signed_up_handler(request, user, **kwargs):
    """
    Maneja el registro de nuevos usuarios (tanto OAuth como registro normal)
    Los usuarios se crean sin aprobación por defecto
    """
    user.is_approved = False
    user.save()
    print(f"Nuevo usuario registrado: {user.username} - Pendiente de aprobación")


@receiver(social_account_added)
def social_account_added_handler(request, sociallogin, **kwargs):
    """
    Maneja específicamente cuando se añade una cuenta social (Google OAuth)
    """
    user = sociallogin.user
    if not user.is_approved:
        user.is_approved = False
        user.save()
        print(f"Usuario OAuth creado: {user.username} - Pendiente de aprobación")