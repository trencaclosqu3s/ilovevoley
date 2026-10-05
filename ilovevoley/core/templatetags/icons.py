"""Iconos SVG de trazo (24x24, currentColor) en sustitución de emojis, para que toda la UI tenga un único estilo.

Se registra como builtin en TEMPLATES, así que se usa sin `{% load %}`: `{% icon 'trophy' %}` o `{% icon 'star' 'w-4 h-4 text-yellow-500' %}`.
El tamaño por defecto es 1.1em (clase `.icon` en input.css), de modo que escala con el texto como lo hacía el emoji.
"""
from django import template
from django.utils.html import format_html
from django.utils.safestring import mark_safe

register = template.Library()

_CIRCLE = '<circle cx="12" cy="12" r="9"/>'

ICONS = {
    'ball': '<circle cx="12" cy="12" r="9"/><path d="M12 3c2 3 2.5 6 0 9s-2 6 0 9M4 8c4 0 7 1.5 8 4M20 8c-4 0-7 1.5-8 4"/>',
    'clipboard': '<rect x="8" y="3" width="8" height="4" rx="1"/><path d="M8 5H6a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2h-2M9 12h6M9 16h6"/>',
    'calendar': '<rect x="3" y="5" width="18" height="16" rx="3"/><path d="M8 3v4M16 3v4M3 10h18"/>',
    'trophy': '<path d="M8 4h8v5a4 4 0 0 1-8 0zM8 6H4v1a3 3 0 0 0 4 3M16 6h4v1a3 3 0 0 1-4 3M12 13v4M8 20h8"/>',
    'link': '<path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1"/>',
    'film': '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M7 4v16M17 4v16M3 9h4M3 15h4M17 9h4M17 15h4"/>',
    'video': '<rect x="3" y="6" width="13" height="12" rx="3"/><path d="m16 10 5-3v10l-5-3"/>',
    'chart': '<path d="M4 20V10M10 20V4M16 20v-8M22 20H2"/>',
    'users': '<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20a6.5 6.5 0 0 1 13 0M16 4.5a3.5 3.5 0 0 1 0 7M18 14.5a6.5 6.5 0 0 1 3.5 5.5"/>',
    'user': '<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>',
    'pencil': '<path d="M4 20h4L19 9a2.8 2.8 0 0 0-4-4L4 16z"/><path d="m13.5 6.5 4 4"/>',
    'sparkles': '<path d="M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5M15.5 15.5 18 18M18 6l-2.5 2.5M8.5 15.5 6 18"/>',
    'camera': '<path d="M4 8h3l2-3h6l2 3h3a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V9a1 1 0 0 1 1-1z"/><circle cx="12" cy="13" r="3.5"/>',
    'star': '<path d="m12 3 2.7 5.6 6.1.9-4.4 4.3 1 6.1L12 17l-5.4 2.9 1-6.1L3.2 9.5l6.1-.9z"/>',
    'plus': '<path d="M12 5v14M5 12h14"/>',
    'search': '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
    'map-pin': '<path d="M12 21s-6-5.5-6-10a6 6 0 0 1 12 0c0 4.5-6 10-6 10z"/><circle cx="12" cy="11" r="2.5"/>',
    'cog': '<circle cx="12" cy="12" r="3"/><path d="M12 3v2M12 19v2M3 12h2M19 12h2M5.6 5.6 7 7M17 17l1.4 1.4M18.4 5.6 17 7M7 17l-1.4 1.4"/>',
    'target': _CIRCLE + '<circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1" fill="currentColor"/>',
    'medal': '<circle cx="12" cy="14" r="6"/><path d="M8.5 3 12 9l3.5-6"/>',
    'bulb': '<path d="M9 18h6M10 21h4M12 3a6 6 0 0 0-4 10.5c.7.7 1 1.5 1 2.5h6c0-1 .3-1.8 1-2.5A6 6 0 0 0 12 3z"/>',
    'building': '<rect x="5" y="3" width="14" height="18" rx="1"/><path d="M9 7h2M13 7h2M9 11h2M13 11h2M10 21v-4h4v4"/>',
    'eye': '<path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
    'document': '<path d="M6 3h8l5 5v13H6zM14 3v5h5M9 13h6M9 17h6"/>',
    'chat': '<path d="M21 12a8 8 0 0 1-11.5 7.2L4 20l1-4.5A8 8 0 1 1 21 12z"/>',
    'bell': '<path d="M6 16v-5a6 6 0 0 1 12 0v5l2 2H4zM10 21h4"/>',
    'phone': '<rect x="7" y="2" width="10" height="20" rx="2"/><path d="M11 18h2"/>',
    'logout': '<path d="M9 4H5v16h4M16 8l4 4-4 4M20 12H9"/>',
    'moon': '<path d="M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5z"/>',
    'clock': _CIRCLE + '<path d="M12 7v5l3 2"/>',
    'check': '<path d="m5 12.5 4.5 4.5L19 7"/>',
    'check-circle': _CIRCLE + '<path d="m8 12.5 3 3 5-6"/>',
    'x': '<path d="M6 6l12 12M18 6 6 18"/>',
    'x-circle': _CIRCLE + '<path d="m9 9 6 6M15 9l-6 6"/>',
    'warning': '<path d="M12 3 2 20h20z"/><path d="M12 10v4M12 17h.01"/>',
    'info': _CIRCLE + '<path d="M12 11v5M12 8h.01"/>',
    'ban': _CIRCLE + '<path d="m5.6 5.6 12.8 12.8"/>',
    'tag': '<path d="M3 12V4h8l10 10-8 8z"/><circle cx="7.5" cy="8.5" r="1"/>',
    'refresh': '<path d="M20 11a8 8 0 0 0-14-4M4 4v4h4M4 13a8 8 0 0 0 14 4M20 20v-4h-4"/>',
    'home': '<path d="M3 11.5 12 4l9 7.5M5.5 10v10h13V10M10 20v-5h4v5"/>',
    'lock': '<rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/>',
    'key': '<circle cx="8" cy="15" r="4"/><path d="m11 12 9-9M16 7l3 3"/>',
    'arrow-left': '<path d="M19 12H5M11 6l-6 6 6 6"/>',
    'heart': '<path d="M12 20s-7-4.5-7-10a4 4 0 0 1 7-2.5A4 4 0 0 1 19 10c0 5.5-7 10-7 10z"/>',
}

