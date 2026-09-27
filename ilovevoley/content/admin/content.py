import uuid

from django.conf import settings
from django.contrib import admin
from django.contrib.admin import helpers
from django.shortcuts import render
from django.utils import timezone
from django.utils.html import format_html
from unfold.admin import ModelAdmin, TabularInline

from ..models import Video, Image
from ilovevoley.competitions.models import Match


@admin.register(Video)
class VideoAdmin(ModelAdmin):
    list_display = ('title', 'category', 'match', 'set_number', 'created_by', 'created_at')
    list_filter = ('category', 'match__league', 'set_number', 'created_at')
    search_fields = ('title', 'description', 'match__home_team__name', 'match__away_team__name')
    readonly_fields = ('created_at',)
    autocomplete_fields = ('match',)


class ImageInline(TabularInline):
    model = Image
    extra = 0
    readonly_fields = ('thumbnail_preview', 'status', 'uploaded_by', 'upload_date')
    fields = ('thumbnail_preview', 'title', 'status', 'uploaded_by', 'upload_date')

    def thumbnail_preview(self, obj):
        """Miniatura para inline"""
        if obj.image:
            return format_html(
                '<img src="{}" width="40" height="40" style="object-fit: cover; border-radius: 3px;" />',
                obj.image.url
            )
        return '-'
    thumbnail_preview.short_description = 'Img'

    def has_add_permission(self, request, obj=None):
        """No permitir agregar desde inline"""
        return False


