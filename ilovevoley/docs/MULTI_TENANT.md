# Sistema Multi-Tenant por Organización

Este documento detalla la arquitectura y funcionamiento del sistema multi-tenant implementado en I Love Voley.

## 🎯 Objetivo y Concepto

La plataforma permite alojar múltiples clubes y organizaciones deportivas de forma independiente. Cada club dispone de su propio entorno visual y de contenidos, mientras que los datos federativos públicos (ligas, calendarios, partidos oficiales) se comparten entre organizaciones.

## 🏛️ Modelo de Datos

### `Organization` (`ilovevoley.core.models.Organization`)

Representa a cada club u organización en la plataforma:

- **`slug`**: Identificador único que coincide con el subdominio (ej: `santjosep` para `santjosep.ilovevoley.es`).
- **`name`**: Nombre completo del club (ej: "Club Voleibol Sant Josep").
- **`club`**: Clave foránea opcional a `teams.Club` que vincula la organización con su club federativo oficial. Permite detectar automáticamente qué equipos y partidos pertenecen a este club sin necesidad de configuraciones estáticas.
- **`logo`**: Logotipo específico del club para el navbar y encabezados.
- **`primary_color`** y **`secondary_color`**: Colores corporativos hexadecimales aplicados dinámicamente en el tema visual.
- **`default_home`**: Sección de inicio del tenant (`videos`, `images`, `competitions`). Define a dónde redirige la raíz del tenant y el logo del navbar.
- **`instagram_url`**: Perfil de Instagram para enlaces sociales.
- **`club_team_names`**: Diccionario JSON con nombres o prefijos de equipo por categoría (usado como fallback o ajuste fino).

### `Membership` (`ilovevoley.users.models.Membership`)

Gestiona la pertenencia de un usuario a un club:

- **`user`**: Usuario Django.
- **`organization`**: Club u organización a la que pertenece.
- **`role`**: Rol dentro de la organización:
  - `admin`: Administrador de la organización.
  - `manager`: Gestor o moderador del club (puede aprobar membresías y subir contenido).
  - `member`: Miembro estándar (acceso a ver contenido y comentar).
- **`is_approved`**: Booleano que indica si la membresía ha sido aprobada.

## 🌐 Resolución de Tenant (`TenantMiddleware`)

El middleware [`TenantMiddleware`](file:///Users/jamartinmari/PycharmProjects/videosvoley/ilovevoley/core/middleware.py) intercepta cada petición HTTP y resuelve la organización según el host:

1. Extrae el host de `request.META['HTTP_HOST']`.
2. Si la petición accede al dominio raíz sin subdominio (ej: `ilovevoley.es`), `request.tenant` es `None` y se muestra la landing general.
3. Si la petición accede a un subdominio reservado (ej: `www.ilovevoley.es`), emite una redirección permanente HTTP 301 al dominio raíz manteniendo ruta y query params.
4. Si la petición accede al subdominio de un club (ej: `santjosep.ilovevoley.es`), busca la organización activa por `slug`.
5. Si el subdominio no existe o está inactivo, devuelve `404 Not Found`.
6. Rutas globales (como la suscripción a calendarios ICS) están exentas de la restricción de tenant.

## 🛡️ Moderación Descentralizada de Membresías

A diferencia de los paneles monolíticos clásicos:

- **Los managers de cada club** tienen acceso a `/core/moderacion/` para aprobar las solicitudes de membresía (`Membership`) de su propio club, sin necesidad de permisos de superusuario global.
- Al registrarse un usuario en el subdominio de un club, se envía una notificación por email a los administradores y managers de esa organización con un enlace de aprobación directa mediante token seguro.
- Las imágenes y contenidos globales requieren supervisión de administradores con permisos de staff.

## 🏠 Homepage Configurable por Organización

Cada organización puede seleccionar en el admin su página de inicio (`default_home`):
- **Vídeos** (`videos`): Redirige a `/content/` (`content:video_list`).
- **Galería de Imágenes** (`images`): Redirige a `/content/imagenes/` (`content:image_gallery`).
- **Competiciones y Partidos** (`competitions`): Redirige a `/competitions/ligas/` (`competitions:league_list`).

El enlace del logotipo y el nombre en el navbar apuntan automáticamente a la URL configurada mediante la propiedad `organization.home_url_name`.
