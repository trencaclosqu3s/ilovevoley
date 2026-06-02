# Multi-Tenant Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convertir VideosVoley de una app single-club a multi-tenant con subdominios, aislamiento de contenido por club y una cuenta de usuario que funciona en varios tenants.

**Architecture:** Nuevo modelo `Organization` (tenant) + `Membership` (usuario↔tenant con rol). `TenantMiddleware` resuelve el tenant desde el `Host` header y lo pone en `request.tenant`. `Video` e `Image` ganan FK a `Organization`. El branding dinámico usa CSS custom properties inyectadas desde un context processor.

**Tech Stack:** Django 5.2, PostgreSQL, django-allauth, Tailwind CSS CDN, certbot-dns-ovh (infraestructura)

**Spec:** `docs/superpowers/specs/2026-06-02-multi-tenant-design.md`

---

## Mapa de ficheros

| Fichero | Acción | Responsabilidad |
|---|---|---|
| `videosvoley/rag/` | **BORRAR** | Sistema RAG completo (no se usa) |
| `videosvoley/core/models.py` | **CREAR** | Modelo `Organization` |
| `videosvoley/core/migrations/0001_initial.py` | **CREAR** | Migración de Organization |
| `videosvoley/users/models.py` | **MODIFICAR** | Añadir modelo `Membership` |
| `videosvoley/users/migrations/0008_membership.py` | **CREAR** | Migración de Membership |
| `videosvoley/videos/models.py` | **MODIFICAR** | FK `organization` en `Video` e `Image` |
| `videosvoley/videos/migrations/0032_video_image_organization.py` | **CREAR** | Migración schema FK |
| `videosvoley/videos/migrations/0033_data_sant_josep.py` | **CREAR** | Migración de datos: crear Sant Josep, asignar contenido y usuarios |
| `videosvoley/core/middleware.py` | **MODIFICAR** | Añadir `TenantMiddleware` (passthrough en Phase 1) |
| `videosvoley/core/context_processors.py` | **CREAR** | `tenant_context`: inyecta tenant y colores |
| `videosvoley/core/mixins.py` | **CREAR** | `TenantMemberRequired`, `TenantManagerRequired`, `TenantAdminRequired`, `get_club_team_filter` |
| `videosvoley/users/adapters.py` | **MODIFICAR** | `save_user` crea `Membership` al registrarse |
| `videosvoley/videos/views.py` | **MODIFICAR** | `Video`/`Image` filtradas por tenant; `CLUB_TEAM_NAME` → `get_club_team_filter` |
| `videosvoley/videos/forms.py` | **MODIFICAR** | Recibir `organization` kwarg; usar `club_team_names` en vez de settings |
| `videosvoley/templates/base.html` | **MODIFICAR** | CSS vars `--brand`/`--brand-dark`; Tailwind config usa `var(--brand)` |
| `videosvoley/core/views.py` | **MODIFICAR** | Añadir vista `landing` |
| `videosvoley/templates/landing.html` | **CREAR** | Landing page con clubs activos |
| `videosvoley/core/urls.py` | **MODIFICAR** | URL `/` → `landing` (cuando no hay tenant) |
| `config/urls.py` | **MODIFICAR** | Eliminar `rag/`; ruta raíz → landing |
| `config/settings.py` | **MODIFICAR** | Añadir middleware, context processor; eliminar RAG de INSTALLED_APPS; `SESSION_COOKIE_DOMAIN` |
| `config/celery.py` | **MODIFICAR** | Eliminar referencia a `videosvoley.rag` |
| `nginx.conf` | **MODIFICAR** | `server_name *.ilovevoley.es` + wildcard cert |
| `tests/test_tenant.py` | **CREAR** | Tests de middleware, Membership y mixins |

---

## Fase 1 — Backend (invisible para usuarios)

---

### Task 1: Borrar sistema RAG

**Files:**
- Delete: `videosvoley/rag/` (directorio completo)
- Modify: `config/settings.py:59`
- Modify: `config/urls.py:30`
- Modify: `config/celery.py:17`

- [ ] **Step 1: Eliminar directorio RAG**

```bash
rm -rf /path/to/project/videosvoley/rag
```

- [ ] **Step 2: Eliminar de INSTALLED_APPS en settings.py**

En `config/settings.py`, eliminar la línea:
```python
'videosvoley.rag',
```

También eliminar el bloque de logging del RAG (buscar la key `'rag'` en `LOGGING`):
```python
# Buscar y eliminar este bloque en LOGGING['loggers']:
'rag': {
    ...
},
```

- [ ] **Step 3: Eliminar URL del RAG en config/urls.py**

Eliminar:
```python
path('rag/', include('videosvoley.rag.urls', namespace='rag')),
```

Y el import si existe: `from videosvoley.rag...`

- [ ] **Step 4: Eliminar referencia en config/celery.py**

Eliminar la línea:
```python
EXCLUDED_APPS = ['videosvoley.rag']
```
o el elemento `'videosvoley.rag'` si EXCLUDED_APPS tiene otros valores.

- [ ] **Step 5: Verificar que la app arranca sin errores**

```bash
docker-compose exec web python manage.py check
```
Expected: `System check identified no issues (0 silenced).`

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "chore: eliminar sistema RAG (no funcional, no se va a usar)"
```

---

### Task 2: Modelo Organization

**Files:**
- Create: `videosvoley/core/models.py`
- Create: `videosvoley/core/migrations/__init__.py` (si no existe)
- Create: `videosvoley/core/migrations/0001_initial.py` (generada por makemigrations)
- Create: `tests/test_tenant.py`

- [ ] **Step 1: Escribir test que falla**

Crear `tests/test_tenant.py`:

```python
import pytest
from django.test import TestCase


