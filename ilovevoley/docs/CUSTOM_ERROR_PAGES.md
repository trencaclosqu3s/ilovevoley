# Páginas de Error Personalizadas 🏐

## Descripción

Se han creado páginas de error personalizadas con temática de voleibol para mejorar la experiencia de usuario cuando ocurren errores en la aplicación.

## Páginas creadas

### 404 - Página no encontrada
- **Mensaje**: "¡Has fallado el saque!"
- **Icono**: `ball` (pelota rebotando, `art-bounce`)
- **Descripción**: "La página que buscas se ha ido fuera de la cancha"

### 500 - Error del servidor
- **Mensaje**: "¡El árbitro pita falta!"
- **Icono**: `x-circle`
- **Descripción**: "Hemos tocado la red en el servidor"

### 403 - Acceso denegado
- **Mensaje**: "¡Bloqueo triple!"
- **Icono**: `lock`
- **Descripción**: "Tu remate ha sido bloqueado en la red"

### 400 - Solicitud incorrecta
- **Mensaje**: "¡Doble toque!"
- **Icono**: `warning`
- **Descripción**: "La solicitud que enviaste no es válida"

### 429 - Demasiadas peticiones
- **Mensaje**: "¡Tiempo de descanso!"
- **Icono**: `clock`
- **Descripción**: "Has enviado demasiadas peticiones en muy poco tiempo"
- Se muestra cuando salta el rate limiting (`RATELIMIT_VIEW = 'ilovevoley.core.views.custom_429'` y las vistas de login/reset de [AUTENTICACION.md](AUTENTICACION.md))

## Características

✅ **Diseño coherente**: Extienden `base_error.html`, página autónoma (no extiende `base.html` ni conoce el tenant) con los colores corporativos de I Love Voley
✅ **Responsive**: Se adaptan a móviles, tablets y escritorio
✅ **Iconos**: Cada página tiene su icono SVG (`{% icon %}`) relacionado con el error
✅ **Mensajes divertidos**: Utilizan terminología del voleibol de forma humorística
✅ **Animaciones**: Animación CSS sutil (`art-bounce` en el 404)
✅ **Acciones útiles**: Botones para volver al inicio o a la página anterior (`data-action="back"`, sin JS inline por la [CSP](CSP.md))
✅ **Branding**: Logo de I Love Voley en el pie
✅ **i18n**: Textos con `{% trans %}` (castellano y catalán)

## Cómo probar las páginas (en modo DEBUG)

Mientras `DEBUG=True`, puedes acceder a las siguientes URLs de prueba:

```
http://localhost:8008/test-error/400/  # Probar página 400
http://localhost:8008/test-error/403/  # Probar página 403
http://localhost:8008/test-error/404/  # Probar página 404
http://localhost:8008/test-error/429/  # Probar página 429
http://localhost:8008/test-error/500/  # Probar página 500
```

**Nota**: Estas URLs solo están disponibles en modo desarrollo. En producción (`DEBUG=False`), las páginas se mostrarán automáticamente cuando ocurran los errores correspondientes.

## Probar en producción

Para probar las páginas en modo producción (sin DEBUG):

1. Temporalmente establece `DEBUG=False` en tu `.env`
2. Asegúrate de tener configurado `ALLOWED_HOSTS` correctamente
3. Ejecuta `docker compose -f docker-compose.dev.yml run --rm web python manage.py collectstatic --noinput` para recoger archivos estáticos
4. Visita una URL inexistente para ver el 404
5. Para el 500, puedes crear temporalmente una vista que lance una excepción

## Archivos creados/modificados

### Nuevos archivos:
- `ilovevoley/templates/base_error.html` - Plantilla base común
- `ilovevoley/templates/400.html` - Página de error 400
- `ilovevoley/templates/403.html` - Página de error 403
- `ilovevoley/templates/404.html` - Página de error 404
- `ilovevoley/templates/429.html` - Página de error 429
- `ilovevoley/templates/500.html` - Página de error 500

### Archivos modificados:
- `config/urls.py` - `handler400/403/404/500` y URLs de prueba (solo con `DEBUG`)
- `ilovevoley/core/views.py` - Vistas `custom_400`, `custom_403`, `custom_404`, `custom_429`, `custom_500` y `test_*`

## Mensajes divertidos incluidos

Algunos ejemplos de los mensajes con temática de voleibol:

- **404**: "No encontramos esa página... ¡Parece que el líbero no llegó a esa recepción!"
- **500**: "¡Rotación incorrecta! Algo salió mal en nuestro lado de la cancha..."
- **403**: "¡No puedes pasar! El bloqueo está bien colocado y no tienes permiso para acceder aquí."
- **400**: "¡El árbitro pita! Has tocado el balón dos veces seguidas... La solicitud está mal formada."
- **429**: "¡El árbitro pita tiempo técnico! Tu ritmo de juego es demasiado rápido para el marcador."

## Terminología de voleibol utilizada

- 🏐 Saque (serve)
- 🏐 Recepción
- 🏐 Bloqueo (block)
- 🏐 Remate (spike)
- 🏐 Doble toque (double hit)
- 🏐 Rotación
- 🏐 Tocar la red (net fault)
- 🏐 Tarjeta roja
- 🏐 Tiempo muerto (timeout)
- 🏐 Líbero

## Notas técnicas

- Las páginas usan TailwindCSS (igual que el resto de la aplicación)
- Sin tenant, `base_error.html` fija en `:root` la variable `--brand` con el color corporativo (`#01696f`) y deriva de ella el resto de tonos (`--brand-solid`, `--tint`...)
- Las animaciones CSS son sutiles para no distraer
- Los handlers funcionan tanto en modo DEBUG como en producción
