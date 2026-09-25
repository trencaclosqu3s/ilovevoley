# Diseño Multi-Tenant — VideosVoley

**Fecha:** 2026-06-02  
**Estado:** Aprobado

## Contexto

VideosVoley es actualmente una plataforma de gestión de vídeos e imágenes para el Club Sant Josep de voleibol. La plataforma está personalizada para un único club: el nombre del equipo, los colores y los filtros de contenido están hardcodeados en `settings.py` y en el código.

El detonante del cambio: Marc (hijo de Paula, quien graba los partidos) se incorpora a la Selecció Balear este verano y el año próximo cambia de club. Se quiere que pueda usar la misma plataforma, pero los usuarios de un club no deben ver el contenido de otro.

**Escala prevista:** 2-3 clubs, gestionados manualmente por el administrador. No es un producto SaaS ni requiere auto-servicio.

## Decisiones de diseño

| Decisión | Elección | Motivo |
|---|---|---|
| Separación de tenants | Subdominio por club | Más profesional que rutas; OVH con wildcard cert es viable |
| Datos federativos | Compartidos entre tenants | Son datos públicos; el filtro por club sigue siendo la lente |
| Una cuenta / varios clubs | Sí, via Membership | El caso Marc (Sant Josep → Sóller) requiere una sola cuenta |
| Gestión de tenants | Manual por admin | Escala de 2-3 clubs no necesita auto-servicio |
| RAG | Borrado total | Era un test que no funciona; no se va a usar |

## Modelo de datos

### `Organization` (app: `videosvoley.core`)

Representa un tenant — un club que usa la plataforma.

```python
class Organization(models.Model):
    slug            = CharField(max_length=50, unique=True)   # subdominio: "santjosep"
    name            = CharField(max_length=100)                # "Club Sant Josep"
    logo            = ImageField(null=True, blank=True)
    primary_color   = CharField(max_length=7, default='#6d28d9')  # hex
    secondary_color = CharField(max_length=7, null=True, blank=True)
    club_team_names = JSONField(default=dict)   # {"Senior": "SANT JOSEP", "Juvenil": "SANT JOSEP B"}
    is_active       = BooleanField(default=True)
    created_at      = DateTimeField(auto_now_add=True)
```

`club_team_names` reemplaza `CLUB_TEAM_NAME` y `CLUB_TEAM_NAMES` de `settings.py`.

### `Membership` (app: `videosvoley.users`)

Vincula un usuario a un tenant con un rol y estado de aprobación.

```python
class Membership(models.Model):
    ROLES = [('admin', 'Admin'), ('manager', 'Manager'), ('member', 'Miembro')]

    user         = ForeignKey(User, on_delete=CASCADE)
    organization = ForeignKey(Organization, on_delete=CASCADE)
    role         = CharField(max_length=20, choices=ROLES, default='member')
    is_approved  = BooleanField(default=False)
    joined_at    = DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'organization')
```

**Roles:**
- `admin` — aprueba usuarios, gestiona el tenant, sube contenido
- `manager` — sube vídeos e imágenes, comenta (equivale al grupo `VideoManagers` actual)
- `member` — visualiza contenido, comenta

### Cambios en modelos existentes

**`Video` e `Image`**: añadir `organization = ForeignKey(Organization, on_delete=PROTECT)`.

**`User`**: sin cambios estructurales. `User.is_approved` se conserva como flag de "cuenta activa a nivel plataforma" (escudo anti-spam). La aprobación efectiva para acceder a un tenant es `Membership.is_approved`.

**Modelos federativos** (`League`, `Team`, `Match`, `Standing`, `Club`, `Category`): sin cambios. Son datos compartidos entre todos los tenants.

## Middleware y resolución de tenant

### `TenantMiddleware` (app: `videosvoley.core`)

Se coloca antes de `AuthenticationMiddleware` en `MIDDLEWARE`.

```python
class TenantMiddleware:
    def __call__(self, request):
        host = request.get_host().split(':')[0]        # "santjosep.ilovevoley.es"
        subdomain = host.split('.')[0]                  # "santjosep"
        root_domain = '.'.join(host.split('.')[-2:])    # "ilovevoley.es"

        if host == root_domain:
            request.tenant = None   # dominio raíz → landing page
        else:
            try:
                request.tenant = Organization.objects.get(slug=subdomain, is_active=True)
            except Organization.DoesNotExist:
                return HttpResponseNotFound()

        return self.get_response(request)
```

**Desarrollo local:** añadir entradas en `/etc/hosts`:
```
127.0.0.1 santjosep.localhost
127.0.0.1 soller.localhost
```
El middleware funciona igual. `SESSION_COOKIE_DOMAIN = None` en desarrollo (por defecto).

### Scoping en vistas

```python
# Patrón estándar en todas las vistas con contenido de tenant
videos = Video.objects.filter(organization=request.tenant)
```

### Mixins de autorización (app: `videosvoley.core`)

```python
class TenantMemberRequired(LoginRequiredMixin):
    # Comprueba Membership(user, tenant, is_approved=True)

class TenantManagerRequired(TenantMemberRequired):
    # Comprueba role in ['manager', 'admin']

class TenantAdminRequired(TenantMemberRequired):
    # Comprueba role == 'admin'
```

Reemplazan los decoradores y comprobaciones de grupo actuales.

## Branding dinámico

### Context processor (app: `videosvoley.core`)