# Emoji -> nombre de icono, para quien migre plantillas nuevas.
EMOJI_TO_ICON = {
    '🏐': 'ball', '📋': 'clipboard', '📅': 'calendar', '🏆': 'trophy', '🔗': 'link', '🎬': 'film', '📹': 'video', '📊': 'chart',
    '👥': 'users', '👤': 'user', '📝': 'pencil', '🎉': 'sparkles', '📸': 'camera', '⭐': 'star', '➕': 'plus', '🔍': 'search',
    '📍': 'map-pin', '⚙️': 'cog', '🎯': 'target', '🥇': 'medal', '🥈': 'medal', '🥉': 'medal', '💡': 'bulb', '🏢': 'building',
    '👁️': 'eye', '📄': 'document', '💬': 'chat', '💭': 'chat', '🔔': 'bell', '📱': 'phone', '🚪': 'logout', '💤': 'moon',
    '📌': 'map-pin', '🕒': 'clock', '🤝': 'users', '✓': 'check', '✅': 'check-circle', '❌': 'x-circle', '✕': 'x', '⚠️': 'warning',
    '⚠': 'warning', 'ℹ️': 'info', 'ℹ': 'info', '🚨': 'warning', '🔞': 'ban', '🏷️': 'tag', '🔄': 'refresh', '🏥': 'building', '🏠': 'home', '🔑': 'key', '🚫': 'ban', '🛑': 'ban',
}


@register.simple_tag
def icon(name, css_class=''):
    return format_html(
        '<svg class="icon {}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" '
        'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{}</svg>',
        css_class, mark_safe(ICONS[name]),
    )
