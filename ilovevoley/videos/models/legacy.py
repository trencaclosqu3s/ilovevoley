"""Upload paths de compatibilidad para migraciones históricas de videos."""


def player_photo_upload_path(instance, filename):
    return f'players/{filename}'


def staff_photo_upload_path(instance, filename):
    return f'staff/{filename}'


__all__ = ['player_photo_upload_path', 'staff_photo_upload_path']
