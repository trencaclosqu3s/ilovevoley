"""
Moderation views re-exports for backward compatibility.
"""
from videosvoley.content.views import (
    image_moderate_action,
    image_moderate_bulk,
    image_moderation,
    moderate_image_api,
)
from videosvoley.core.views import (
    approve_user_api,
    moderation_counts_api,
    moderation_panel,
    reject_user_api,
)

__all__ = [
    'image_moderation',
    'image_moderate_action',
    'image_moderate_bulk',
    'moderation_counts_api',
    'moderation_panel',
    'approve_user_api',
    'reject_user_api',
    'moderate_image_api',
]
