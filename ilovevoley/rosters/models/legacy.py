"""Modelos legados Player y Staff eliminados en la Fase 3 (#68).

Upload paths mantenidos como stubs para compatibilidad con migraciones históricas de rosters.
"""


def player_photo_upload_path(instance, filename):
    return f'players/{filename}'


def staff_photo_upload_path(instance, filename):
    return f'staff/{filename}'


__all__ = ['player_photo_upload_path', 'staff_photo_upload_path']
