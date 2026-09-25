"""Reexport de modelos de content desde ilovevoley.content para retrocompatibilidad."""
from ilovevoley.content.models import Comment, Image, Video, image_upload_path  # noqa: F401

__all__ = ['Comment', 'Image', 'Video', 'image_upload_path']