class OrganizationModelTest(TestCase):
    def test_create_organization(self):
        from videosvoley.core.models import Organization
        org = Organization.objects.create(
            slug='testclub',
            name='Test Club',
            primary_color='#ff0000',
            club_team_names={'Senior': 'TEST CLUB'},
        )
        self.assertEqual(org.slug, 'testclub')
        self.assertEqual(org.club_team_names['Senior'], 'TEST CLUB')
        self.assertTrue(org.is_active)

    def test_slug_unique(self):
        from videosvoley.core.models import Organization
        from django.db import IntegrityError
        Organization.objects.create(slug='unique', name='A')
        with self.assertRaises(IntegrityError):
            Organization.objects.create(slug='unique', name='B')
```

- [ ] **Step 2: Verificar que falla**

```bash
docker-compose exec web python manage.py test tests.test_tenant.OrganizationModelTest -v 2
```
Expected: ImportError o ModuleNotFoundError

- [ ] **Step 3: Crear videosvoley/core/models.py**

```python
from django.db import models


class Organization(models.Model):
    slug            = models.CharField(max_length=50, unique=True)
    name            = models.CharField(max_length=100)
    logo            = models.ImageField(upload_to='organizations/logos/', null=True, blank=True)
    primary_color   = models.CharField(max_length=7, default='#9B7FBF')
    secondary_color = models.CharField(max_length=7, default='#7B5FA0', blank=True)
    club_team_names = models.JSONField(default=dict, help_text='{"Senior": "SANT JOSEP", "Juvenil": "SANT JOSEP B"}')
    is_active       = models.BooleanField(default=True)
    created_at      = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Organización'
        verbose_name_plural = 'Organizaciones'

    def __str__(self):
        return self.name
```

- [ ] **Step 4: Verificar que core tiene migrations (crearlas si no existen)**

```bash
ls videosvoley/core/migrations/
```

Si no hay directorio `migrations/`, crear:
```bash
mkdir -p videosvoley/core/migrations
touch videosvoley/core/migrations/__init__.py
```

- [ ] **Step 5: Registrar Organization en el admin de core**

Editar o crear `videosvoley/core/admin.py`:
```python
from django.contrib import admin
from .models import Organization


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ['slug', 'name', 'is_active', 'created_at']
    list_filter = ['is_active']
    search_fields = ['slug', 'name']
```

- [ ] **Step 6: Generar y aplicar migración**

```bash
docker-compose exec web python manage.py makemigrations core
docker-compose exec web python manage.py migrate core
```

- [ ] **Step 7: Pasar los tests**

```bash
docker-compose exec web python manage.py test tests.test_tenant.OrganizationModelTest -v 2
```
Expected: 2 tests OK

- [ ] **Step 8: Commit**

```bash
git add videosvoley/core/models.py videosvoley/core/admin.py videosvoley/core/migrations/ tests/test_tenant.py
git commit -m "feat(core): añadir modelo Organization para multi-tenancy"
```

---

### Task 3: Modelo Membership

**Files:**
- Modify: `videosvoley/users/models.py` (añadir al final)
- Create: `videosvoley/users/migrations/0008_membership.py` (generada)
- Modify: `tests/test_tenant.py`

- [ ] **Step 1: Añadir tests de Membership**

Añadir al final de `tests/test_tenant.py`:

```python
class MembershipModelTest(TestCase):
    def setUp(self):
        from videosvoley.core.models import Organization
        from django.contrib.auth import get_user_model
        User = get_user_model()
        self.org = Organization.objects.create(slug='club1', name='Club 1')
        self.user = User.objects.create_user(username='testuser', password='pass')

    def test_create_membership(self):
        from videosvoley.users.models import Membership
        m = Membership.objects.create(
            user=self.user,
            organization=self.org,
            role='member',
            is_approved=False,
        )
        self.assertEqual(m.role, 'member')
        self.assertFalse(m.is_approved)

    def test_unique_user_organization(self):
        from videosvoley.users.models import Membership
        from django.db import IntegrityError
        Membership.objects.create(user=self.user, organization=self.org)
        with self.assertRaises(IntegrityError):
            Membership.objects.create(user=self.user, organization=self.org)
```

- [ ] **Step 2: Verificar que fallan**

```bash
docker-compose exec web python manage.py test tests.test_tenant.MembershipModelTest -v 2
```
Expected: ImportError (Membership no existe aún)

- [ ] **Step 3: Añadir Membership a videosvoley/users/models.py**

Añadir al final del fichero (después de la última clase existente):

```python
from videosvoley.core.models import Organization


class Membership(models.Model):
    ROLES = [
        ('admin', 'Admin'),
        ('manager', 'Manager'),
        ('member', 'Miembro'),
    ]

    user         = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='memberships')
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='memberships')
    role         = models.CharField(max_length=20, choices=ROLES, default='member')
    is_approved  = models.BooleanField(default=False)
    joined_at    = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'organization')
        verbose_name = 'Membresía'
        verbose_name_plural = 'Membresías'

    def __str__(self):
        return f'{self.user} @ {self.organization} ({self.role})'
```

Asegúrate de que `from django.conf import settings` ya está importado en el fichero, o añádelo al principio si no.

- [ ] **Step 4: Registrar en el admin de users**

En `videosvoley/users/admin.py`, añadir:
```python
from .models import Membership

@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    list_display = ['user', 'organization', 'role', 'is_approved', 'joined_at']
    list_filter = ['organization', 'role', 'is_approved']
    search_fields = ['user__username', 'user__email']
    actions = ['approve_memberships']

    @admin.action(description='Aprobar membresías seleccionadas')
    def approve_memberships(self, request, queryset):
        queryset.update(is_approved=True)
