# Páginas de Error Personalizadas 🏐

## Descripción

Se han creado páginas de error personalizadas con temática de voleibol para mejorar la experiencia de usuario cuando ocurren errores en la aplicación.

## Páginas creadas

### 404 - Página no encontrada
- **Mensaje**: "¡Has fallado el saque!"
- **Emoji**: 🏐 (pelota rebotando)
- **Arte ASCII**: Pelota de voleibol
- **Descripción**: "La página que buscas se ha ido fuera de la cancha"

### 500 - Error del servidor
- **Mensaje**: "¡El árbitro pita falta!"
- **Emoji**: 🔴 (tarjeta roja temblando)
- **Arte ASCII**: Tarjeta roja con "ERROR 500"
- **Descripción**: "Hemos tocado la red en el servidor"

### 403 - Acceso denegado
- **Mensaje**: "¡Bloqueo triple!"
- **Emoji**: 🙅‍♂️ (brazos bloqueando)
- **Arte ASCII**: Bloqueo en la red
- **Descripción**: "Tu remate ha sido bloqueado en la red"

### 400 - Solicitud incorrecta
- **Mensaje**: "¡Doble toque!"
- **Emoji**: ⚠️ (advertencia temblando)
- **Arte ASCII**: Doble toque
- **Descripción**: "La solicitud que enviaste no es válida"

## Características

✅ **Diseño coherente**: Siguen el estilo visual de la aplicación (colores morados y amarillos del club)
✅ **Responsive**: Se adaptan a móviles, tablets y escritorio
✅ **Arte ASCII**: Cada página tiene su propio arte ASCII relacionado con el error
✅ **Mensajes divertidos**: Utilizan terminología del voleibol de forma humorística
✅ **Animaciones**: Emojis con animaciones CSS sutiles
✅ **Acciones útiles**: Botones para volver al inicio o a la página anterior
✅ **Branding**: Mantienen la identidad del CV Sant Josep Obrer

## Cómo probar las páginas (en modo DEBUG)

Mientras `DEBUG=True`, puedes acceder a las siguientes URLs de prueba:

```
http://localhost:8000/test-error/400/  # Probar página 400
http://localhost:8000/test-error/403/  # Probar página 403
http://localhost:8000/test-error/404/  # Probar página 404
http://localhost:8000/test-error/500/  # Probar página 500
```

**Nota**: Estas URLs solo están disponibles en modo desarrollo. En producción (`DEBUG=False`), las páginas se mostrarán automáticamente cuando ocurran los errores correspondientes.

## Probar en producción

Para probar las páginas en modo producción (sin DEBUG):

1. Temporalmente establece `DEBUG=False` en tu `.env`
2. Asegúrate de tener configurado `ALLOWED_HOSTS` correctamente
3. Ejecuta `python manage.py collectstatic` para recoger archivos estáticos
4. Visita una URL inexistente para ver el 404
5. Para el 500, puedes crear temporalmente una vista que lance una excepción

## Archivos creados/modificados

### Nuevos archivos:
- `videosvoley/templates/400.html` - Página de error 400
- `videosvoley/templates/403.html` - Página de error 403
- `videosvoley/templates/404.html` - Página de error 404
- `videosvoley/templates/500.html` - Página de error 500

### Archivos modificados:
- `config/urls.py` - Añadidos handlers de error personalizados y URLs de prueba
- `videosvoley/core/views.py` - Añadidas vistas para los handlers de error

## Mensajes divertidos incluidos

Algunos ejemplos de los mensajes con temática de voleibol:

- **404**: "No encontramos esa página... ¡Parece que el líbero no llegó a esa recepción!"
- **500**: "¡Rotación incorrecta! Algo salió mal en nuestro lado de la cancha..."
- **403**: "¡No puedes pasar! El bloqueo está bien colocado y no tienes permiso para acceder aquí."
- **400**: "¡El árbitro pita! Has tocado el balón dos veces seguidas... La solicitud está mal formada."

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
- Los colores del club están definidos: `csj-purple` (#9B7FBF) y `csj-yellow` (#F4D47C)
- El arte ASCII está optimizado para diferentes tamaños de pantalla
- Las animaciones CSS son sutiles para no distraer
- Los handlers funcionan tanto en modo DEBUG como en producción
