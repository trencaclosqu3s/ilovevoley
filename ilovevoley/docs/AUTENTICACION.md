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
   http://localhost:8008/accounts/google/login/callback/
   http://127.0.0.1:8008/accounts/google/login/callback/
   ```

3. **Configurar el Site en Django Admin:**
   - Acceder a `/<ADMIN_URL>sites/site/1/change/` (`/admin/` en desarrollo; ver [ADMIN_URL_SEGURIDAD.md](ADMIN_URL_SEGURIDAD.md))
   - Configurar:
     - **Domain name**: `ilovevoley.es`
     - **Display name**: `I Love Voley CV Sant Josep`

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
ACCOUNT_EMAIL_VERIFICATION = 'optional'  # Los registros locales reciben el correo de verificación, pero pueden entrar sin confirmarlo
SOCIALACCOUNT_EMAIL_VERIFICATION = 'none'

# Obtener email de Google
SOCIALACCOUNT_QUERY_EMAIL = True
SOCIALACCOUNT_EMAIL_REQUIRED = True
SOCIALACCOUNT_STORE_TOKENS = False  # Solo identificación: no se almacenan tokens de acceso/refresco en base de datos

# Login con Google sobre una cuenta local con el mismo email (solo si está verificado)
SOCIALACCOUNT_EMAIL_AUTHENTICATION = True
SOCIALACCOUNT_EMAIL_AUTHENTICATION_AUTO_CONNECT = True
```

Los scopes de Google se limitan a `profile` y `email` (`GOOGLE_BASIC_SCOPES`); no se piden permisos de Calendar.

### Adapter Personalizado

El archivo `ilovevoley/users/adapters.py` contiene:

1. **`CustomSocialAccountAdapter`**:
   - Permite auto-signup con `is_auto_signup_allowed()`
   - Genera automáticamente un username único basado en el email
   - Extrae información del perfil de Google
   - `authenticate_by_email()` solo reutiliza una cuenta local si su email está verificado (evita el pre-secuestro de cuentas)
   - `save_user()` crea la `Membership` pendiente en el tenant actual

2. **`CustomAccountAdapter`**: `pre_login()`/`post_login()` redirigen a `/profile/` el primer login tras una aprobación (`User.pending_profile_review`) o tras `LOGIN_PROFILE_REVIEW_INACTIVITY_DAYS` sin entrar, salvo que haya un `next` explícito (#544).

3. **Generación de Username**:
   - Se toma la parte antes del `@` del email
   - Si existe, se añade un número al final (ej: `usuario1`, `usuario2`)

---

## Páginas de Autenticación y Rate Limiting

Las rutas críticas de autenticación (`/accounts/login/`, `/accounts/signup/`, `/accounts/password/reset/`) están protegidas contra ataques de fuerza bruta mediante vistas personalizadas con limitación de tasa (`RatelimitedLoginView`, `RatelimitedSignupView`, `RatelimitedPasswordResetView`, `RatelimitedPasswordResetFromKeyView`, en `ilovevoley/users/views.py`) que tienen prioridad sobre las rutas estándar de allauth. Además, `ACCOUNT_RATE_LIMITS` quita a allauth el tramo `/key` de `login_failed` y `reset_password` para que un tercero no pueda bloquear la cuenta de la víctima (#202).

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
    ├─ Sí → Login automático → Redirige a la home del club (`LOGIN_REDIRECT_URL`) o a /profile/ (#544)
    └─ No → Crea cuenta automática → Pending approval
```

### Flujo con Sistema de Aprobación y Membresías

Por seguridad, **todas las cuentas nuevas** (tanto con Google como con registro normal) requieren aprobación previa para acceder al contenido del club:

1. El usuario se registra (vía Google OAuth o formulario).
2. Se crea la cuenta y su `Membership` para la organización actual con estado pendiente.
3. Se muestra la página de "Pendiente de aprobación" (`/pending-approval/`).
4. Se envía notificación por email a los administradores y managers correspondientes.
5. **Aprobación descentralizada**:
   - Los **managers o administradores del club** pueden aprobar la membresía directamente desde el panel `/core/moderacion/` de su organización, o mediante el enlace seguro con token del email.
   - Los **superusuarios** pueden además aprobar cuentas globales desde el panel de administración general (`/admin/`).
6. El usuario recibe un email de confirmación (si está configurado).
7. El usuario queda habilitado para interactuar y visualizar el contenido privado de la organización.

---

## Estilos y Diseño

Todas las páginas de autenticación usan:

- **TailwindCSS** para estilos responsivos
- **Colores del club**: los de la organización del tenant (variable CSS `--brand`), con morado (`#9B7FBF`) y amarillo (`#F4D47C`) como valores por defecto
- **Logo del club** en la parte superior
- **Optimizaciones móviles**:
  - Campos de formulario de mínimo 44px de alto
  - Font-size de 16px para prevenir zoom en iOS
  - Touch-manipulation para mejor UX táctil
- **Notificaciones toast** con Notyf

---

## Seguridad

### HTTPS

Producción ya sirve todo por **HTTPS**:

1. Certificado Let's Encrypt (comodín `*.ilovevoley.es`) gestionado por el servicio `certbot` (`certbot/dns-ovh`) en `certbot/`
2. `nginx.conf` redirige HTTP → HTTPS
3. Los URIs `http://` de Google Cloud Console solo hacen falta para desarrollo local

### CSRF Protection

El sistema está protegido contra ataques CSRF:

`CSRF_TRUSTED_ORIGINS` se lee del `.env`; debe incluir el dominio de producción y, con subdominios por club, cada origen de tenant (`https://*.ilovevoley.es`). Las cookies de sesión y CSRF usan `SESSION_COOKIE_DOMAIN`/`CSRF_COOKIE_DOMAIN` (`.ilovevoley.es` en producción) para compartir sesión entre clubes.

---

## Troubleshooting

### El usuario no puede acceder después de login

**Causa**: La cuenta o su `Membership` en ese club no están aprobadas

**Solución**:
1. Un manager/admin del club la aprueba en `/core/moderacion/`
2. O, en el admin (`/<ADMIN_URL>users/membership/` y `/<ADMIN_URL>users/user/`), marcar `is_approved = True` en la membresía y en el usuario

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
   http://localhost:8008/accounts/google/login/callback/
   http://127.0.0.1:8008/accounts/google/login/callback/
   ```
3. Configurar en Django Admin Site:
   - Domain: `localhost:8008`

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
- [Evaluación de Proveedores de Login Social (ADR 2026-10-02)](../../docs/architecture/2026-10-02-proveedores-login-social.md): Justificación técnica de exclusividad de Google frente a Apple, Facebook, Discord, etc.


