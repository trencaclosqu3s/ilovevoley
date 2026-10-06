from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils.translation import gettext_lazy as _
import secrets


class User(AbstractUser):
    avatar = models.ImageField(upload_to='avatars/', null=True, blank=True)
    is_approved = models.BooleanField(
        default=False,
        help_text=_('Indica si el usuario ha sido aprobado por un administrador para acceder al contenido.')
    )
    parent_info = models.TextField(
        blank=True,
        verbose_name=_('Información Familiar'),
        help_text=_('Indica de qué niño/a eres padre/familiar (ej: "papá de Juanito de Infantil")')
    )
    # Calendar subscription token (for .ics feed)
    calendar_token = models.CharField(
        max_length=64,
        unique=True,
        null=True,
        blank=True,
        verbose_name=_('Token de Suscripción al Calendario'),
        help_text=_('Token único para suscribirse al calendario de partidos vía .ics')
    )
    
    # Relación con fichas de hijos (para padres)
    children = models.ManyToManyField(
        'rosters.Person',
        blank=True,
        related_name='parents',
        verbose_name=_('Hijos'),
        help_text=_('Fichas de los hijos que puedes editar')
    )

    # Idioma preferido de la interfaz. Los nombres de idioma se muestran en su
    # propio idioma (endónimos), por eso no se traducen.
    preferred_language = models.CharField(
        max_length=5,
        choices=[('es', 'Español'), ('ca', 'Català')],
        blank=True,
        default='',
        verbose_name=_('Idioma preferido'),
        help_text=_('Idioma en el que se muestra la interfaz. Vacío: el del navegador.'),
    )

    # Control de avisos y ciclo de inactividad (#327)
    inactivity_warning_level = models.PositiveSmallIntegerField(
        default=0,
        verbose_name=_('Nivel de aviso de inactividad'),
        help_text=_('0: sin aviso, 1: primer aviso (30 días), 2: aviso final (7 días)'),
    )
    inactivity_warning_sent_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_('Fecha del último aviso de inactividad'),
    )

    # Reentrada a moderación de una cuenta desactivada por inactividad (#327).
    # Solo se rellena cuando la propia persona pide la reactivación; mientras
    # esté a NULL no aparece en el panel y no se avisa a nadie.
    reactivation_requested_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_('Solicitud de reactivación'),
        help_text=_('Fecha en que una cuenta desactivada pidió volver a ser revisada.'),
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
        if tenant:
            from ilovevoley.core.tenant_utils import person_belongs_to_tenant, user_is_tenant_manager
            if user_is_tenant_manager(self, tenant) and person_belongs_to_tenant(person, tenant):
                return True

        return False


from ilovevoley.core.models import Category, Organization


class Membership(models.Model):
    ROLES = [
        ('admin', _('Admin')),
        ('manager', _('Manager')),
        ('member', _('Miembro')),
    ]

    user         = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='memberships')
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='memberships')
    role         = models.CharField(max_length=20, choices=ROLES, default='member')
    is_approved  = models.BooleanField(default=False)
    joined_at    = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'organization')
        verbose_name = _('Membresía')
        verbose_name_plural = _('Membresías')

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
        verbose_name=_('Categorías de Interés'),
        help_text=_('Categorías de contenido que deseas ver en este club'),
    )
    # Con equipos elegidos, los avisos de partido y el iCal de este club se limitan a ellos
    # y las categorías dejan de aplicarse a partidos (siguen filtrando álbumes y contenido).
    teams = models.ManyToManyField(
        'teams.Team',
        blank=True,
        related_name='followers',
        verbose_name=_('Mis equipos'),
    )

    class Meta:
        unique_together = ('user', 'organization')
        verbose_name = _('Preferencia de categorías')
        verbose_name_plural = _('Preferencias de categorías')

    def __str__(self):
        return f'{self.user} @ {self.organization}'


