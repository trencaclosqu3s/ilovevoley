"""Capa de compatibilidad del paquete legado ``videos``.

Ya no sirve vistas: cada ruta antigua responde con una redirección permanente
(HTTP 301) hacia su ruta canónica en la app de dominio correspondiente, de modo
que los marcadores externos siguen funcionando. Las vistas viven en
``content``, ``competitions``, ``teams``, ``rosters`` y ``core``.
"""

from django.urls import path
from django.views.generic import RedirectView


def _legacy(pattern: str, target: str):
    """Ruta antigua de ``/videos/`` que redirige de forma permanente a ``target``.

    Se conserva la query string original para no romper marcadores con filtros
    ni tokens.
    """
    return path(
        pattern,
        RedirectView.as_view(
            pattern_name=target,
            permanent=True,
            query_string=True,
        ),
    )


urlpatterns = [
    # content: vídeos e imágenes
    _legacy('', 'content:video_list'),
    _legacy('nuevo/', 'content:video_create'),
    _legacy('nuevo-multiple/', 'content:video_bulk_create'),
    _legacy('<int:video_id>/', 'content:video_detail'),
    _legacy('imagenes/', 'content:image_gallery'),
    _legacy('imagenes/individual/', 'content:image_gallery_individual'),
    _legacy('imagenes/subir/', 'content:image_upload'),
    _legacy('imagenes/subir-multiples/', 'content:image_bulk_upload'),
    _legacy('imagenes/<int:image_id>/', 'content:image_detail'),
    _legacy('partidos/<int:match_id>/imagenes/', 'content:match_images'),
    _legacy('imagenes/album/<uuid:album_group_id>/', 'content:album_group_images'),
    _legacy('admin/imagenes/moderar/', 'content:image_moderation'),
    _legacy('admin/imagenes/<int:image_id>/moderar/', 'content:image_moderate_action'),
    _legacy('admin/imagenes/moderar-masivo/', 'content:image_moderate_bulk'),
    _legacy('api/images/<int:image_id>/moderate/', 'content:moderate_image_api'),

    # competitions: ligas, partidos, clasificación y calendario
    _legacy('ligas/', 'competitions:league_list'),
    _legacy('ligas/<int:league_id>/', 'competitions:league_detail'),
    _legacy('partidos/<int:match_id>/', 'competitions:match_detail'),
    _legacy('calendario/', 'competitions:calendar_view'),
    _legacy('clasificacion/', 'competitions:standings_view'),
    _legacy('calendario/amistoso/nuevo/', 'competitions:friendly_match_create'),
    _legacy('calendario/suscripcion/<str:token>/', 'competitions:calendar_feed'),
    _legacy('ajax/matches-by-category/', 'competitions:ajax_matches_by_category'),
    _legacy('ajax/teams-by-league-category/', 'competitions:ajax_teams_by_league_category'),
    _legacy('ajax/search-teams/', 'competitions:ajax_search_teams'),
    _legacy('ajax/partidos/<int:match_id>/resultado/', 'competitions:ajax_add_match_result'),
    _legacy('ajax/partidos/<int:match_id>/alineacion/', 'competitions:ajax_acta_lineup'),

    # teams: equipos
    _legacy('equipos/', 'teams:team_list'),
    _legacy('equipos/<int:team_id>/plantilla/', 'teams:team_roster'),
    _legacy('ajax/register-team/', 'teams:ajax_register_team'),

    # rosters: plantillas y personas
    _legacy('plantillas/', 'rosters:roster_overview'),
    _legacy('personas/', 'rosters:person_list'),
    _legacy('personas/nueva/', 'rosters:person_create'),
    _legacy('personas/<int:person_id>/', 'rosters:person_detail'),
    _legacy('personas/<int:person_id>/editar/', 'rosters:person_edit'),
    _legacy('personas/<int:person_id>/jugador/agregar/', 'rosters:player_role_create'),
    _legacy('roles-jugador/<int:role_id>/editar/', 'rosters:player_role_edit'),
    _legacy('roles-jugador/<int:role_id>/toggle/', 'rosters:player_role_toggle_active'),
    _legacy('personas/<int:person_id>/staff/agregar/', 'rosters:staff_role_create'),
    _legacy('roles-staff/<int:role_id>/editar/', 'rosters:staff_role_edit'),
    _legacy('roles-staff/<int:role_id>/toggle/', 'rosters:staff_role_toggle_active'),

    # core: moderación, institucional
    _legacy('moderacion/', 'core:moderation_panel'),
    _legacy('api/moderation/counts/', 'core:moderation_counts_api'),
    _legacy('api/users/<int:user_id>/approve/', 'core:approve_user_api'),
    _legacy('api/users/<int:user_id>/reject/', 'core:reject_user_api'),
    _legacy('quienes-somos/', 'core:about'),
]