```python
def tenant_context(request):
    org = getattr(request, 'tenant', None)
    return {
        'tenant': org,
        'tenant_color': org.primary_color if org else '#6d28d9',
    }
```

### Base template

```html
<!-- base.html — en <head> -->
<style>
  :root { --brand: {{ tenant_color }}; }
</style>
{% if tenant.logo %}
  <img src="{{ tenant.logo.url }}" alt="{{ tenant.name }}">
{% endif %}
```

### Tailwind config

```js
// tailwind.config.js
colors: { brand: 'var(--brand)' }
```

`csj-purple` se mantiene como alias durante la transición (`csj-purple: 'var(--brand)'`) y se elimina una vez completado el renombrado en templates y `forms.py`.

## Autenticación y registro

### Registro en un subdominio

1. Usuario llega a `soller.ilovevoley.es/accounts/signup/`
2. Se crea `User` normalmente via allauth
3. Un **adapter de allauth** sobrescribe `save_user()` para crear `Membership(user, org=request.tenant, role='member', is_approved=False)` — los signals no tienen acceso a `request`, por eso se usa el adapter que sí lo tiene
4. Notificación al admin del tenant
5. Admin aprueba → `Membership.is_approved = True`

### Usuario existente en tenant nuevo

Si un usuario con sesión activa visita un subdominio donde no tiene `Membership`, ve una pantalla de "Solicitar acceso a [Club]". Al confirmar, se crea la `Membership` pendiente y fluye por el proceso de aprobación normal.

### Google OAuth — sin cambios

El callback de Google sigue siendo uno solo en el dominio raíz:
```
https://ilovevoley.es/accounts/google/login/callback/
```
La cookie de sesión cross-domain hace que el login sea transparente entre subdominios.

### Ajuste en settings (producción)

```python
SESSION_COOKIE_DOMAIN = '.ilovevoley.es'   # punto inicial obligatorio
```

## Landing page (dominio raíz)

`ilovevoley.es` muestra una página pública con las organizaciones activas. Si el usuario está autenticado, se destacan los clubs a los que pertenece. Cada tarjeta enlaza al subdominio del club.

No requiere autenticación. Es la entrada natural para usuarios nuevos que reciben un link al dominio raíz.

## Infraestructura

### Certificado wildcard

```bash
pip install certbot-dns-ovh

certbot certonly \
  --dns-ovh \
  --dns-ovh-credentials ~/ovh.ini \
  -d ilovevoley.es \
  -d *.ilovevoley.es
```

La renovación automática existente no cambia. Cada nuevo subdominio queda cubierto sin acción adicional.

### nginx

```nginx
# Cambio mínimo en nginx.conf
server_name ilovevoley.es *.ilovevoley.es;

ssl_certificate     /path/to/fullchain.pem;
ssl_certificate_key /path/to/privkey.pem;
```

El admin de Django se mantiene en la URL con string aleatorio actual — sin cambios.

## Estrategia de migración

### Fase 1 — Infraestructura invisible (sin impacto para usuarios)

1. Borrar sistema RAG completo: directorio `videosvoley/rag/` y todas sus referencias en URLs, settings, imports.
2. Crear modelos `Organization` y `Membership`, generar y aplicar migraciones.
3. Insertar fila `Organization(slug="santjosep", name="Club Sant Josep", primary_color="#6d28d9", club_team_names={...})`.
4. Migración de datos: asignar `organization=santjosep` a todos los `Video` e `Image` existentes.
5. Crear `Membership` para todos los usuarios existentes, mapeando grupo `VideoManagers` → role `manager`, resto → role `member`, todos con `is_approved=True`.
6. Instalar `TenantMiddleware` en modo passthrough: si no hay subdominio válido, asigna Sant Josep por defecto (para que `ilovevoley.es` siga funcionando igual).
7. Añadir context processor, sin activar branding dinámico aún.

**Resultado:** el sitio funciona exactamente igual en `ilovevoley.es`.

### Fase 2 — Activar subdominio Sant Josep

1. Obtener certificado wildcard via certbot-dns-ovh.
2. DNS: `santjosep.ilovevoley.es` apunta al mismo servidor.
3. Actualizar `nginx.conf`: `server_name ilovevoley.es *.ilovevoley.es`.
4. `SESSION_COOKIE_DOMAIN = '.ilovevoley.es'` en settings de producción.
5. Activar branding dinámico: `csj-purple → brand` en templates y `forms.py`.
6. `ilovevoley.es` raíz → landing page con clubs disponibles.
7. Middleware deja de hacer passthrough: subdominio desconocido → 404.

**Resultado:** usuarios acceden a `santjosep.ilovevoley.es` con el mismo contenido de siempre.

### Fase 3 — Añadir nuevo tenant

1. Insertar fila en `Organization` con slug, colores, nombres de equipo.
2. DNS: `soller.ilovevoley.es` (el wildcard ya lo cubre).
3. Crear primer usuario admin del tenant.

**Resultado:** nuevo club operativo en minutos, sin tocar código ni nginx.

## Lo que NO cambia

- URL de Django admin (string aleatorio en producción)
- Modelos federativos (`League`, `Team`, `Match`, `Standing`, `Club`, `Category`)
- Configuración OAuth de Google (un solo callback URL)
- docker-compose
- Sistema de imágenes con Google Vision API
- Google Calendar sync
- Sistema de scraping de datos federativos