```

- [ ] **Step 5: Generar y aplicar migración**

```bash
docker-compose exec web python manage.py makemigrations users
docker-compose exec web python manage.py migrate users
```

- [ ] **Step 6: Pasar los tests**

```bash
docker-compose exec web python manage.py test tests.test_tenant.MembershipModelTest -v 2
```
Expected: 2 tests OK

- [ ] **Step 7: Commit**

```bash
git add videosvoley/users/models.py videosvoley/users/admin.py videosvoley/users/migrations/ tests/test_tenant.py
git commit -m "feat(users): añadir modelo Membership para control de acceso por tenant"
```

---

### Task 4: FK organization en Video e Image

**Files:**
- Modify: `videosvoley/videos/models.py` — añadir FK en `Video` e `Image`
- Create: `videosvoley/videos/migrations/0032_video_image_organization.py` (generada)

- [ ] **Step 1: Añadir FK en Video e Image en models.py**

Buscar la clase `Video` en `videosvoley/videos/models.py` y añadir el campo (tras los campos existentes, antes de `class Meta`):

```python
# En clase Video:
organization = models.ForeignKey(
    'core.Organization',
    on_delete=models.PROTECT,
    null=True,  # null=True temporalmente para la migración de datos
    blank=True,
    related_name='videos',
    verbose_name='Organización',
)
```

Buscar la clase `Image` y añadir:

```python
# En clase Image:
organization = models.ForeignKey(
    'core.Organization',
    on_delete=models.PROTECT,
    null=True,  # null=True temporalmente para la migración de datos
    blank=True,
    related_name='images',
    verbose_name='Organización',
)
```

- [ ] **Step 2: Generar migración de schema**

```bash
docker-compose exec web python manage.py makemigrations videos --name video_image_organization
docker-compose exec web python manage.py migrate videos
```

- [ ] **Step 3: Verificar que los modelos funcionan**

```bash
docker-compose exec web python manage.py shell -c "
from videosvoley.videos.models import Video, Image
print('Video fields:', [f.name for f in Video._meta.get_fields() if hasattr(f, 'name') and 'org' in f.name])
print('Image fields:', [f.name for f in Image._meta.get_fields() if hasattr(f, 'name') and 'org' in f.name])
"
```
Expected: ambos muestran `['organization']`

- [ ] **Step 4: Commit**

```bash
git add videosvoley/videos/models.py videosvoley/videos/migrations/0032_video_image_organization.py
git commit -m "feat(videos): añadir FK organization a Video e Image"
```

---

### Task 5: Migración de datos — Sant Josep

**Files:**
- Create: `videosvoley/videos/migrations/0033_data_sant_josep.py`

Esta migración crea la organización Sant Josep, asigna todos los vídeos e imágenes existentes a ella, y crea membresías para todos los usuarios actuales.

- [ ] **Step 1: Crear la migración de datos manualmente**

Crear `videosvoley/videos/migrations/0033_data_sant_josep.py`:

```python
from django.db import migrations


def create_sant_josep_and_migrate(apps, schema_editor):
    Organization = apps.get_model('core', 'Organization')
    Video = apps.get_model('videos', 'Video')
    Image = apps.get_model('videos', 'Image')
    User = apps.get_model('users', 'User')
    Membership = apps.get_model('users', 'Membership')
    Group = apps.get_model('auth', 'Group')

    org, _ = Organization.objects.get_or_create(
        slug='santjosep',
        defaults={
            'name': 'Club Sant Josep',
            'primary_color': '#9B7FBF',
            'secondary_color': '#7B5FA0',
            'club_team_names': {'Senior': 'SANT JOSEP'},
            'is_active': True,
        }
    )

    Video.objects.filter(organization__isnull=True).update(organization=org)
    Image.objects.filter(organization__isnull=True).update(organization=org)

    try:
        managers_group = Group.objects.get(name='VideoManagers')
        manager_ids = set(managers_group.user_set.values_list('id', flat=True))
    except Group.DoesNotExist:
        manager_ids = set()

    for user in User.objects.all():
        role = 'manager' if user.id in manager_ids else 'member'
        Membership.objects.get_or_create(
            user=user,
            organization=org,
            defaults={'role': role, 'is_approved': user.is_approved},
        )


def reverse_migration(apps, schema_editor):
    Organization = apps.get_model('core', 'Organization')
    Membership = apps.get_model('users', 'Membership')
    Video = apps.get_model('videos', 'Video')
    Image = apps.get_model('videos', 'Image')
    try:
        org = Organization.objects.get(slug='santjosep')
        Video.objects.filter(organization=org).update(organization=None)
        Image.objects.filter(organization=org).update(organization=None)
        Membership.objects.filter(organization=org).delete()
        org.delete()
    except Organization.DoesNotExist:
        pass


class Migration(migrations.Migration):

    dependencies = [
        ('videos', '0032_video_image_organization'),
        ('core', '0001_initial'),
        ('users', '0008_membership'),
    ]

    operations = [
        migrations.RunPython(create_sant_josep_and_migrate, reverse_migration),
    ]
```

- [ ] **Step 2: Aplicar la migración**

```bash
docker-compose exec web python manage.py migrate videos
```

- [ ] **Step 3: Verificar los datos**

```bash
docker-compose exec web python manage.py shell -c "
from videosvoley.core.models import Organization
from videosvoley.users.models import Membership
from videosvoley.videos.models import Video, Image

