# 📧 Guía de Moderación por Email - Super Simple

## Para la Moderadora (Mami del Equipo) 👩‍💼

### 🎯 ¿Qué Hace Esta Funcionalidad?

Te llega un email por cada **usuario nuevo** y por cada **imagen pendiente**. Las imágenes puedes **aprobarlas o rechazarlas desde el propio email**; los usuarios se aprueban en el **panel de moderación** del club (`/core/moderacion/`), al que lleva el botón del email. ¡Así de simple! 🎉

Los emails llegan a los superusuarios y a los **admins y managers aprobados del club** donde ocurre el alta o la subida.

---

## 📬 Nuevo Usuario Registrado

### Qué Vas a Recibir:

Cuando alguien se registre en la web, te llegará un email como este:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔔 Nuevo usuario registrado
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Nombre de usuario: juanito_papa
Email: juan@example.com
Nombre completo: Juan García
Información Familiar: Papá de Pedrito de Infantil
Fecha de registro: 07/10/2025 14:30
Estado actual: ⏳ Pendiente de aprobación

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

### ¿Qué Hacer?

- Haz clic en el botón **"🔔 Revisar en el panel de moderación"** (necesitas tener la sesión iniciada)
- En el panel verás la solicitud con sus datos y los botones para aprobarla o rechazarla

**Aprobar (Lo Normal)**
- ¡Listo! El usuario ya puede usar la web
- Le llegará un email automático avisándole

**Rechazar (Si Algo No Cuadra)**
- El usuario no podrá acceder al club

### 💡 Consejos:
- ✅ **Aprueba** si ves que la información familiar tiene sentido (ej: "mamá de Luis de infantil")
- ❌ **Rechaza** si parece spam o no tiene sentido
- 🤔 **Pregunta al equipo** si tienes dudas antes de decidir

---

## 🖼️ Nueva Imagen Subida

### Qué Vas a Recibir:

Cuando alguien suba una foto, te llegará un email con:

1. **Información de la imagen**:
   - Título de la imagen
   - Quién la subió
   - Tipo de imagen (partido, celebración, etc.)
   - Etiquetas

2. **LA IMAGEN VISIBLE EN EL EMAIL** 🖼️:
   - **La imagen aparece directamente en el cuerpo del email** (grande y clara)
   - También está adjunta como archivo por si quieres guardarla
   - Puedes revisarla sin internet una vez descargado el email
   - Se ve perfectamente en móvil y ordenador

3. **Botones de Acción**: Aprobar o Rechazar directamente

Si alguien sube **varias fotos de golpe** (cola de subida desde el móvil), en vez de un email por foto te llega **un solo email del lote** con el botón **"Ir al panel de moderación"**, y allí las moderas todas.

### ¿Qué Hacer?

**Opción 1: Aprobar (Si la Imagen Está Bien)**
- Revisa la imagen adjunta
- Si es apropiada, haz clic en **"✓ Aprobar Imagen"** y confirma en la página que se abre
- La imagen aparecerá en la galería del club
- El usuario recibirá una notificación

**Opción 2: Rechazar (Si No Es Apropiada)**
- Si la imagen no es adecuada, haz clic en **"✗ Rechazar Imagen"** y confirma
- La imagen NO se publicará
- El usuario recibirá una notificación de rechazo

**Opción 3: Añadir Notas**
- Si quieres dejar un comentario sobre por qué la rechazaste
- Haz clic en **"Ver en Admin Panel"**
- Allí puedes añadir notas de moderación

### 💡 Criterios de Moderación:
- ✅ **Aprobar**: Fotos de partidos, celebraciones, entrenamientos, equipo
- ✅ **Aprobar**: Fotos de buena calidad relacionadas con voleibol
- ❌ **Rechazar**: Contenido ofensivo o inapropiado
- ❌ **Rechazar**: Fotos borrosas o de muy mala calidad
- ❌ **Rechazar**: Contenido no relacionado con voleibol/deporte

---

## 🔐 Seguridad

### ¿Son Seguros Los Enlaces?

**¡Sí! Totalmente seguros:**

