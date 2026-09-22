# Configuración de Vídeos de YouTube

## Problema: Vídeos no se muestran en la web

Si experimentas problemas al incrustar vídeos de YouTube (como errores en Firefox sobre `consent.youtube.com` o Safari que no muestra el vídeo), el problema probablemente es la **configuración de privacidad del vídeo en YouTube**.

## Solución: Usar vídeos "No listados" (Unlisted)

### ❌ NO usar vídeos "Privados"

Los vídeos configurados como **"Privados"** en YouTube:
- ❌ **NO se pueden incrustar** en sitios web externos
- ❌ Solo son visibles en YouTube para usuarios específicos autorizados
- ❌ Causarán errores en navegadores (Firefox, Safari, etc.)

### ✅ SÍ usar vídeos "No listados" (Unlisted)

Los vídeos configurados como **"No listados"** en YouTube:
- ✅ **SÍ se pueden incrustar** perfectamente en sitios web
- ✅ Solo son accesibles con el enlace directo
- ✅ No aparecen en búsquedas de YouTube
- ✅ No aparecen en tu canal público
- ✅ Son ideales para contenido de menores con acceso controlado

## Cómo configurar un vídeo como "No listado"

1. Sube tu vídeo a YouTube
2. En la configuración de visibilidad, selecciona **"No listado"** (Unlisted)
3. Guarda los cambios
4. Copia la URL del vídeo
5. Pégala en el formulario de la web

## Seguridad y Privacidad

### Seguridad implementada en la web

La aplicación ya implementa varias medidas de seguridad:

1. **Dominio sin cookies**: Usa `youtube-nocookie.com` para evitar tracking
2. **Sin vídeos relacionados**: Parámetro `rel=0` para no mostrar sugerencias externas
3. **Branding mínimo**: Parámetro `modestbranding=1`
4. **Sin API JavaScript**: Parámetro `enablejsapi=0` para mayor seguridad

### Protección adicional por la web

Además de usar vídeos "No listados", la web ofrece su propia capa de protección:

1. **Autenticación requerida**: Solo usuarios registrados y aprobados pueden acceder
2. **Control de acceso**: Los administradores aprueban manualmente cada usuario
3. **Preferencias de categorías**: Los usuarios solo ven contenido de sus categorías autorizadas

## Alternativas a YouTube

Si necesitas mayor control sobre el acceso a los vídeos, considera estas alternativas:

### 1. Vimeo Business
- Privacidad por dominio (solo se pueden ver en tu web)
- Mejor control de acceso
- Sin publicidad
- Costo: ~$60/mes

### 2. Bunny Stream
- CDN global rápido
- Privacidad por dominio
- API completa
- Más económico: ~$0.005/GB

### 3. Hosting propio
- Control total
- Más trabajo técnico
- Costos de servidor y almacenamiento
- Requiere configuración de streaming

## Soporte para livestreams

### ✅ Los livestreams ahora funcionan correctamente

La web **detecta automáticamente** las URLs de livestreams (`youtube.com/live/`) y las convierte internamente para que funcionen perfectamente en la incrustación.

### Cómo funciona

1. **Detección automática**: Si pegas una URL como `https://www.youtube.com/live/QLF8o7Pn4bI`
2. **Conversión interna**: La web la convierte automáticamente a formato de incrustación
3. **Reproducción perfecta**: Funciona en todos los navegadores (Firefox, Safari, Chrome, etc.)

### No necesitas hacer nada especial

- ✅ Pega la URL del livestream tal como está
- ✅ La web se encarga de la conversión automáticamente
- ✅ Funciona igual que los vídeos normales

## Preguntas frecuentes

### ¿Los vídeos "No listados" son seguros para menores?

Sí, combinados con la autenticación de la web:
- El vídeo solo es accesible con el enlace directo
- La web requiere autenticación y aprobación de administrador
- No aparece en búsquedas públicas de YouTube

### ¿Los livestreams funcionan en la web?

Sí, perfectamente. La web detecta automáticamente las URLs de livestreams (`youtube.com/live/`) y las convierte internamente para que funcionen en todos los navegadores.

### ¿Alguien puede compartir el enlace del vídeo?

Técnicamente sí, pero:
- El enlace directo de YouTube solo funcionaría para quien lo reciba
- Dentro de la web, solo usuarios autenticados pueden ver el reproductor
- Puedes monitorear el acceso desde YouTube Analytics

### ¿Puedo cambiar un vídeo de "Privado" a "No listado"?

Sí, en cualquier momento:
1. Ve a YouTube Studio
2. Selecciona el vídeo
3. Haz clic en "Visibilidad"
4. Cambia a "No listado"
5. Guarda los cambios

El vídeo empezará a funcionar inmediatamente en la web.

## Soporte técnico

Si continúas teniendo problemas después de configurar el vídeo como "No listado":

1. Verifica que la URL del vídeo sea correcta
2. Prueba el enlace directamente en YouTube
3. Comprueba que el vídeo no tenga restricciones de edad o geográficas
4. Contacta con el administrador del sistema