org = Organization.objects.get(slug='santjosep')
print(f'Org: {org}')
print(f'Videos asignados: {Video.objects.filter(organization=org).count()}')
print(f'Imágenes asignadas: {Image.objects.filter(organization=org).count()}')
print(f'Membresías creadas: {Membership.objects.filter(organization=org).count()}')
print(f'Videos sin asignar: {Video.objects.filter(organization__isnull=True).count()}')
"
```
Expected: Videos/Images = total existente, sin asignar = 0

- [ ] **Step 4: Commit**

```bash
git add videosvoley/videos/migrations/0033_data_sant_josep.py
git commit -m "feat(migration): crear org Sant Josep y migrar contenido y usuarios existentes"
```

---

### Task 6: TenantMiddleware (modo passthrough)

**Files:**
- Modify: `videosvoley/core/middleware.py`
- Modify: `config/settings.py:129`
- Modify: `tests/test_tenant.py`

En esta fase el middleware asigna Sant Josep como fallback cuando no hay subdominio reconocido, para que `ilovevoley.es` siga funcionando igual.

- [ ] **Step 1: Añadir test del middleware**

Añadir a `tests/test_tenant.py`:

```python
class TenantMiddlewareTest(TestCase):
    def setUp(self):
        from videosvoley.core.models import Organization
        self.org = Organization.objects.create(
            slug='testclub', name='Test Club', is_active=True
        )

    def test_middleware_sets_tenant_from_subdomain(self):
        from django.test import RequestFactory
        from videosvoley.core.middleware import TenantMiddleware
        factory = RequestFactory(SERVER_NAME='testclub.ilovevoley.es')
        request = factory.get('/')
        request.META['HTTP_HOST'] = 'testclub.ilovevoley.es'

        middleware = TenantMiddleware(lambda r: type('R', (), {'status_code': 200})())
        middleware(request)

        self.assertEqual(request.tenant, self.org)

    def test_middleware_passthrough_on_root_domain(self):
        from videosvoley.core.models import Organization
        from django.test import RequestFactory
        from videosvoley.core.middleware import TenantMiddleware

        root_org = Organization.objects.create(slug='santjosep', name='Sant Josep', is_active=True)
        factory = RequestFactory()
        request = factory.get('/')
        request.META['HTTP_HOST'] = 'ilovevoley.es'

        middleware = TenantMiddleware(lambda r: type('R', (), {'status_code': 200})())
        middleware(request)

        self.assertEqual(request.tenant, root_org)
```

- [ ] **Step 2: Verificar que fallan**

```bash
docker-compose exec web python manage.py test tests.test_tenant.TenantMiddlewareTest -v 2
```
Expected: ImportError o AttributeError (TenantMiddleware no existe aún)

- [ ] **Step 3: Añadir TenantMiddleware a videosvoley/core/middleware.py**

Añadir al principio del fichero los imports necesarios y la nueva clase (antes de `Error404TrackingMiddleware`):

```python
from django.http import HttpResponseNotFound
```

Añadir la clase `TenantMiddleware` antes de `Error404TrackingMiddleware`:

```python
class TenantMiddleware:
    """
    Resuelve el tenant (Organization) a partir del subdominio del Host header
    y lo pone en request.tenant.

    Modo passthrough (Fase 1): si no hay subdominio reconocido, asigna Sant Josep
    para que ilovevoley.es siga funcionando. En Fase 2 se elimina el passthrough.
    """

    PASSTHROUGH = True  # Cambiar a False en Fase 2

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        from videosvoley.core.models import Organization

        host = request.get_host().split(':')[0]
        parts = host.split('.')
        root_domain = '.'.join(parts[-2:])

        if host == root_domain:
            # Dominio raíz: passthrough a Sant Josep en Fase 1
            if self.PASSTHROUGH:
                try:
                    request.tenant = Organization.objects.get(slug='santjosep', is_active=True)
                except Organization.DoesNotExist:
                    request.tenant = None
            else:
                request.tenant = None  # Landing page en Fase 2
        else:
            subdomain = parts[0]
            try:
                request.tenant = Organization.objects.get(slug=subdomain, is_active=True)
            except Organization.DoesNotExist:
                if self.PASSTHROUGH:
                    try:
                        request.tenant = Organization.objects.get(slug='santjosep', is_active=True)
                    except Organization.DoesNotExist:
                        request.tenant = None
                else:
                    return HttpResponseNotFound()

        return self.get_response(request)
```

- [ ] **Step 4: Añadir TenantMiddleware a MIDDLEWARE en settings.py**

En `config/settings.py`, añadir como primera entrada de MIDDLEWARE (antes de SecurityMiddleware):

```python
MIDDLEWARE = [
    'videosvoley.core.middleware.TenantMiddleware',  # ← añadir aquí
    'django.middleware.security.SecurityMiddleware',
    ...
]
```

- [ ] **Step 5: Pasar los tests**

```bash
docker-compose exec web python manage.py test tests.test_tenant.TenantMiddlewareTest -v 2
```
Expected: 2 tests OK

- [ ] **Step 6: Verificar que el sitio arranca**

```bash
docker-compose exec web python manage.py check
```
Expected: `System check identified no issues (0 silenced).`

- [ ] **Step 7: Commit**

```bash
git add videosvoley/core/middleware.py config/settings.py tests/test_tenant.py
git commit -m "feat(core): añadir TenantMiddleware en modo passthrough (Fase 1)"
```

---

### Task 7: Context processor + branding dinámico en base.html

**Files:**
- Create: `videosvoley/core/context_processors.py`
- Modify: `config/settings.py` (añadir context processor)
- Modify: `videosvoley/templates/base.html` (CSS vars + Tailwind config)

- [ ] **Step 1: Crear videosvoley/core/context_processors.py**

```python
def tenant_context(request):
    org = getattr(request, 'tenant', None)
    return {
        'tenant': org,
        'tenant_color': org.primary_color if org else '#9B7FBF',
        'tenant_color_dark': org.secondary_color if org else '#7B5FA0',
    }
