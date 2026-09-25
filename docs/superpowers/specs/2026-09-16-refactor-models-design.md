# Refactor de la app monolítica `videos`

- **Fecha**: 2026-09-16
- **Estado**: diseño aprobado, pendiente de plan de implementación
- **Autor**: Bert + Claude

## 1. Contexto y objetivo

La app `videos` nació como una landing para publicar vídeos de partidos y ha
crecido por acumulación hasta absorber galería de imágenes, scraping de la
federación, plantillas, clubes, equipos y multi-tenant. Hoy concentra seis
ficheros monolíticos:

| Fichero | Líneas |
|---|---|
| `views.py` | 2797 |
| `scraping.py` | 2518 |
| `tasks.py` | 1928 |
| `models.py` | 1433 |
| `admin.py` | 1398 |
| `forms.py` | 1104 |

El objetivo es recuperar fronteras de dominio legibles **sin arriesgar los datos
de producción y sin volver a quedarse a medias**, que es lo que ocurrió en el
intento anterior.

Conviene registrar que `models.py` no es el peor fichero del proyecto: `views.py`
casi lo duplica. El refactor los cubre todos, con `models.py` primero por ser el
ancla que el resto referencia.

## 2. Veredicto sobre `origin/refactor_apps`

La rama previa (divergió el 2025-10-26; main lleva 190 commits encima) se
descarta entera salvo su mapa de dominio.

**Lo que se conserva**: la descomposición en cuatro dominios, que es acertada —
`content` (Video, Comment, Image), `competitions` (League, Match, Standing,
ScrapingEndpoint), `teams` (Club, Team) y `rosters` (Person, PlayerRole,
StaffRole). Con una corrección: la rama metía `Category` dentro de `content`, y
este diseño la extrae a `core` por las razones de 7.2.

**Lo que se descarta y por qué**: cada app nueva llevaba un `0001_initial.py`
lleno de `CreateModel`, es decir, **creaba tablas nuevas y vacías en paralelo a
las existentes** y después copiaba las filas a mano con una batería de comandos
(`migrate_content_data`, `migrate_teams_data`, `migrate_competitions_data`,
`migrate_rosters_data`, `update_foreign_keys`, `verify_migration_integrity`).
Sobre una base de datos viva eso implica doble esquema temporal, preservación
manual de claves primarias, FKs cruzadas entre apps viejas y nuevas y ningún
rollback limpio. El propio `fix_migrations_step_by_step.md` de la rama, con sus
`migrate --fake` encadenados, documenta que ya estaban peleando contra el grafo
de migraciones antes de terminar.

Existía la alternativa correcta y no se usó: `SeparateDatabaseAndState` con
`db_table` fijado, que es la que adopta este diseño (sección 7).

Además la rama es irrecuperable por antigüedad: 9 migraciones nuevas en `videos`
y cambios estructurales posteriores que desconoce (multi-tenant con FK
`Organization` en Video e Image, fases de liga, variantes de equipo, scraping
RFEVB, categorías M2M).

## 3. Estado actual medido

Datos obtenidos de la base de datos de producción el 2026-09-16:

| Métrica | Valor |
|---|---|
| Modelos en `models.py` | 15 (+3 managers) |
| Imports de `videos.models` | 84, repartidos en 38 ficheros |
| Migraciones en `videos` | 35 |
| `{% url %}` en templates | 171 |
| `reverse()` / `redirect()` en Python | 48 |
| Tareas Celery | 16, **todas con `name=` explícito** |
| `GenericForeignKey` / `ContentType` en código propio | ninguno |

Datos de negocio relevantes para la fase 3:

| Modelo | Filas |
|---|---|
| `Player` | 21 (18 ya existen como `Person`, 3 no) |
| `Staff` | 3 |
| `Person` / `PlayerRole` / `StaffRole` | 33 / 36 / 6 |
| `League` | 91 (13 con `category` deprecado, 90 con `categories` M2M) |
| Ligas con `category` y sin `categories` | **1** |
| Ligas donde `category` queda fuera de `categories` | **0** |

Tooling: **no hay pytest** (los tests son `django.test.TestCase`), **no hay CI**
(solo dependabot) y **no existe `CLAUDE.md`** (`WARP.md` es un symlink roto).
`videosvoley/core/tasks/` existe vacío, residuo de un intento previo.

