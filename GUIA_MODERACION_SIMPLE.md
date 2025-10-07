# 📧 Guía de Moderación por Email - Super Simple

## Para la Moderadora (Mami del Equipo) 👩‍💼

### 🎯 ¿Qué Hace Esta Funcionalidad?

Ahora puedes **aprobar o rechazar usuarios e imágenes directamente desde tu email**, sin necesidad de entrar al panel de administración. ¡Así de simple! 🎉

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

**Opción 1: Aprobar (Lo Normal)**
- Haz clic en el botón verde grande **"✓ Aprobar Usuario"**
- ¡Listo! El usuario ya puede usar la web
- Le llegará un email automático avisándole

**Opción 2: Rechazar (Si Algo No Cuadra)**
- Haz clic en el botón rojo **"✗ Rechazar Usuario"**
- El usuario no podrá acceder
- Su cuenta quedará desactivada

**Opción 3: Ver Más Detalles**
- Si no estás segura, haz clic en **"Ver en Admin Panel"**
- Te llevará al panel de administración con todos los detalles

### 💡 Consejos:
- ✅ **Aprueba** si ves que la información familiar tiene sentido (ej: "mamá de Luis de infantil")
- ❌ **Rechaza** si parece spam o no tiene sentido
- 🤔 **Revisa en Admin** si tienes dudas

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

### ¿Qué Hacer?

**Opción 1: Aprobar (Si la Imagen Está Bien)**
- Revisa la imagen adjunta
- Si es apropiada, haz clic en **"✓ Aprobar Imagen"**
- La imagen aparecerá en la galería pública
- El usuario recibirá una notificación

**Opción 2: Rechazar (Si No Es Apropiada)**
- Si la imagen no es adecuada, haz clic en **"✗ Rechazar Imagen"**
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

- ✅ Los enlaces están **cifrados** con tecnología de Django
- ✅ Solo funcionan durante **7 días** (después expiran)
- ✅ Solo pueden aprobar/rechazar **ese usuario/imagen específico**
- ✅ No pueden hacer nada más en la web
- ✅ No necesitas hacer login

### ¿Qué Pasa Si...?

**❓ El enlace no funciona**
- Probablemente haya expirado (más de 7 días)
- Solución: Accede al panel de admin directamente

**❓ Ya aprobé/rechacé y hago clic de nuevo**
- Te dirá que ya fue moderado
- No pasa nada malo, está controlado

**❓ Aprobé por error**
- Accede al panel de admin
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
3. ✅ Si todo parece OK, haces clic en el botón verde **"Aprobar Usuario"**
4. 🌐 Se abre una página confirmando que fue aprobado
5. 🎉 ¡El usuario ya puede acceder!
6. 📨 El usuario recibe un email automático: "Tu cuenta ha sido aprobada"

### Primera Vez Que Recibes Un Email De Imagen:

1. 📧 Te llega el email: **"Nueva imagen pendiente de moderación: Partido Infantil vs Aleví"**
2. 🖼️ **Ves la imagen directamente en el email** (grande y clara)
3. 👀 Revisas que sea apropiada
4. ✅ Si está bien, haces clic en el botón verde **"Aprobar Imagen"**
5. 🌐 Se abre una página confirmando que fue aprobada
6. 🎉 ¡La imagen ya está visible en la galería!
7. 📨 El usuario recibe un email: "Tu imagen ha sido aprobada"

---

## 🆘 ¿Problemas?

### No Me Llegan Los Emails
- Revisa la carpeta de SPAM
- Asegúrate de que tu email es superuser en el sistema
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
Email → Ver Info → Botón Verde (aprobar) o Rojo (rechazar) → ¡Listo!
```

### Imagen Nueva:
```
Email → Ver Imagen Adjunta → Botón Verde (aprobar) o Rojo (rechazar) → ¡Listo!
```

---

## 📞 Contacto

Si tienes dudas o problemas:
- Contacta al desarrollador
- O accede al panel de admin tradicional

---

**¡Es así de fácil! No necesitas aprender a usar el admin panel. Todo desde tu email. 💪**

🎉 **¡Feliz moderación!** 🎉