```

- [ ] **Step 2: Registrar en settings.py**

En `config/settings.py`, en la sección `TEMPLATES[0]['OPTIONS']['context_processors']`, añadir al final:

```python
'videosvoley.core.context_processors.tenant_context',
```

- [ ] **Step 3: Modificar base.html — CSS vars antes del script de Tailwind**

En `videosvoley/templates/base.html`, localizar la línea:
```html
<script src="https://cdn.tailwindcss.com"></script>
```

Añadir ANTES de esa línea:
```html
<style>
  :root {
    --brand: {{ tenant_color }};
    --brand-dark: {{ tenant_color_dark }};
  }
</style>
```

- [ ] **Step 4: Modificar el inline Tailwind config en base.html**

Localizar en `base.html` las líneas:
```js
'csj-purple': '#9B7FBF',
```
y
```js
'csj-purple-dark': '#7B5FA0',
```

Reemplazarlas por:
```js
'csj-purple': 'var(--brand)',
'csj-purple-dark': 'var(--brand-dark)',
```

(Las demás claves del config de Tailwind no cambian.)

- [ ] **Step 5: Añadir nombre y logo del tenant en el header de base.html**

Localizar el logo/nombre del club en el header de `base.html` y hacerlos dinámicos. Buscar el texto estático tipo `Sant Josep` o el tag `<img>` del logo y reemplazar por:

```html
{% if tenant.logo %}
  <img src="{{ tenant.logo.url }}" alt="{{ tenant.name }}" class="h-8 w-auto">
{% else %}
  <span class="font-bold text-white">{{ tenant.name|default:"VideosVoley" }}</span>
{% endif %}
```

- [ ] **Step 6: Verificar visualmente**

```bash
docker-compose up
```
Abrir `http://localhost:8000` y verificar que los colores del club siguen siendo morados (Sant Josep). Si cambias `primary_color` de Sant Josep en el admin a `#ff0000`, la página debe mostrar rojo.

- [ ] **Step 7: Commit**

```bash
git add videosvoley/core/context_processors.py config/settings.py videosvoley/templates/base.html
git commit -m "feat(core): context processor de tenant + branding dinámico en base.html"
```

---

### Task 8: Adapters allauth — crear Membership al registrarse

**Files:**
- Modify: `videosvoley/users/adapters.py`

- [ ] **Step 1: Añadir save_user a CustomAccountAdapter**

En `videosvoley/users/adapters.py`, añadir el método `save_user` a `CustomAccountAdapter` (login con email/contraseña):

```python
def save_user(self, request, user, form, commit=True):
    user = super().save_user(request, user, form, commit=commit)
    if commit and getattr(request, 'tenant', None):
        from videosvoley.users.models import Membership
        Membership.objects.get_or_create(
            user=user,
            organization=request.tenant,
            defaults={'role': 'member', 'is_approved': False},
        )
    return user
```

- [ ] **Step 2: Modificar save_user en CustomSocialAccountAdapter**

El método `save_user` ya existe en `CustomSocialAccountAdapter`. Añadir la lógica de Membership al final, antes del `return user`:

```python
def save_user(self, request, sociallogin, form=None):
    user = super().save_user(request, sociallogin, form)

    # Código existente de parent_info...
    if form and hasattr(form, 'cleaned_data'):
        parent_info = form.cleaned_data.get('parent_info', '')
        if parent_info:
            user.parent_info = parent_info
            user.save()

    # Crear Membership para el tenant actual
    if getattr(request, 'tenant', None):
        from videosvoley.users.models import Membership
        Membership.objects.get_or_create(
            user=user,
            organization=request.tenant,
            defaults={'role': 'member', 'is_approved': False},
        )

    return user
```

- [ ] **Step 3: Verificar que no hay errores de sintaxis**

```bash
docker-compose exec web python manage.py check
```
Expected: `System check identified no issues (0 silenced).`

- [ ] **Step 4: Commit**

```bash
git add videosvoley/users/adapters.py
git commit -m "feat(users): crear Membership al registrarse via allauth"
```

---

### Task 9: Mixins de autorización + helper get_club_team_filter

**Files:**
- Create: `videosvoley/core/mixins.py`
- Modify: `tests/test_tenant.py`

- [ ] **Step 1: Añadir tests**

Añadir a `tests/test_tenant.py`:

```python
class GetClubTeamFilterTest(TestCase):
    def test_returns_q_for_tenant_with_names(self):
        from videosvoley.core.models import Organization
        from videosvoley.core.mixins import get_club_team_filter
        org = Organization.objects.create(
            slug='testclub',
            name='Test',
            club_team_names={'Senior': 'TEST CLUB', 'Juvenil': 'TEST B'},
        )
        q = get_club_team_filter(org)
        # Verificar que el Q no es vacío
        self.assertIsNotNone(q)

    def test_falls_back_to_settings_when_no_tenant(self):
        from videosvoley.core.mixins import get_club_team_filter
        from django.db.models import Q
        q = get_club_team_filter(None)
        self.assertIsNotNone(q)
```

- [ ] **Step 2: Verificar que fallan**

```bash
docker-compose exec web python manage.py test tests.test_tenant.GetClubTeamFilterTest -v 2
```
Expected: ImportError

- [ ] **Step 3: Crear videosvoley/core/mixins.py**

