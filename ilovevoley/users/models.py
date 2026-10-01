from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
import secrets


class User(AbstractUser):
    avatar = models.ImageField(upload_to='avatars/', null=True, blank=True)
    is_approved = models.BooleanField(
        default=False,
        help_text='Indica si el usuario ha sido aprobado por un administrador para acceder al contenido.'
    )
    parent_info = models.TextField(
        blank=True,
        verbose_name='Información Familiar',
        help_text='Indica de qué niño/a eres padre/familiar (ej: "papá de Juanito de Infantil")'
    )
    # Calendar subscription token (for .ics feed)
    calendar_token = models.CharField(
        max_length=64,
        unique=True,
        null=True,
        blank=True,
        verbose_name='Token de Suscripción al Calendario',
        help_text='Token único para suscribirse al calendario de partidos vía .ics'
    )
    
    # Relación con fichas de hijos (para padres)
    children = models.ManyToManyField(
        'rosters.Person',
        blank=True,
        related_name='parents',
        verbose_name='Hijos',
        help_text='Fichas de los hijos que puedes editar'
    )

    def __str__(self):
        return self.username

    def save(self, *args, **kwargs):
        # Sanear avatar automáticamente a nivel de modelo ante cualquier nueva subida
        from ilovevoley.videos.utils import sanitize_model_image_field
        sanitize_model_image_field(self, 'avatar', max_size=1024)
        super().save(*args, **kwargs)
    
    def get_or_create_calendar_token(self):
        """Genera un token de calendario si no existe y lo retorna"""
        if not self.calendar_token:
            self.calendar_token = secrets.token_urlsafe(32)
            self.save(update_fields=['calendar_token'])
        return self.calendar_token

    def preferred_categories_for(self, organization):
        """Categorías de interés del usuario en una organización concreta.

        Las preferencias son independientes por club; sin organización activa
        no hay preferencias aplicables.
        """
        if organization is None:
            return Category.objects.none()
        return Category.objects.filter(
            category_preferences__user=self,
            category_preferences__organization=organization,
        )

    def has_preferred_categories(self, organization):
        """Indica si el usuario tiene alguna categoría de interés en un club."""
        return self.preferred_categories_for(organization).exists()

    def profile_organizations(self, tenant=None):
        """Organizaciones del usuario visibles y configurables en su perfil.

        Devuelve las organizaciones activas en las que el usuario tiene
        membresía (aprobada o pendiente). Si no tiene membresías (p. ej.
        superusuario recién creado), devuelve todas las organizaciones activas
        o el tenant activo como fallback.
        """
        orgs = list(
            Organization.objects.filter(
                memberships__user=self,
                is_active=True,
            ).distinct().order_by('name')
        )
        if not orgs:
            if self.is_superuser:
                orgs = list(Organization.objects.filter(is_active=True).order_by('name'))
            elif tenant and getattr(tenant, 'is_active', False):
                orgs = [tenant]
        return orgs

    def can_edit_person(self, person, tenant=None):
        """Verifica si el usuario puede editar una ficha específica."""
        if self.is_superuser:
            return True

        # El propio usuario puede editar su ficha si está vinculada
        if person.user == self:
            return True

        # Los padres pueden editar las fichas de sus hijos
        if self.children.filter(pk=person.pk).exists():
            return True

        # Managers/admins del tenant pueden editar fichas que pertenezcan a su tenant
        tenant = tenant or getattr(person, 'organization', None)
        if tenant:
            from ilovevoley.core.tenant_utils import person_belongs_to_tenant, user_is_tenant_manager
            if user_is_tenant_manager(self, tenant) and person_belongs_to_tenant(person, tenant):
                return True

        return False


from ilovevoley.core.models import Category, Organization


class Membership(models.Model):
    ROLES = [
        ('admin', 'Admin'),
        ('manager', 'Manager'),
        ('member', 'Miembro'),
    ]

    user         = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='memberships')
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='memberships')
    role         = models.CharField(max_length=20, choices=ROLES, default='member')
    is_approved  = models.BooleanField(default=False)
    joined_at    = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'organization')
        verbose_name = 'Membresía'
        verbose_name_plural = 'Membresías'

    def __str__(self):
        return f'{self.user} @ {self.organization} ({self.role})'


class CategoryPreference(models.Model):
    """Categorías de interés de un usuario para una organización concreta.

    Sustituye al antiguo M2M global ``User.preferred_categories`` para que cada
    club mantenga su propio conjunto de categorías sin interferencias.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='category_preferences',
    )
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name='category_preferences',
    )
    categories = models.ManyToManyField(
        Category,
        blank=True,
        related_name='category_preferences',
        verbose_name='Categorías de Interés',
        help_text='Categorías de contenido que deseas ver en este club',
    )

    class Meta:
        unique_together = ('user', 'organization')
        verbose_name = 'Preferencia de categorías'
        verbose_name_plural = 'Preferencias de categorías'

    def __str__(self):
        return f'{self.user} @ {self.organization}'


class WebPushSubscription(models.Model):
    """Suscripción de dispositivo a notificaciones Web Push vinculada a usuario y club."""
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='web_push_subscriptions',
        verbose_name='Usuario',
    )
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name='web_push_subscriptions',
        verbose_name='Organización / Club',
    )
    endpoint = models.TextField(
        unique=True,
        verbose_name='Push Service Endpoint',
        help_text='URL de entrega proporcionada por el servicio Push del navegador (FCM, Apple APNs, etc.)',
    )
    p256dh = models.CharField(
        max_length=255,
        verbose_name='Clave Pública P-256 (Dispositivo)',
    )
    auth = models.CharField(
        max_length=255,
        verbose_name='Token de Autenticación Criptográfica',
    )
    user_agent = models.CharField(
        max_length=500,
        blank=True,
        default='',
        verbose_name='User Agent',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Suscripción Web Push'
        verbose_name_plural = 'Suscripciones Web Push'
        indexes = [
            models.Index(fields=['organization', 'user']),
        ]

    def __str__(self):
        owner = self.user.username if self.user else 'Anónimo'
        return f'{owner} @ {self.organization.name} ({self.endpoint[:30]}...)'
