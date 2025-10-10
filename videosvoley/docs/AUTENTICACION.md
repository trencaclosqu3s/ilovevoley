# 🔐 Sistema de Autenticación

## Configuración de Login con Google OAuth

### Problema Resuelto: redirect_uri_mismatch

Cuando se intenta hacer login con Google, puede aparecer el error `Error 400: redirect_uri_mismatch`. Esto ocurre porque el URI de redirección no está autorizado en Google Cloud Console.

**Solución:**

1. **Acceder a Google Cloud Console**
   - Ir a [Google Cloud Console](https://console.cloud.google.com/)
   - Seleccionar el proyecto
   - Ir a **APIs y servicios** → **Credenciales**
   - Editar el cliente OAuth 2.0

2. **Agregar URIs de redirección autorizados:**
   ```
   https://ilovevoley.es/accounts/google/login/callback/
   http://ilovevoley.es/accounts/google/login/callback/
   http://localhost:8000/accounts/google/login/callback/
   http://127.0.0.1:8000/accounts/google/login/callback/
   ```

3. **Configurar el Site en Django Admin:**
   - Acceder a `/admin/sites/site/1/change/`
   - Configurar:
     - **Domain name**: `ilovevoley.es`
     - **Display name**: `Vídeos Voley CV Sant Josep`

4. **Variables de entorno necesarias:**
   ```bash
   ALLOWED_HOSTS=ilovevoley.es,localhost,127.0.0.1
   CSRF_TRUSTED_ORIGINS=https://ilovevoley.es,http://ilovevoley.es
   ```

---

## Auto-Registro con Google

### Configuración

El sistema está configurado para permitir el **auto-registro** cuando un usuario inicia sesión con Google por primera vez.

**Configuración en `settings.py`:**

```python
# Auto-signup habilitado
SOCIALACCOUNT_AUTO_SIGNUP = True
ACCOUNT_EMAIL_VERIFICATION = 'none'
SOCIALACCOUNT_EMAIL_VERIFICATION = 'none'

# Obtener email de Google
SOCIALACCOUNT_QUERY_EMAIL = True
SOCIALACCOUNT_EMAIL_REQUIRED = True
SOCIALACCOUNT_STORE_TOKENS = True
```

### Adapter Personalizado

El archivo `videosvoley/users/adapters.py` contiene:

1. **`CustomSocialAccountAdapter`**:
   - Permite auto-signup con `is_auto_signup_allowed()`
   - Genera automáticamente un username único basado en el email
   - Extrae información del perfil de Google

2. **Generación de Username**:
   - Se toma la parte antes del `@` del email
   - Si existe, se añade un número al final (ej: `usuario1`, `usuario2`)

---

## Páginas de Autenticación

### Templates Disponibles

1. **`account/login.html`** - Página de inicio de sesión
   - Login con usuario/email y contraseña
   - Botón de "Entrar con Google"
   - Enlace a la página de registro

2. **`account/signup.html`** - Página de registro normal
   - Formulario con usuario, email y contraseña
   - Botón de "Registrarse con Google"
   - Enlace a la página de login

3. **`socialaccount/signup.html`** - Completar registro con Google
   - Se muestra si Google requiere información adicional
   - Pre-llena el email desde Google
   - Permite editar el username

4. **`users/pending_approval.html`** - Cuenta pendiente de aprobación
   - Se muestra después del registro
   - Informa que debe esperar aprobación del admin

### Flujo de Registro

```
Usuario hace clic en "Entrar/Registrarse con Google"
    ↓
Se autentica con Google
    ↓
¿Usuario existe?
    ├─ Sí → Login automático → Redirige a /videos/
    └─ No → Crea cuenta automática → Pending approval
```

### Flujo con Sistema de Aprobación

Por seguridad, **todas las cuentas nuevas** (tanto con Google como con registro normal) requieren aprobación de un administrador:

1. Usuario se registra (Google o formulario)
2. Se crea la cuenta con `is_approved=False`
3. Se muestra página de "Pendiente de aprobación"
4. Se envía notificación por email al admin (si está configurado)
5. Admin aprueba la cuenta desde `/admin/`
6. Usuario recibe email de aprobación (si está configurado)
7. Usuario puede iniciar sesión

---

## Estilos y Diseño

Todas las páginas de autenticación usan:

- **TailwindCSS** para estilos responsivos
- **Colores del club**: morado (`#9B7FBF`) y amarillo (`#F4D47C`)
- **Logo del club** en la parte superior
- **Optimizaciones móviles**:
  - Campos de formulario de mínimo 44px de alto
  - Font-size de 16px para prevenir zoom en iOS
  - Touch-manipulation para mejor UX táctil
- **Notificaciones toast** con Notyf

---

## Seguridad

### HTTPS Recomendado

Para producción, se recomienda usar **HTTPS** en lugar de HTTP:

1. El proyecto ya tiene configuración de Certbot en `/certbot/`
2. Usar Let's Encrypt para certificado SSL gratuito
3. Configurar nginx para redireccionar HTTP → HTTPS
4. Actualizar los URIs en Google Cloud Console para usar solo HTTPS

### CSRF Protection

El sistema está protegido contra ataques CSRF:

```python
CSRF_TRUSTED_ORIGINS = ['https://ilovevoley.es']
```

Asegurar que este dominio coincida con el dominio de producción.

---

## Troubleshooting

### El usuario no puede acceder después de login

**Causa**: La cuenta no está aprobada

**Solución**:
1. Ir a `/admin/users/user/`
2. Encontrar el usuario
3. Marcar `is_approved = True`
4. Guardar

### Google sigue pidiendo registro

**Causa**: Falta configuración en `settings.py` o en el adapter

**Verificar**:
1. `SOCIALACCOUNT_AUTO_SIGNUP = True` en settings.py
2. Adapter tiene `is_auto_signup_allowed()` retornando `True`
3. El adapter está correctamente configurado en `SOCIALACCOUNT_ADAPTER`

### Error: "Usuario ya existe"

**Causa**: El email de Google ya está registrado con otro método

**Solución**:
1. El usuario debe usar el método de login original
2. O en admin, conectar la cuenta de Google al usuario existente

---

## Testing

### Probar en Local

1. Configurar Google OAuth Client ID para localhost
2. Agregar en Google Cloud Console:
   ```
   http://localhost:8000/accounts/google/login/callback/
   http://127.0.0.1:8000/accounts/google/login/callback/
   ```
3. Configurar en Django Admin Site:
   - Domain: `localhost:8000`

### Probar en Producción

1. Usar las URLs de producción en Google Cloud Console
2. Configurar el Site correctamente
3. Verificar que HTTPS esté funcionando
4. Probar el flujo completo de registro y aprobación

---

## Referencias

- [Django Allauth Documentation](https://django-allauth.readthedocs.io/)
- [Google OAuth 2.0 Setup](https://developers.google.com/identity/protocols/oauth2)
- [Redirect URI Mismatch Error](https://developers.google.com/identity/protocols/oauth2/web-server#authorization-errors-redirect-uri-mismatch)