## 4. Principios

1. **Cada fase debe ser verificable por una máquina, no por la memoria de
   nadie.** El intento anterior falló porque la única forma de saber si algo se
   había roto era abrir la app y mirar.
2. **Los movimientos son mecánicos.** El código cambia de sitio y nada más. Así
   cualquier diferencia de comportamiento es un bug detectable, y el diff es
   revisable. La limpieza de deuda va en su propia fase.
3. **Ni una fila de datos se copia.** Las mudanzas entre apps son cambios de
   estado de Django, no de esquema.
4. **Un commit por módulo, cada uno desplegable y reversible por separado.**

## 5. Decisiones tomadas

| Decisión | Elección |
|---|---|
| Alcance | Paquetes primero (fase 1), apps reales después (fase 2) |
| Red de seguridad | pytest + guidelines de testing del usuario + CI en GitHub Actions |
| Deuda técnica | Fase propia y **al final**, después de la fase 2 |
| Ubicación de `Category` | Fichero propio desde la fase 1 |
| Vistas/URLs en la fase 2 | **No se mueven**: se quedan en `videos` |
| Vistas/URLs a largo plazo | Se mudan en una **fase 4** propia, tras la fase 3 |

## 6. Fase 0 — Red de seguridad

### 6.1 pytest

`requirements-dev.txt` con `pytest` y `pytest-django`, instalado en la imagen de
desarrollo. `pytest.ini` con `DJANGO_SETTINGS_MODULE = config.settings`.

Los tests actuales son `django.test.TestCase` y pytest-django los ejecuta sin
reescribir ninguno. Comando de referencia (adaptado de las guidelines del
usuario al compose y al nombre de servicio de este proyecto):

```bash
docker compose -f docker-compose.dev.yml run --rm web python -m pytest --create-db
```

`--create-db` es obligatorio: fuerza recrear la BD de test aplicando todas las
migraciones. Sin él la BD de test queda desactualizada y los fallos son
engañosos (columnas ausentes).

### 6.2 Reorganización de tests

Estructura `app/tests/` según las guidelines del usuario, con `__init__.py`:

| Origen | Destino |
|---|---|
| `videosvoley/videos/tests.py` (473 líneas, RFEVB) | `videosvoley/videos/tests/test_scraping.py` |
| `videosvoley/users/tests.py` | `videosvoley/users/tests/test_*.py` |
| `tests/test_tenant.py` (raíz) | `videosvoley/core/tests/test_tenant.py` |
| `tests/test_sentry.py` (raíz) | `videosvoley/core/tests/test_sentry.py` |

### 6.3 Tests nuevos

Aplicando las reglas de valor del usuario (un test existe si protege una regla
de negocio propia, no si sube cobertura), se escriben en `test_models.py`:

- **`Image.save()`** — el de mayor valor: deduce `year` del partido o parsea la
  temporada (`"2024-25"` → 2024), fuerza `image_type='match'`, y en post-save
  copia las categorías de la liga y de ambos equipos. Transformación no trivial
  con efectos persistentes.
- **`MatchManager`** — el manager por defecto excluye `withdrawn` y
  `all_objects` no. Si alguien altera el orden de los managers al mover el
  modelo, `Match.objects` empieza a devolver partidos retirados en toda la app.
- **`LeagueManager`** (`visible_in_app`, `reference_leagues`,
  `historical_leagues`, `external_leagues`) — combinaciones de tres flags.
- **`League.get_combined_matches()` / `get_all_phases()`** y
  **`Team.get_all_variants()` / `root_team`** — recursión padre-hijo.
- **`Match.clean()`** — validación propia, incluida la autocorrección de
  `is_friendly` cuando hay `federation_id`.
- **`Video.get_embed_url()`** — parsing de tres formatos de URL de YouTube,
  incluido livestream.

Excluidos explícitamente por las mismas reglas: properties triviales
(`full_name`, `is_finished`, `result_display`), configuración de `ModelAdmin`,
y aserciones de `status_code` sin comprobación de efecto.

### 6.4 Guarda anti-migración fantasma