- ✅ Los enlaces están **firmados** con tecnología de Django
- ✅ Solo funcionan durante **60 minutos** (`MODERATION_TOKEN_MAX_AGE`) y **una sola vez**
- ✅ Solo pueden aprobar/rechazar **esa imagen específica**
- ✅ No pueden hacer nada más en la web
- ✅ Necesitas tener la **sesión iniciada** con una cuenta que pueda moderar ese club (si no, te pedirá entrar)

### ¿Qué Pasa Si...?

**❓ El enlace no funciona**
- Probablemente haya expirado (más de 60 minutos) o ya se usó
- Solución: Accede al panel de moderación (`/core/moderacion/`) directamente

**❓ Ya aprobé/rechacé y hago clic de nuevo**
- Te dirá que ya fue moderado
- No pasa nada malo, está controlado

**❓ Aprobé por error**
- Accede al panel de administración
- Busca el usuario/imagen
- Cambia el estado manualmente

**❓ No veo la imagen en el email**
- La imagen debería verse directamente en el cuerpo del email
- Si no la ves, comprueba si tu cliente de correo bloquea imágenes
- En Gmail/Outlook: busca un botón que diga "Mostrar imágenes" o "Display images"
- La imagen también está adjunta, puedes abrirla desde ahí
- O accede al panel de admin para ver la imagen

---

## 📱 Desde el Móvil

**¡Todo funciona perfectamente desde el móvil!** 📱

1. Abre el email en tu iPhone/Android
2. Revisa la información (y la imagen si es el caso)
3. Haz clic en el botón que quieras
4. ¡Listo! Moderación completada

---

## 🎓 Tutorial Paso a Paso

### Primera Vez Que Recibes Un Email De Usuario:

1. 📧 Te llega el email: **"Nuevo usuario pendiente de aprobación: juanito_papa"**
2. 👀 Lees la información del usuario
3. 🔔 Haces clic en **"Revisar en el panel de moderación"**
4. ✅ Si todo parece OK, lo apruebas desde el panel
5. 🎉 ¡El usuario ya puede acceder!
6. 📨 El usuario recibe un email automático: "Tu cuenta ha sido aprobada"

### Primera Vez Que Recibes Un Email De Imagen:

1. 📧 Te llega el email: **"Nueva imagen pendiente de moderación: Partido Infantil vs Aleví"**
2. 🖼️ **Ves la imagen directamente en el email** (grande y clara)
3. 👀 Revisas que sea apropiada
4. ✅ Si está bien, haces clic en el botón verde **"Aprobar Imagen"**
5. 🌐 Se abre una página donde confirmas la aprobación
6. 🎉 ¡La imagen ya está visible en la galería!
7. 📨 El usuario recibe un email: "Tu imagen ha sido aprobada"

---

## 🆘 ¿Problemas?

### No Me Llegan Los Emails
- Revisa la carpeta de SPAM
- Asegúrate de que eres admin o manager aprobado del club (o superusuario) y tienes email en tu cuenta
- Contacta con el desarrollador

### Los Botones No Funcionan
- Prueba desde otro navegador
- Copia y pega el enlace en el navegador
- Accede al panel de admin como alternativa

### No Sé Si Aprobar O Rechazar
- **Para usuarios**: Si tiene información familiar razonable → Aprueba
- **Para imágenes**: Si es apropiada y de buena calidad → Aprueba
- **Si tienes dudas**: Mira los detalles en el Admin Panel

---

## 🎯 Resumen Ultra-Rápido

### Usuario Nuevo:
```
Email → Ver Info → Panel de moderación → Aprobar o Rechazar → ¡Listo!
```

### Imagen Nueva:
```
Email → Ver Imagen Adjunta → Botón Verde (aprobar) o Rojo (rechazar) → Confirmar → ¡Listo!
```

---

## 📞 Contacto

Si tienes dudas o problemas:
- Contacta al desarrollador
- O accede al panel de admin tradicional

---

**¡Es así de fácil! No necesitas aprender a usar el admin panel: el email y el panel de moderación bastan. 💪**

🎉 **¡Feliz moderación!** 🎉