```python
from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db.models import Q


def get_club_team_filter(tenant):
    """Retorna un Q que filtra partidos por los equipos del tenant."""
    if tenant and tenant.club_team_names:
        team_names = list(tenant.club_team_names.values())
    else:
        fallback = getattr(settings, 'CLUB_TEAM_NAME', 'SANT JOSEP')
        team_names = [fallback]

    q = Q()
    for name in team_names:
        q |= (
            Q(home_team__name__icontains=name) |
            Q(away_team__name__icontains=name) |
            Q(home_team_text__icontains=name) |
            Q(away_team_text__icontains=name)
        )
    return q


class TenantMemberRequired(LoginRequiredMixin):
    """
    Requiere Membership aprobada en request.tenant.
    Subclases pueden definir required_roles para exigir un rol concreto.
    """
    required_roles = None  # None = cualquier member aprobado

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if request.user.is_superuser:
            return super().dispatch(request, *args, **kwargs)
        tenant = getattr(request, 'tenant', None)
        if not tenant:
            raise PermissionDenied
        from videosvoley.users.models import Membership
        qs = Membership.objects.filter(
            user=request.user,
            organization=tenant,
            is_approved=True,
        )
        if self.required_roles:
            qs = qs.filter(role__in=self.required_roles)
        if not qs.exists():
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)


class TenantManagerRequired(TenantMemberRequired):
    """Requiere role manager o admin en el tenant."""
    required_roles = ['manager', 'admin']


class TenantAdminRequired(TenantMemberRequired):
    """Requiere role admin en el tenant."""
    required_roles = ['admin']
```

- [ ] **Step 4: Pasar los tests**

```bash
docker-compose exec web python manage.py test tests.test_tenant.GetClubTeamFilterTest -v 2
```
Expected: 2 tests OK

- [ ] **Step 5: Commit**

```bash
git add videosvoley/core/mixins.py tests/test_tenant.py
git commit -m "feat(core): mixins de autorización por tenant + helper get_club_team_filter"
```

---

### Task 10: Actualizar views.py — filtrar por tenant

**Files:**
- Modify: `videosvoley/videos/views.py`

Hay dos cambios en views.py:
1. Los queries de `Video` e `Image` deben filtrar por `request.tenant`
2. Las referencias a `CLUB_TEAM_NAME`/`settings.CLUB_TEAM_NAME` deben usar `get_club_team_filter(request.tenant)`

- [ ] **Step 1: Añadir imports al principio de views.py**

Al principio de `videosvoley/videos/views.py`, añadir:

```python
from videosvoley.core.mixins import get_club_team_filter
```

- [ ] **Step 2: Reemplazar referencias a CLUB_TEAM_NAME en views.py**

Buscar todos los bloques donde aparece:
```python
CLUB_TEAM_NAME = 'SANT JOSEP'
```
o
```python
CLUB_TEAM_NAME = getattr(settings, 'CLUB_TEAM_NAME', 'SANT JOSEP')
```
seguidos de un filtro Q manual.

Reemplazar el patrón completo. Ejemplo de antes:
```python
CLUB_TEAM_NAME = 'SANT JOSEP'
matches = Match.objects.filter(
    Q(home_team__name__icontains=CLUB_TEAM_NAME) |
    Q(away_team__name__icontains=CLUB_TEAM_NAME) |
    Q(home_team_text__icontains=CLUB_TEAM_NAME) |
    Q(away_team_text__icontains=CLUB_TEAM_NAME)
)
```

Ejemplo de después:
```python
matches = Match.objects.filter(get_club_team_filter(request.tenant))
```

Hacer lo mismo para cada uno de los ~8 lugares donde aparece este patrón. Para el caso `getattr(settings, 'CLUB_TEAM_NAME', 'SANT JOSEP')` en views que tienen `request`:
```python
# antes
club_team_name = getattr(settings, 'CLUB_TEAM_NAME', 'SANT JOSEP')
# (seguido de Q filter manual)

# después
# (usar directamente get_club_team_filter(request.tenant))
```

- [ ] **Step 3: Añadir filtro por tenant en queries de Video e Image**

Buscar en views.py los lugares donde se hace `Video.objects.all()` o `Video.objects.filter(...)` sin filtro de tenant, y añadir el filtro. El patrón:

```python
# Antes (típico en listados)
videos = Video.objects.filter(...)

# Después
videos = Video.objects.filter(organization=request.tenant, ...)
```

Y para Image:
```python
images = Image.objects.filter(organization=request.tenant, ...)
```

**Nota:** Las vistas de detalle de partido, liga y vídeo concreto no necesitan filtro por tenant en el objeto en sí (un vídeo tiene una ID única), pero sí deben verificar que `video.organization == request.tenant`. Añadir comprobación:

```python
# En video_detail y image_detail:
if video.organization != request.tenant and not request.user.is_superuser:
    raise Http404
```

- [ ] **Step 4: Reemplazar decoradores is_approved + VideoManagers por mixins**

Las vistas basadas en funciones usan `@user_passes_test(user_is_approved)` y `@user_passes_test(lambda u: u.groups.filter(name='VideoManagers').exists())`. Estas se pueden mantener tal cual en Fase 1 — los mixins se usarán en vistas nuevas. La migración completa de decoradores a mixins es trabajo para después de confirmar que todo funciona.

- [ ] **Step 5: Verificar que la app arranca y responde**

```bash
docker-compose exec web python manage.py check
```
Expected: `System check identified no issues (0 silenced).`

Abrir `http://localhost:8000/videos/` y verificar que lista vídeos normalmente.

- [ ] **Step 6: Commit**

```bash
git add videosvoley/videos/views.py
git commit -m "feat(videos): filtrar Video e Image por tenant, usar get_club_team_filter"
```

---

### Task 11: Actualizar forms.py — recibir organization

**Files:**
- Modify: `videosvoley/videos/forms.py`

Los formularios usan `settings.CLUB_TEAM_NAME` para filtrar el queryset de partidos. Deben recibir la organización como parámetro.

- [ ] **Step 1: Modificar VideoForm.__init__ para aceptar organization**

En `videosvoley/videos/forms.py`, en la clase `VideoForm`, modificar `__init__`:

```python
def __init__(self, *args, **kwargs):
    self.organization = kwargs.pop('organization', None)
    super().__init__(*args, **kwargs)
    self.fields['match'].required = False
    self._setup_match_queryset()
```

- [ ] **Step 2: Modificar _setup_match_queryset para usar organization**

En `_setup_match_queryset`, reemplazar:
```python
club_team_name = getattr(settings, 'CLUB_TEAM_NAME', 'SANT JOSEP')
```

Por:
```python
from videosvoley.core.mixins import get_club_team_filter
club_filter = get_club_team_filter(self.organization)
```

Y luego usar `club_filter` en el Q filter en lugar de construirlo manualmente. Buscar el bloque `club_query = (...)` y reemplazarlo por `club_query = club_filter`.

- [ ] **Step 3: Repetir el mismo patrón en los otros 4 formularios que usan CLUB_TEAM_NAME**

Los formularios afectados (buscar las líneas 278, 913, 1021, 1082):

Para cada formulario que tenga `club_team_name = getattr(settings, 'CLUB_TEAM_NAME', 'SANT JOSEP')`:
1. Añadir `self.organization = kwargs.pop('organization', None)` en `__init__`
2. Reemplazar la línea de `club_team_name` por `from videosvoley.core.mixins import get_club_team_filter` + `club_filter = get_club_team_filter(self.organization)`
3. Usar `club_filter` en el Q

- [ ] **Step 4: Actualizar las vistas que instancian estos formularios**

En `videosvoley/videos/views.py`, buscar cada lugar donde se instancia `VideoForm(...)` o los otros formularios modificados, y añadir `organization=request.tenant`:

```python
# Antes
form = VideoForm(request.POST)
# Después
form = VideoForm(request.POST, organization=request.tenant)

# Antes
form = VideoForm(instance=video)
# Después
form = VideoForm(instance=video, organization=request.tenant)
```

- [ ] **Step 5: Verificar que los formularios funcionan**

```bash
docker-compose up
```
Navegar a `http://localhost:8000/videos/nuevo/` (con usuario VideoManager) y verificar que el select de partidos muestra los partidos del club.

- [ ] **Step 6: Commit**

```bash
git add videosvoley/videos/forms.py videosvoley/videos/views.py
git commit -m "feat(videos): formularios reciben organization para filtrar partidos por tenant"
```

---

## Fase 2 — Activar subdominio

---

### Task 12: Landing page

**Files:**
- Modify: `videosvoley/core/views.py`
- Create: `videosvoley/templates/landing.html`
- Modify: `config/urls.py`

- [ ] **Step 1: Añadir vista landing a videosvoley/core/views.py**

Añadir al final del fichero:

```python
def landing(request):
    from videosvoley.core.models import Organization
    organizations = Organization.objects.filter(is_active=True).order_by('name')

    user_org_ids = set()
    if request.user.is_authenticated:
        from videosvoley.users.models import Membership
        user_org_ids = set(
            Membership.objects.filter(
                user=request.user, is_approved=True
            ).values_list('organization_id', flat=True)
        )

    return render(request, 'landing.html', {
        'organizations': organizations,
        'user_org_ids': user_org_ids,
    })
```

- [ ] **Step 2: Crear videosvoley/templates/landing.html**

```html
{% extends "base.html" %}

{% block title %}Bienvenido — VideosVoley{% endblock %}

{% block content %}
<div class="min-h-screen flex flex-col items-center justify-center px-4 py-12">
  <h1 class="text-3xl font-bold text-gray-800 dark:text-white mb-2">VideosVoley</h1>
  <p class="text-gray-500 dark:text-gray-400 mb-10">Selecciona tu club para continuar</p>

  <div class="grid grid-cols-1 sm:grid-cols-2 gap-6 w-full max-w-2xl">
    {% for org in organizations %}
    <a href="//{{ org.slug }}.ilovevoley.es/"
       class="block bg-white dark:bg-gray-800 rounded-xl shadow-md p-6 border-t-4 hover:shadow-lg transition-shadow"
       style="border-color: {{ org.primary_color }};">
      {% if org.logo %}
        <img src="{{ org.logo.url }}" alt="{{ org.name }}" class="h-12 w-auto mb-3">
      {% else %}
        <div class="h-12 w-12 rounded-full mb-3 flex items-center justify-center text-white font-bold text-xl"
             style="background-color: {{ org.primary_color }};">
          {{ org.name|first }}
        </div>
      {% endif %}
      <h2 class="text-lg font-semibold text-gray-800 dark:text-white">{{ org.name }}</h2>
      {% if org.id in user_org_ids %}
        <span class="text-xs text-green-600 dark:text-green-400 font-medium">✓ Tienes acceso</span>
      {% endif %}
    </a>
    {% empty %}
    <p class="col-span-2 text-center text-gray-400">No hay clubs activos.</p>
    {% endfor %}
  </div>
</div>
{% endblock %}
```

- [ ] **Step 3: Registrar URL en config/urls.py**

La URL raíz actualmente redirige a `/videos/`. Cuando no hay tenant (`request.tenant is None`), debe ir a la landing. Añadir la URL de landing:

```python
from videosvoley.core.views import landing

# Añadir antes de la línea con RedirectView:
path('', landing, name='landing'),
```

**Nota:** El middleware en Fase 2 pondrá `request.tenant = None` para el dominio raíz. La landing no necesita tenant, así que funciona con `tenant = None`.

- [ ] **Step 4: Verificar la landing**

```bash
docker-compose up
```
Abrir `http://localhost:8000/` y verificar que muestra la tarjeta de Sant Josep.

- [ ] **Step 5: Commit**

```bash
git add videosvoley/core/views.py videosvoley/templates/landing.html config/urls.py
git commit -m "feat(core): landing page en dominio raíz con selección de tenant"
```