@admin.register(Image)
class ImageAdmin(ModelAdmin):
    list_display = ('thumbnail_preview', 'title', 'match', 'set_number', 'album_display', 'categories_display_admin', 'status', 'uploaded_by', 'upload_date', 'moderated_by', 'original_format', 'was_converted')
    list_filter = ('status', 'categories', 'season', 'set_number', 'upload_date', 'match__league', 'was_converted', 'original_format')
    search_fields = ('title', 'description', 'match__home_team__name', 'match__away_team__name', 'album_name')
    readonly_fields = ('upload_date', 'thumbnail_preview', 'vision_api_details', 'moderation_date', 'original_format', 'was_converted')
    date_hierarchy = 'upload_date'
    actions = ['approve_images', 'reject_images', 'check_with_vision_api', 'assign_to_album', 'assign_to_match', 'unassign_album', 'unassign_match']
    filter_horizontal = ('categories',)

    fieldsets = (
        ('Imagen', {
            'fields': ('thumbnail_preview', 'image', 'title', 'description', 'image_type', 'tags', 'original_format', 'was_converted')
        }),
        ('Asociación', {
            'fields': ('match', 'set_number', 'categories', 'season'),
            'description': 'Categorías y temporada se asignan automáticamente desde el partido, pero puedes modificarlas'
        }),
        ('Moderación', {
            'fields': ('status', 'moderated_by', 'moderation_date', 'moderation_notes')
        }),
        ('Google Vision API', {
            'fields': ('vision_api_checked', 'vision_api_safe', 'vision_api_details'),
            'classes': ('collapse',),
            'description': 'Información de verificación automática de contenido'
        }),
        ('Metadata', {
            'fields': ('uploaded_by', 'upload_date'),
            'classes': ('collapse',)
        })
    )

    def thumbnail_preview(self, obj):
        """Muestra miniatura de la imagen"""
        if obj.image:
            return format_html(
                '<img src="{}" width="80" height="80" style="object-fit: cover; border-radius: 4px;" />',
                obj.image.url
            )
        return '-'
    thumbnail_preview.short_description = 'Preview'

    def album_display(self, obj):
        """Muestra el álbum de la imagen"""
        if obj.album_name:
            return obj.album_name
        return '-'
    album_display.short_description = 'Álbum'
    album_display.admin_order_field = 'album_name'

    def categories_display_admin(self, obj):
        """Muestra las categorías de forma legible"""
        cats = obj.categories.all()
        if cats:
            return ', '.join([cat.name for cat in cats])
        return '-'
    categories_display_admin.short_description = 'Categorías'

    def get_queryset(self, request):
        """Optimizar consultas con select_related y prefetch_related"""
        return super().get_queryset(request).select_related(
            'match__home_team', 'match__away_team', 'match__league',
            'uploaded_by', 'moderated_by'
        ).prefetch_related('categories')

    def approve_images(self, request, queryset):
        """Acción masiva para aprobar imágenes"""
        updated = queryset.filter(status='pending').update(
            status='approved',
            moderated_by=request.user,
            moderation_date=timezone.now(),
            moderation_notes='Aprobada masivamente desde admin'
        )

        if updated:
            self.message_user(request, f'{updated} imagen(es) aprobada(s) correctamente.')
        else:
            self.message_user(request, 'No hay imágenes pendientes para aprobar.')

    approve_images.short_description = "Aprobar imágenes seleccionadas"

    def reject_images(self, request, queryset):
        """Acción masiva para rechazar imágenes"""
        updated = queryset.filter(status='pending').update(
            status='rejected',
            moderated_by=request.user,
            moderation_date=timezone.now(),
            moderation_notes='Rechazada masivamente desde admin'
        )

        if updated:
            self.message_user(request, f'{updated} imagen(es) rechazada(s) correctamente.')
        else:
            self.message_user(request, 'No hay imágenes pendientes para rechazar.')

    reject_images.short_description = "Rechazar imágenes seleccionadas"

    def check_with_vision_api(self, request, queryset):
        """Acción para verificar imágenes con Google Vision API"""
        if not getattr(settings, 'GOOGLE_VISION_ENABLED', False):
            self.message_user(request, 'Google Vision API no está habilitada.', level='WARNING')
            return

        try:
            from ilovevoley.videos.utils import check_image_with_vision_api
            checked_count = 0
            unsafe_count = 0

            for image in queryset:
                if not image.vision_api_checked:
                    try:
                        result = check_image_with_vision_api(image.image)
                        image.vision_api_checked = True
                        image.vision_api_safe = result.get('safe', True)
                        image.vision_api_details = result

                        if not result.get('safe', True):
                            unsafe_count += 1
                            # Auto-rechazar si no es segura
                            image.status = 'rejected'
                            image.moderated_by = request.user
                            image.moderation_date = timezone.now()
                            image.moderation_notes = 'Auto-rechazada por Google Vision API'

                        image.save()
                        checked_count += 1

                    except Exception as e:
                        self.message_user(request, f'Error verificando {image.title}: {e}', level='ERROR')

            if checked_count > 0:
                self.message_user(request, f'{checked_count} imagen(es) verificada(s) con Vision API.')
                if unsafe_count > 0:
                    self.message_user(request, f'{unsafe_count} imagen(es) marcada(s) como insegura(s).', level='WARNING')

        except ImportError:
            self.message_user(request, 'Utilidad de Vision API no disponible.', level='ERROR')

    check_with_vision_api.short_description = "Verificar con Google Vision API"

    def assign_to_album(self, request, queryset):
        """Asignar imágenes seleccionadas a un álbum nuevo o existente."""
        if 'apply' in request.POST:
            action_type = request.POST.get('action_type')
            if action_type == 'new':
                album_name = request.POST.get('album_name', '').strip()
                if not album_name:
                    self.message_user(request, 'El nombre del álbum no puede estar vacío.', level='ERROR')
                    return None
                album_id = uuid.uuid4()
            else:
                raw_id = request.POST.get('album_group_id', '').strip()
                if not raw_id:
                    self.message_user(request, 'Selecciona un álbum existente.', level='ERROR')
                    return None
                try:
                    album_id = uuid.UUID(raw_id)
                except ValueError:
                    self.message_user(request, 'Álbum no válido.', level='ERROR')
                    return None
                album_name = Image.objects.filter(album_group_id=album_id).values_list('album_name', flat=True).first() or ''

            ids = request.POST.getlist(helpers.ACTION_CHECKBOX_NAME)
            updated = Image.objects.filter(pk__in=ids).update(
                album_group_id=album_id,
                album_name=album_name,
            )
            self.message_user(request, f'{updated} foto(s) asignada(s) al álbum "{album_name}".')
            return None

        existing_albums = (
            Image.objects
            .filter(album_group_id__isnull=False)
            .exclude(album_name='')
            .values('album_group_id', 'album_name')
            .distinct()
            .order_by('album_name')
        )
        return render(request, 'admin/videos/assign_album_action.html', {
            **self.admin_site.each_context(request),
            'queryset': queryset,
            'existing_albums': existing_albums,
            'action_checkbox_name': helpers.ACTION_CHECKBOX_NAME,
            'title': 'Asignar álbum a imágenes seleccionadas',
        })

    assign_to_album.short_description = "Asignar a álbum"

    def assign_to_match(self, request, queryset):
        """Asignar imágenes seleccionadas a un partido."""
        if 'apply' in request.POST:
            match_id = request.POST.get('match_id', '').strip()
            if not match_id:
                self.message_user(request, 'Selecciona un partido.', level='ERROR')
                return None
            try:
                match = Match.objects.get(pk=match_id)
            except Match.DoesNotExist:
                self.message_user(request, 'Partido no encontrado.', level='ERROR')
                return None

            ids = request.POST.getlist(helpers.ACTION_CHECKBOX_NAME)
            updated = Image.objects.filter(pk__in=ids).update(match=match)
            self.message_user(request, f'{updated} foto(s) asignada(s) al partido "{match}".')
            return None

        from django.utils import timezone
        from django.conf import settings as django_settings
        from django.db.models import Q as DQ

        club_name = getattr(django_settings, 'CLUB_TEAM_NAME', 'SANT JOSEP')
        club_query = (
            DQ(home_team__name__icontains=club_name) |
            DQ(away_team__name__icontains=club_name) |
            DQ(home_team_text__icontains=club_name) |
            DQ(away_team_text__icontains=club_name) |
            DQ(home_team__parent_team__name__icontains=club_name) |
            DQ(away_team__parent_team__name__icontains=club_name)
        )
        now = timezone.now()
        base_qs = Match.objects.select_related('home_team', 'away_team', 'league')
        past = base_qs.filter(club_query, match_date__lt=now).order_by('-match_date')
        next_match = base_qs.filter(club_query, match_date__gte=now).order_by('match_date').first()
        if next_match:
            matches = list(base_qs.filter(id=next_match.id)) + list(past)
        else:
            matches = list(past)

        return render(request, 'admin/videos/assign_match_action.html', {
            **self.admin_site.each_context(request),
            'queryset': queryset,
            'matches': matches,
            'action_checkbox_name': helpers.ACTION_CHECKBOX_NAME,
            'title': 'Asignar partido a imágenes seleccionadas',
        })

    assign_to_match.short_description = "Asignar a partido"

    def unassign_album(self, request, queryset):
        """Quitar el álbum de las imágenes seleccionadas."""
        updated = queryset.filter(album_group_id__isnull=False).update(
            album_group_id=None,
            album_name='',
        )
        if updated:
            self.message_user(request, f'{updated} foto(s) desasignada(s) de su álbum.')
        else:
            self.message_user(request, 'Las imágenes seleccionadas no pertenecían a ningún álbum.')

    unassign_album.short_description = "Desasignar álbum"

    def unassign_match(self, request, queryset):
        """Quitar el partido de las imágenes seleccionadas."""
        updated = queryset.filter(match__isnull=False).update(match=None, set_number=None)
        if updated:
            self.message_user(request, f'{updated} foto(s) desasignada(s) de su partido.')
        else:
            self.message_user(request, 'Las imágenes seleccionadas no tenían partido asignado.')

    unassign_match.short_description = "Desasignar partido"

    def save_model(self, request, obj, form, change):
        """Auto-asignar moderador en cambios de estado"""
        if change and 'status' in form.changed_data:
            if obj.status in ['approved', 'rejected'] and not obj.moderated_by:
                obj.moderated_by = request.user
                obj.moderation_date = timezone.now()

        super().save_model(request, obj, form, change)