class NotificationType(models.TextChoices):
    MATCH_RESULT = 'match_result', _('Resultados de partidos')
    NEW_ALBUM = 'new_album', _('Nuevos álbumes de fotos')
    MATCH_CHANGE = 'match_change', _('Cambios de horario o pista')
    MATCH_REMINDER = 'match_reminder', _('Recordatorios previos al partido')
    MATCH_MEDIA = 'match_media', _('Fotos y vídeos de partidos')
    MATCH_PHOTOS = 'match_photos', _('Recordatorio para subir fotos del partido')
    IMAGE_TAG = 'image_tag', _('Avisos de etiquetado en fotos')


class NotificationPreference(models.Model):
    """Preferencia de un usuario para recibir un tipo de notificación push en un club concreto."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notification_preferences',
        verbose_name=_('Usuario'),
    )
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name='notification_preferences',
        verbose_name=_('Organización / Club'),
    )
    notification_type = models.CharField(
        max_length=32,
        choices=NotificationType.choices,
        verbose_name=_('Tipo de notificación'),
    )
    is_enabled = models.BooleanField(
        default=True,
        verbose_name=_('Activado'),
        help_text=_('Indica si el usuario desea recibir este tipo de notificación.'),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('user', 'organization', 'notification_type')
        verbose_name = _('Preferencia de notificación')
        verbose_name_plural = _('Preferencias de notificaciones')
        indexes = [
            models.Index(fields=['organization', 'notification_type', 'is_enabled']),
        ]

    def __str__(self):
        state = 'activado' if self.is_enabled else 'desactivado'
        return f'{self.user} @ {self.organization} ({self.notification_type}: {state})'


class WebPushSubscription(models.Model):
    """Suscripción de dispositivo a notificaciones Web Push vinculada a usuario y club."""
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='web_push_subscriptions',
        verbose_name=_('Usuario'),
    )
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name='web_push_subscriptions',
        verbose_name=_('Organización / Club'),
    )
    endpoint = models.TextField(
        unique=True,
        verbose_name=_('Push Service Endpoint'),
        help_text=_('URL de entrega proporcionada por el servicio Push del navegador (FCM, Apple APNs, etc.)'),
    )
    p256dh = models.CharField(
        max_length=255,
        verbose_name=_('Clave Pública P-256 (Dispositivo)'),
    )
    auth = models.CharField(
        max_length=255,
        verbose_name=_('Token de Autenticación Criptográfica'),
    )
    user_agent = models.CharField(
        max_length=500,
        blank=True,
        default='',
        verbose_name=_('User Agent'),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _('Suscripción Web Push')
        verbose_name_plural = _('Suscripciones Web Push')
        indexes = [
            models.Index(fields=['organization', 'user']),
        ]

    def __str__(self):
        owner = self.user.username if self.user else 'Anónimo'
        return f'{owner} @ {self.organization.name} ({self.endpoint[:30]}...)'


class WebPushAudit(models.Model):
    """Auditoría mínima de envíos push por ejecución de tarea (#316).

    No guarda el texto del push ni datos de usuarios. Se limpia periódicamente
    para mantener una retención acotada (90 días).
    """

    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name='web_push_audits',
        verbose_name=_('Organización / Club'),
    )
    notification_type = models.CharField(
        max_length=64,
        blank=True,
        default='',
        verbose_name=_('Tipo de notificación'),
    )
    match_id = models.PositiveIntegerField(
        null=True,
        blank=True,
        db_index=True,
        verbose_name=_('ID de partido'),
    )
    candidates_count = models.PositiveIntegerField(
        default=0,
        verbose_name=_('Dispositivos candidatos'),
    )
    dispatched_count = models.PositiveIntegerField(
        default=0,
        verbose_name=_('Enviados'),
    )
    failed_count = models.PositiveIntegerField(
        default=0,
        verbose_name=_('Fallidos'),
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        verbose_name=_('Fecha'),
    )

    class Meta:
        ordering = ['-created_at']
        verbose_name = _('Auditoría de aviso push')
        verbose_name_plural = _('Auditorías de avisos push')
        indexes = [
            models.Index(fields=['organization', 'notification_type', '-created_at']),
        ]

    def __str__(self):
        type_str = self.notification_type or 'general'
        date_str = self.created_at.strftime('%Y-%m-%d %H:%M') if self.created_at else ''
        return f'{date_str} @ {self.organization.name} ({type_str}): {self.dispatched_count}/{self.candidates_count}'
