"""Management command para renombrar imágenes en storage y actualizar la base de datos.

Uso:
    python manage.py rename_content_images [--dry-run] [--all] [--match ID] [--album UUID]
"""
import os
from io import BytesIO

from django.core.management.base import BaseCommand

from ilovevoley.content.image_naming import (
    build_descriptive_storage_path,
    build_descriptive_title,
    is_generic_camera_filename,
)
from ilovevoley.content.models import Image
from ilovevoley.content.thumbnails import generate_image_thumbnails


class Command(BaseCommand):
    help = 'Renombra imágenes en storage con nombres descriptivos y actualiza sus títulos en base de datos.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Simula el renombrado sin modificar archivos ni base de datos.',
        )
        parser.add_argument(
            '--all',
            action='store_true',
            help='Procesa todas las imágenes, incluso las que no tienen título genérico.',
        )
        parser.add_argument(
            '--match',
            type=int,
            help='Filtra por ID de partido.',
        )
        parser.add_argument(
            '--album',
            type=str,
            help='Filtra por UUID de álbum (album_group_id).',
        )

    def handle(self, *args, **options):
        dry_run = options.get('dry_run', False)
        process_all = options.get('all', False)
        match_id = options.get('match')
        album_group_id = options.get('album')

        qs = Image.objects.select_related('match', 'match__home_team', 'match__away_team', 'organization')
        if match_id:
            qs = qs.filter(match_id=match_id)
        if album_group_id:
            qs = qs.filter(album_group_id=album_group_id)

        # Ordenar por fecha o ID ascendente para asignar secuenciales ordenados
        qs = qs.order_by('upload_date', 'id')

        total = qs.count()
        self.stdout.write(f"Iniciando escaneo de {total} imagen(es)...")

        renamed_count = 0
        skipped_count = 0
        errors_count = 0

        # Secuenciales en memoria para este lote
        context_sequences = {}

        for image in qs:
            try:
                if not image.image:
                    skipped_count += 1
                    continue

                storage = image.image.storage
                old_path = image.image.name
                old_title = image.title or ''

                needs_rename = False
                if process_all:
                    needs_rename = True
                elif is_generic_camera_filename(old_title):
                    needs_rename = True
                else:
                    # Verificar si la ruta actual parece UUID o cámara
                    filename_only = os.path.basename(old_path)
                    name_without_ext = os.path.splitext(filename_only)[0]
                    if is_generic_camera_filename(name_without_ext):
                        needs_rename = True

                if not needs_rename:
                    skipped_count += 1
                    continue

                # Determinar contexto para secuencia
                if image.match_id:
                    ctx_key = f"match_{image.match_id}"
                elif image.album_group_id:
                    ctx_key = f"album_{image.album_group_id}"
                else:
                    ctx_key = "loose"

                if ctx_key not in context_sequences:
                    context_sequences[ctx_key] = 1
                seq = context_sequences[ctx_key]
                context_sequences[ctx_key] += 1

                # Calcular nuevo título
                if image.match:
                    new_title = build_descriptive_title(match=image.match, seq=seq)
                elif image.album_name:
                    new_title = build_descriptive_title(album_name=image.album_name, seq=seq)
                elif not is_generic_camera_filename(old_title):
                    new_title = old_title
                else:
                    new_title = build_descriptive_title(base_title='Foto', seq=seq)

                # Calcular nuevo path en storage
                _, ext = os.path.splitext(old_path)
                upload_date = image.upload_date.date() if image.upload_date else None
                new_path = build_descriptive_storage_path(
                    match=image.match,
                    album_name=image.album_name,
                    base_title=new_title if not image.match and not image.album_name else '',
                    seq=seq,
                    extension=ext,
                    storage=storage,
                    now_date=upload_date,
                )

                if old_path == new_path and old_title == new_title:
                    skipped_count += 1
                    continue

                if dry_run:
                    self.stdout.write(
                        self.style.WARNING(
                            f"[DRY-RUN] #{image.id}: '{old_title}' -> '{new_title}' | '{old_path}' -> '{new_path}'"
                        )
                    )
                    renamed_count += 1
                    continue

                # Ejecutar renombrado físico en storage
                if storage.exists(old_path):
                    with storage.open(old_path, 'rb') as old_file:
                        content_bytes = old_file.read()
                    storage.save(new_path, BytesIO(content_bytes))
                    if old_path != new_path:
                        storage.delete(old_path)

                # Actualizar campos del modelo
                image.image.name = new_path
                image.title = new_title
                image.save(update_fields=['image', 'title'])

                # Regenerar miniaturas con los nuevos nombres
                try:
                    generate_image_thumbnails(image)
                except Exception as thumb_err:
                    self.stdout.write(
                        self.style.WARNING(f"Aviso al regenerar miniaturas de #{image.id}: {thumb_err}")
                    )

                self.stdout.write(
                    self.style.SUCCESS(
                        f"[RENAMED] #{image.id}: '{old_title}' -> '{new_title}' ({new_path})"
                    )
                )
                renamed_count += 1

            except Exception as e:
                errors_count += 1
                self.stdout.write(
                    self.style.ERROR(f"Error procesando imagen #{image.id}: {e}")
                )

        prefix_msg = "[DRY-RUN] " if dry_run else ""
        self.stdout.write(
            self.style.SUCCESS(
                f"\n{prefix_msg}Proceso completado: {renamed_count} renombradas, "
                f"{skipped_count} omitidas, {errors_count} errores."
            )
        )
