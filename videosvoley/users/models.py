from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    avatar = models.ImageField(upload_to='avatars/', null=True, blank=True)
    is_approved = models.BooleanField(
        default=False,
        help_text='Indica si el usuario ha sido aprobado por un administrador para acceder al contenido.'
    )

    def __str__(self):
        return self.username