---

### Task 13: Settings + desactivar passthrough

**Files:**
- Modify: `config/settings.py`
- Modify: `videosvoley/core/middleware.py`

- [ ] **Step 1: Añadir SESSION_COOKIE_DOMAIN en settings.py (producción)**

En `config/settings.py`, en la sección de configuración de sesión (o al final de las settings de producción):

```python
# Multi-tenant: cookie compartida entre subdominios
SESSION_COOKIE_DOMAIN = config('SESSION_COOKIE_DOMAIN', default=None)
CSRF_COOKIE_DOMAIN = config('SESSION_COOKIE_DOMAIN', default=None)
```

En el fichero `.env` de producción (NO en development):
```
SESSION_COOKIE_DOMAIN=.ilovevoley.es
```

- [ ] **Step 2: Añadir ilovevoley.es a ALLOWED_HOSTS y CSRF_TRUSTED_ORIGINS**

En `config/settings.py`, verificar que ALLOWED_HOSTS incluye wildcard:
```python
ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='localhost,127.0.0.1').split(',')
```

En `.env` de producción, actualizar:
```
ALLOWED_HOSTS=ilovevoley.es,*.ilovevoley.es,santjosep.ilovevoley.es
CSRF_TRUSTED_ORIGINS=https://ilovevoley.es,https://*.ilovevoley.es
```

- [ ] **Step 3: Desactivar modo passthrough en TenantMiddleware**

En `videosvoley/core/middleware.py`, cambiar:
```python
PASSTHROUGH = True  # Cambiar a False en Fase 2
```
por:
```python
PASSTHROUGH = False
```

- [ ] **Step 4: Verificar localmente con hosts**

Añadir a `/etc/hosts`:
```
127.0.0.1 santjosep.localhost
127.0.0.1 localhost
```

En `.env` de desarrollo:
```
ALLOWED_HOSTS=localhost,santjosep.localhost,127.0.0.1
```

Acceder a `http://santjosep.localhost:8000/videos/` y verificar contenido de Sant Josep.
Acceder a `http://localhost:8000/` y verificar que muestra la landing.

- [ ] **Step 5: Commit**

```bash
git add config/settings.py videosvoley/core/middleware.py
git commit -m "feat(settings): SESSION_COOKIE_DOMAIN + desactivar passthrough del middleware"
```

---

### Task 14: Infraestructura — nginx y certificado wildcard

Esta tarea es de operaciones en el servidor de producción, no de código.

- [ ] **Step 1: Instalar certbot-dns-ovh en el servidor**

```bash
pip install certbot certbot-dns-ovh
```

- [ ] **Step 2: Crear fichero de credenciales OVH**

Crear `~/ovh.ini` con las credenciales de la API de OVH (obtenerlas desde el panel de OVH → API):
```ini
dns_ovh_endpoint = ovh-eu
dns_ovh_application_key = XXXXXXXX
dns_ovh_application_secret = XXXXXXXX
dns_ovh_consumer_key = XXXXXXXX
```
```bash
chmod 600 ~/ovh.ini
```

- [ ] **Step 3: Obtener certificado wildcard**

```bash
certbot certonly \
  --dns-ovh \
  --dns-ovh-credentials ~/ovh.ini \
  -d ilovevoley.es \
  -d '*.ilovevoley.es'
```

- [ ] **Step 4: Actualizar nginx.conf**

Modificar la directiva `server_name`:
```nginx
# Antes
server_name ilovevoley.es;

# Después
server_name ilovevoley.es *.ilovevoley.es;
```

Actualizar las rutas del certificado SSL a las nuevas del wildcard:
```nginx
ssl_certificate     /etc/letsencrypt/live/ilovevoley.es/fullchain.pem;
ssl_certificate_key /etc/letsencrypt/live/ilovevoley.es/privkey.pem;
```

- [ ] **Step 5: Añadir subdominio DNS en OVH**

En el panel DNS de OVH para `ilovevoley.es`, añadir:
```
*.ilovevoley.es  CNAME  ilovevoley.es
```
o un registro A que apunte a la misma IP.

- [ ] **Step 6: Recargar nginx y verificar**

```bash
nginx -t
systemctl reload nginx
```

Acceder a `https://santjosep.ilovevoley.es` y verificar certificado válido y contenido correcto.

- [ ] **Step 7: Commit de nginx.conf**

```bash
git add nginx.conf
git commit -m "infra: nginx wildcard *.ilovevoley.es + rutas certificado wildcard"
```

---

## Verificación final (Fase 1 + 2)

- [ ] `https://ilovevoley.es` → muestra landing con tarjeta Sant Josep
- [ ] `https://santjosep.ilovevoley.es/videos/` → lista vídeos de Sant Josep
- [ ] Login en `santjosep.ilovevoley.es` → sesión activa al visitar `ilovevoley.es` (misma cookie)
- [ ] Usuario sin Membership en un subdominio → página de error o solicitud de acceso
- [ ] Cambiar `primary_color` de Sant Josep en el admin → los colores de la web cambian
- [ ] Añadir nueva Organization `soller` → `soller.ilovevoley.es` resuelve correctamente

---

## Fase 3 — Añadir nuevo tenant (operacional, sin código)

1. En el admin de Django, crear `Organization(slug='soller', name='Sóller Vòlei', primary_color='...', club_team_names={...})`
2. En OVH DNS, el wildcard ya cubre `soller.ilovevoley.es` — no hay que hacer nada
3. Crear un usuario admin para el nuevo tenant y asignarle `Membership(role='admin', is_approved=True)`
4. Los nuevos usuarios que se registren en `soller.ilovevoley.es` quedarán pendientes de aprobación por ese admin