`makemigrations --check --dry-run` debe salir limpio. Mover clases entre ficheros
de la misma app no puede alterar el esquema; si propone una migración, algo se
cambió sin querer. Única excepción prevista y documentada en 7.3.

### 6.5 CI

GitHub Actions con servicio postgres que ejecute `pytest --create-db`,
`makemigrations --check --dry-run` y `manage.py check`.

### 6.6 `CLAUDE.md`

Crear el fichero (hoy `WARP.md` es un symlink roto) con las guidelines de
testing adaptadas y el comando docker del proyecto.

## 7. Fase 1 — Paquetes dentro de `videos`

**Por qué es de riesgo cero**: Django identifica un modelo por su `app_label` y
su `db_table`, no por el fichero en que vive. Mover clases entre ficheros de la
misma app no toca el esquema.

### 7.1 Estructura de `models/`

```
videosvoley/videos/models/
├── __init__.py        # reexporta TODO
├── category.py        # Category                                    ~15
├── teams.py           # Club, Team                                  ~125
├── content.py         # Video, Comment, Image, image_upload_path    ~300
├── competitions.py    # League + LeagueManager, Match + MatchManager
│                      #   + MatchAllManager, Standing,
│                      #   ScrapingEndpoint                          ~380
├── rosters.py         # Person, PlayerRole, StaffRole,
│                      #   person_photo_upload_path                  ~320
└── legacy.py          # Player, Staff y sus upload paths            ~225
```

**`__init__.py` reexporta todos los nombres públicos.** Es la pieza que hace
segura la fase: los 84 imports existentes siguen funcionando sin tocar ninguno,
y las 4 migraciones antiguas que referencian
`videosvoley.videos.models.<función>` siguen resolviendo (ver 7.3).

**`legacy.py` aísla `Player` y `Staff` a propósito**: en la fase 3 su retirada
es borrar un fichero, no operar dentro de otro.

Dependencias, en un solo sentido y sin ciclos:

```
category  ←  teams  ←  competitions
category  ←  content
teams     ←  rosters
teams     ←  legacy
```

Las FKs hacia `Match` ya usan referencias por string (`FK('Match')`), que Django
resuelve en diferido.

### 7.2 `Category` en fichero propio

`Category` la usan `Video`, `Image`, `Team` y `League`: es vocabulario compartido
por los cuatro dominios. Tiene fichero propio en lugar de vivir dentro de
`content.py` porque es el nudo de la fase 2: cuando `content`, `teams` y
`competitions` sean apps separadas, las tres la necesitarán, y si vive dentro de
una de ellas las otras dos acabarían dependiendo de una app ajena. Darle sitio
propio ahora prepara su mudanza a `core` sin volver a moverla.

### 7.3 Migraciones esperadas: exactamente una, y vacía

Cuatro migraciones antiguas referencian funciones por ruta absoluta:

| Migración | Función |
|---|---|
| `0012_image.py` | `image_upload_path` |
| `0015_image_original_format_...` | `image_upload_path` |
| `0019_player_staff.py` | `player_photo_upload_path`, `staff_photo_upload_path` |
| `0020_add_person_role_models.py` | `person_photo_upload_path` |

Como `models` pasa a ser paquete y su `__init__.py` reexporta esas funciones,
`videosvoley.videos.models.image_upload_path` **sigue resolviendo** y las
migraciones antiguas se reproducen sin cambios. Esto es crítico porque
`pytest --create-db` reproduce las 35 migraciones en cada ejecución.

Sin embargo, Django serializa `upload_to` como `módulo.función`. Al mover
`image_upload_path` a `models/content.py` su `__module__` cambia, así que
`makemigrations` **propondrá un `AlterField` sobre esos 4 campos**. No es
evitable sin trucos, ni hace falta evitarlo: `upload_to` es lógica de Python, no
una columna.

**Criterio de aceptación**: tras partir `models.py` se espera **una** migración
`AlterField` sobre esos 4 campos, y `sqlmigrate` sobre ella debe salir **sin una
sola línea de DDL**. Cualquier otra migración propuesta es un error.

### 7.4 Los demás monolitos

Mismo patrón de paquete + reexport, un commit por módulo:

| Orden | Fichero | Líneas | Qué lo mantiene funcionando |
|---|---|---|---|
| 1 | `models.py` | 1433 | reexport → 84 imports intactos |
| 2 | `admin.py` | 1398 | Django importa `videos.admin`; el `__init__` importa los submódulos y los `@register` se ejecutan igual |
| 3 | `forms.py` | 1104 | reexport |
| 4 | `views.py` | 2797 | reexport → `urls.py` no cambia |
| 5 | `tasks.py` | 1928 | los `name=` explícitos protegen las filas de `PeriodicTask`; el `from ... import *` de `config/celery.py:20` sigue funcionando |
| 6 | `scraping.py` | 2518 | reexport; ya tiene cobertura vía los tests RFEVB |

El orden va de menos a más acoplado. `admin` antes que `views` porque un fallo
en admin es inmediato y solo afecta a administradores. `tasks` y `scraping` al
final porque un fallo ahí corrompe datos scrapeados en silencio.

### 7.5 Verificación tras cada commit

```bash
docker compose -f docker-compose.dev.yml run --rm web python manage.py check
docker compose -f docker-compose.dev.yml run --rm web python manage.py makemigrations --check --dry-run
docker compose -f docker-compose.dev.yml run --rm web python -m pytest --create-db
git diff --stat   # solo movimiento: líneas fuera ≈ líneas dentro
```

## 8. Fase 2 — Apps reales

### 8.1 Mecanismo

**Paso A — Clavar el nombre de tabla** mientras el modelo sigue en `videos`:

```python
class League(models.Model):
    class Meta:
        db_table = 'videos_league'   # el nombre que Django ya daba por defecto
```

Genera un `AlterModelTable` de `videos_league` a `videos_league`: cero SQL. A
partir de ahí el nombre de tabla es explícito y deja de derivarse del
`app_label`.

**Paso B — Mudanza solo de estado**, con dos migraciones espejo:

```python
# competitions/migrations/0001_initial.py
migrations.SeparateDatabaseAndState(
    state_operations=[migrations.CreateModel(name='League', ...)],
    database_operations=[],
)

# videos/migrations/00XX_move_competitions.py
migrations.SeparateDatabaseAndState(
    state_operations=[migrations.DeleteModel('League'), ...],
    database_operations=[],
)
```

Con `database_operations=[]`, `CreateModel` y `DeleteModel` son papeleo interno
de Django: la tabla `videos_league` no se crea, ni se borra, ni se toca.
`sqlmigrate` sobre ambas debe salir vacío. Ordenación mediante `run_before` en la
migración de la app nueva.

Rollback: `migrate videos <anterior>` y revertir el código.

### 8.2 Trampas conocidas

**`django_content_type`.** Sus filas van indexadas por `(app_label, model)`. Al
mover `League`, la fila `('videos','league')` queda huérfana y `post_migrate`
crea `('competitions','league')`. Como `auth_permission` cuelga por FK de la
fila vieja, **los permisos asignados a grupos y usuarios apuntarían a un
contenttype muerto**. Requiere una migración de datos que haga
`UPDATE django_content_type SET app_label='competitions'` **antes** de que
`post_migrate` cree la duplicada. `django_admin_log` se arrastra solo al
actualizar en sitio. No hay `GenericForeignKey` en código propio, lo que acota
el impacto a permisos y log de admin.

**FKs desde otras apps.** `Image.match`, `Standing.team`, etc. necesitan
`AlterField` también dentro de `SeparateDatabaseAndState`: la columna y la
constraint no cambian (misma tabla), solo cambia a qué modelo cree Django que
apuntan.

**La app `videos` no se puede borrar.** Su historial vive en `django_migrations`
y las migraciones de las apps nuevas dependen de él. Queda como cascarón con sus
migraciones y, por decisión de 8.3, con vistas, URLs y templates.

### 8.3 La fase 2 mueve datos, no vistas

`views.py`, `urls.py` y los templates **se quedan en `videos`**. El namespace
`videos:` no cambia y las 219 referencias (171 en templates + 48 en Python)
siguen válidas.

El motivo es que mezclarlo juntaría el riesgo verificable (migraciones
state-only, comprobables con `sqlmigrate`) con el que no lo es: un
`{% url 'videos:match_detail' %}` roto no lo detecta `manage.py check`, explota
en runtime. Separadas, la fase 2 es auditable de principio a fin. La mudanza de
las vistas no se descarta: se aplaza a la fase 4 (sección 10), donde va con su
propia red de seguridad.

### 8.4 Orden de extracción

Una app por despliegue, de menor a mayor radio de explosión:

| # | App | Modelos | Razón del puesto |
|---|---|---|---|
| 1 | `rosters` | Person, PlayerRole, StaffRole, (Player, Staff) | **Piloto**: ninguna app depende de ella |
| 2 | `content` | Video, Comment, Image | Nadie depende de ella |
| 3 | `teams` | Club, Team | De ella dependen competitions y rosters |
| 4 | `competitions` | League, Match, Standing, ScrapingEndpoint | El nudo, con el mecanismo ya rodado 3 veces |
| 5 | `core` | Category | Al sitio del que todas pueden depender |

### 8.5 Punto de parada

**La fase 2 es opcional.** Si tras el piloto `rosters` la fase 1 ya resolvió el
problema percibido, parar ahí es un resultado legítimo y no deja el proyecto en
estado inconsistente: `videos` con paquetes internos es una estructura estable y
completa por sí misma.

## 9. Fase 3 — Retirada de deuda

Va al final, después de la fase 2. La razón es que **no es borrado de código
muerto sino reconciliación de datos con solape parcial**, y su duración depende
de decisiones humanas caso por caso. Bloquear el refactor con esa incógnita
sería un mal intercambio; el coste de retrasarla es que el piloto de `rosters`
mueve 5 modelos en lugar de 3, es decir unos minutos en un commit mecánico.

### 9.1 `Player` y `Staff`

Datos medidos: 21 `Player` de los cuales **18 ya existen como `Person`** (cruce
por nombre y apellidos) y 3 no; 3 `Staff`.

1. Migración de datos que cree `Person` para los 3 jugadores sin equivalente, y
   los `Staff` que falten, deduplicando por
   `(first_name, last_name, birth_date)` — la `UniqueConstraint`
   `unique_person_identity` que `Person` ya declara.
2. Verificar que los 18 con equivalente tienen `PlayerRole` en el equipo
   correcto; crear los que falten.
3. Revisión humana de los casos ambiguos antes de continuar.
4. Quitar los inlines de `admin.py:297-304`.
5. Adaptar `management/commands/merge_duplicate_teams.py`, que hoy opera sobre
   `Player` y `Staff` (líneas 34, 221-222, 236-238).
6. `DeleteModel` y borrar `legacy.py`.

### 9.2 `League.category`

Datos medidos: 13 de 91 ligas conservan `category`, pero solo **1** carece de
`categories`, y en **0** el valor viejo queda fuera del M2M.

1. Resolver esa única liga volcando su `category` a `categories`.
2. Verificar que no queda uso de `League.category` en código ni templates.
3. `RemoveField`.

### 9.3 Residuo

Eliminar `videosvoley/core/tasks/`, paquete vacío sin uso.

## 10. Fase 4 — Mudanza de vistas, URLs y templates

**Motivación**: coherencia interna. Que `competitions` tenga los modelos y
`videos` las vistas es defendible operativamente pero incoherente en un
diagrama, y obliga a explicárselo a quien llegue nuevo al proyecto.

**Precondición**: la fase 2 completa. Si se ejerció el punto de parada de 8.5,
esta fase no aplica.

### 10.1 Dos pasos, porque solo uno es peligroso

Mover el código de las vistas y renombrar el namespace de URLs son cosas
separables, y solo la segunda rompe en runtime. Separarlas es lo que hace
asumible esta fase.

**Paso 4a — Mover el código.** Los módulos de `views/` (ya repartidos por la
fase 1) se trasladan a `competitions/views.py`, `content/views.py`, etc.
**`videosvoley/videos/urls.py` se queda donde está** e importa desde las apps
nuevas. El namespace `videos:` no cambia, las 219 referencias siguen intactas y
los templates no se tocan. Es un movimiento mecánico, verificable igual que la
fase 1.

**Paso 4b — Mover los URLconf y renombrar el namespace.** Cada app recibe su
`urls.py` con su `app_name`, `config/urls.py` los incluye, y las referencias
pasan de `videos:x` a `<app>:x`. Aquí sí hay riesgo de runtime, y por eso lleva
red propia.

### 10.2 La red que hace seguro el paso 4b

Un test que barre **estáticamente** los templates: extrae cada nombre de
`{% url 'x' %}` de `videosvoley/templates/**/*.html` y comprueba que `reverse()`
lo resuelve. Cubre las 171 referencias de una vez, es exhaustivo por
construcción y no depende de que nadie se acuerde de abrir cada página. Un
barrido equivalente cubre los 48 `reverse()` y `redirect()` con literal de
cadena en Python.

Este test se escribe **antes** de tocar nada y se ve pasar en verde con los
nombres antiguos. Es la diferencia entre renombrar a ciegas y renombrar con
evidencia.

### 10.3 Templates

Los 25 ficheros de `videosvoley/templates/videos/` se reparten a
`<app>/templates/<app>/`, que el loader `APP_DIRS` localiza sin configuración
adicional. Afecta a las 33 llamadas `render(request, 'videos/...')`, que se
actualizan en el mismo commit que su template.

### 10.4 Orden

Una app por commit y en el mismo orden que la fase 2: `rosters`, `content`,
`teams`, `competitions`. Cada app completa 4a y 4b antes de pasar a la
siguiente, de modo que convivan temporalmente namespaces viejos y nuevos y
cualquier problema quede acotado a una app.

## 11. Riesgos

| Riesgo | Fase | Mitigación |
|---|---|---|
| Migración fantasma al mover modelos | 1 | `makemigrations --check` en CI; única excepción documentada en 7.3 |
| Migraciones antiguas dejan de resolver con `--create-db` | 1 | Reexport en `models/__init__.py`; cubierto por `pytest --create-db` |
| Tareas Celery desregistradas | 1 | Las 16 llevan `name=` explícito, independiente de la ruta del módulo |
| Permisos huérfanos por contenttype | 2 | Migración de datos que actualiza `app_label` antes de `post_migrate` |
| URLs rotas en runtime | 2 | Vistas, URLs y templates no se mueven (8.3) |
| Pérdida de datos en la mudanza de apps | 2 | `database_operations=[]`; `sqlmigrate` debe salir vacío antes de desplegar |
| Reconciliación Player/Person ambigua | 3 | Revisión humana; solape ya medido (18/21) |
| Referencia `{% url %}` o `reverse()` olvidada al renombrar namespaces | 4 | Test de barrido estático de los 219 nombres, escrito y en verde antes de renombrar (10.2) |

## 12. Criterios de aceptación

**Fase 0**: `pytest --create-db` verde en local y en CI; tests reorganizados a
`app/tests/`; los 7 tests de 6.3 escritos y pasando.

**Fase 1**: ningún fichero de `videos` supera ~400 líneas, salvo justificación
explícita en el commit (una función larga e indivisible de `scraping.py`, por
ejemplo); los 84 imports
originales siguen funcionando sin modificarse; `makemigrations --check` limpio
salvo el `AlterField` de 7.3, cuyo `sqlmigrate` sale vacío; `pytest --create-db`
verde tras cada commit.

**Fase 2**: `sqlmigrate` vacío para toda migración de mudanza; recuento de filas
idéntico antes y después en cada tabla movida; permisos de grupos y usuarios
intactos tras el despliegue; `videos:` sigue resolviendo las 219 referencias.

**Fase 3**: cero filas en `Player` y `Staff` antes del `DeleteModel`; ninguna
`Person` duplicada; `League.category` eliminado sin pérdida de categorías.

**Fase 4**: el test de barrido de 10.2 en verde antes y después de cada commit;
`videosvoley/templates/videos/` vacío al terminar; ninguna referencia a
`videos:` superviviente en templates ni en Python.

## 13. Fuera de alcance

- Refactor interno de la lógica de `scraping.py` o `views.py`: solo se reparten
  en módulos, su contenido no se reescribe.
- Cualquier cambio de comportamiento observable. Las fases 1, 2 y 4 son
  mecánicas: reparten código y renombran rutas, sin alterar qué hace la app.
