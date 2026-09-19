# Refactor de la app `videos` — Fases 0 y 1

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dotar al proyecto de una red de tests ejecutable y repartir los seis
ficheros monolíticos de la app `videos` en paquetes, sin alterar una sola línea
de comportamiento ni tocar el esquema de la base de datos.

**Architecture:** Fase 0 instala pytest, reorganiza los tests a la estructura
`app/tests/` y escribe los tests de las reglas de negocio que el refactor podría
romper en silencio. Fase 1 convierte `models.py`, `admin.py`, `forms.py`,
`views.py`, `tasks.py` y `scraping.py` en paquetes cuyo `__init__.py` reexporta
todos los nombres públicos, de modo que ninguno de los 84 imports existentes ni
ninguna de las 35 migraciones necesite modificarse. Django identifica un modelo
por su `app_label` y su `db_table`, no por el fichero en que vive: por eso esta
fase no genera migraciones de esquema.

**Tech Stack:** Django 6.0.8, PostgreSQL 18, Celery 5.6, pytest + pytest-django,
Docker Compose, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-09-16-refactor-models-design.md`

## Global Constraints

- **Django está fijado en 6.0.8** hasta que `django-celery-beat` soporte 6.1+.
  No subir la versión en este plan.
- **Todo comando Django se ejecuta dentro de Docker.** Formato exacto:
  `docker compose -f docker-compose.dev.yml run --rm web <comando>`.
  El `entrypoint.sh` deja pasar cualquier comando que no sea `runserver` ni
  `gunicorn`, así que `python -m pytest` funciona sin `--entrypoint`.
- **⚠️ Este plan NO se ejecuta en el servidor de producción.** Allí la aplicación
  corre como proyecto compose `videosvoley`, y `docker-compose.dev.yml` resuelve
  al mismo nombre de proyecto (lo toma del directorio). Compose daría por
  satisfechos los servicios `db` y `redis` con los contenedores de producción, de
  modo que `pytest --create-db` crearía la base de datos de test dentro del
  Postgres de producción, y `build web` podría sustituir la imagen que usa el
  contenedor `web` de producción al reiniciarse. Ejecutar todo en el entorno de
  desarrollo. Si alguna vez hiciera falta aquí, aislarlo con
  `docker compose -p videosvoley_dev -f docker-compose.dev.yml ...`.
- **`--create-db` es obligatorio en toda ejecución de pytest.** Sin él la BD de
  test queda desactualizada y fallan columnas.
- **Las fases 0 y 1 no cambian comportamiento observable.** Si un test existente
  empieza a fallar, la causa es el refactor, no el test: revertir y revisar.
- **Los tests se escriben según las reglas de valor del proyecto:** un test
  existe solo si protege una regla de negocio propia. Nada de `status_code`
  suelto, HTML decorativo, properties triviales ni configuración de `ModelAdmin`.
- **Nomenclatura de tests en castellano**, coherente con el resto del proyecto.
- **Un commit por tarea.** Mensajes en castellano siguiendo el estilo del repo
  (`feat:`, `fix:`, `refactor:`, `test:`, `chore:`, `docs:`).
- La rama de trabajo es `refactor/models-split`.

---

# FASE 0 — Red de seguridad

### Task 1: Infraestructura de pytest

**Files:**
- Create: `requirements-dev.txt`
- Create: `pytest.ini`
- Modify: `Dockerfile:27-34`

**Interfaces:**
- Consumes: nada.
- Produces: el comando
  `docker compose -f docker-compose.dev.yml run --rm web python -m pytest --create-db`,
  del que dependen todas las tareas siguientes.

- [x] **Step 1: Crear `requirements-dev.txt`**

```
# Dependencias de desarrollo y test.
# Incluye las de producción para que una sola instalación cubra ambos casos.
-r requirements.txt

pytest==9.1.1
pytest-django==4.14.0
```

Versiones comprobadas contra PyPI el 2026-09-17. `pytest-django 4.14.0` declara
soporte explícito de Django 6.0 y Python 3.13, y requiere `pytest>=7.0.0`.

- [x] **Step 2: Instalar las dependencias de desarrollo en la imagen**

En `Dockerfile`, sustituir el bloque que copia e instala `requirements.txt`:

```dockerfile
# Instalar dependencias Python
COPY requirements.txt requirements-dev.txt ./

# Actualizar pip y herramientas de compilación
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --upgrade pip setuptools wheel

# requirements-dev.txt arranca con `-r requirements.txt`, así que esta única
# instalación cubre producción y desarrollo. El sobrecoste en la imagen de
# producción son dos paquetes de test.
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements-dev.txt
```

La imagen de producción se construye con el mismo Dockerfile; el sobrecoste son
dos paquetes de test, asumible frente a mantener dos Dockerfiles divergentes.

- [x] **Step 3: Crear `pytest.ini`**

```ini
[pytest]
DJANGO_SETTINGS_MODULE = config.settings
python_files = test_*.py
# `tests` (raíz) desaparece en la Task 2 del plan de refactor, que reubica sus
# tests en videosvoley/core/tests/. Al hacerlo, quitar `tests` de esta línea.
testpaths = videosvoley tests
addopts = --strict-markers
```

`testpaths` incluye de momento el directorio `tests/` de la raíz. Si se pusiera
solo `videosvoley`, los tests de `test_tenant.py` y `test_sentry.py` dejarían de
ejecutarse en silencio hasta que la Task 2 los reubicase. La Task 2 elimina
`tests` de esta línea al vaciar el directorio.

> **Estado:** los pasos 1-3 se completaron el 2026-09-17 desde el servidor de
> producción (solo edición de ficheros, sin ejecutar nada). Los pasos 4 y 5
> quedan **pendientes** y deben ejecutarse en el entorno de desarrollo, por el
> motivo explicado en las restricciones globales.

- [x] **Step 4: Reconstruir la imagen**

Run: `docker compose -f docker-compose.dev.yml build web`
Expected: build correcto, con `pytest` y `pytest-django` instalados.

- [x] **Step 5: Ejecutar la suite existente**

Run: `docker compose -f docker-compose.dev.yml run --rm web python -m pytest --create-db -v`
Expected: PASS. Los tests actuales son `django.test.TestCase` y pytest-django
los recoge sin modificarlos. Recoge `videosvoley/videos/tests.py` y
`videosvoley/users/tests.py`.

Si falla la creación de la BD de test por permisos, comprobar que el usuario
`volleyuser` del contenedor `db` puede crear bases de datos (lo es por defecto
al ser el `POSTGRES_USER` de la imagen oficial).

- [ ] **Step 6: Commit**

```bash
git add requirements-dev.txt pytest.ini Dockerfile
git commit -m "chore(tests): instalar pytest y pytest-django"
```

---

### Task 2: Reorganizar los tests a la estructura `app/tests/`

**Files:**
- Create: `videosvoley/videos/tests/__init__.py`
- Create: `videosvoley/users/tests/__init__.py`
- Create: `videosvoley/core/tests/__init__.py`
- Move: `videosvoley/videos/tests.py` → `videosvoley/videos/tests/test_scraping.py`
- Move: `videosvoley/users/tests.py` → `videosvoley/users/tests/test_admin.py`
- Move: `tests/test_tenant.py` → repartido en 5 ficheros de `videosvoley/core/tests/`
- Move: `tests/test_sentry.py` → `videosvoley/core/tests/test_sentry.py`
- Delete: `tests/` (directorio raíz)

**Interfaces:**
- Consumes: el comando pytest de la Task 1.
- Produces: los directorios `videosvoley/{videos,users,core}/tests/`, donde las
  Tasks 3-6 añaden `test_models.py`.

- [x] **Step 1: Crear los paquetes de tests**

```bash
mkdir -p videosvoley/videos/tests videosvoley/users/tests videosvoley/core/tests
touch videosvoley/videos/tests/__init__.py \
      videosvoley/users/tests/__init__.py \
      videosvoley/core/tests/__init__.py
```

- [x] **Step 2: Mover los ficheros de una sola responsabilidad**

```bash
git mv videosvoley/videos/tests.py videosvoley/videos/tests/test_scraping.py
git mv videosvoley/users/tests.py videosvoley/users/tests/test_admin.py
git mv tests/test_sentry.py videosvoley/core/tests/test_sentry.py
```

`videos/tests.py` contiene `RFEVBPhaseParserTests`, `RFEVBTeamsParserTests`,
`ScrapeRFEVBFaseCommandTests` y `ScrapeRFEVBCompetitionTaskTests`: todo es
scraping. `users/tests.py` contiene `AdminEmailUtilsTests` y
`UserAdminEmailActionTests`: el punto de entrada de ambos es la acción de admin,
de ahí `test_admin.py`.

- [x] **Step 3: Repartir `tests/test_tenant.py` por responsabilidad**

Sus 7 clases van a 5 ficheros de `videosvoley/core/tests/`. Mover cada clase con
sus imports, sin modificar su cuerpo:

| Clase | Destino |
|---|---|
| `OrganizationModelTest`, `MembershipModelTest` | `test_models.py` |
| `TenantMiddlewareTest` | `test_middleware.py` |
| `LandingViewTest` | `test_views.py` |
| `GetClubTeamFilterTest`, `ClubTeamNamesTest` | `test_templatetags.py` |
| `TenantUtilsTest` | `test_utils.py` |

Después: `git rm tests/test_tenant.py && rmdir tests` (el `__init__.py` de la
raíz también se elimina).

- [x] **Step 4: Verificar que no se ha perdido ningún test**

Run: `docker compose -f docker-compose.dev.yml run --rm web python -m pytest --create-db -v`
Expected: PASS, y el recuento total de tests debe ser **idéntico** al de la
Task 1 Step 5. Anotar ambos números y compararlos: si no coinciden, un test se
ha quedado por el camino.

- [x] **Step 5: Commit**

```bash
git add -A
git commit -m "test: reorganizar tests a la estructura app/tests/"
```

---

### Task 3: Tests de `Image.save()`

**Files:**
- Create: `videosvoley/videos/tests/test_models.py`

**Interfaces:**
- Consumes: `videosvoley/videos/tests/` de la Task 2.
- Produces: `TINY_GIF` y el patrón `setUpTestData` que reutilizan las Tasks 4-6
  en este mismo fichero.

`Image.save()` es el método de mayor riesgo del refactor: deduce `year`, fuerza
`image_type` y, después de guardar, hereda categorías de la liga y de ambos
equipos. Nada de eso es evidente leyendo el modelo.

- [ ] **Step 1: Escribir el test que falla**

Crear `videosvoley/videos/tests/test_models.py`:

```python
from datetime import datetime, timezone as dt_timezone

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.utils import timezone

from videosvoley.videos.models import Category, Image, League, Match, Team

User = get_user_model()

# GIF 1x1 real: evita depender de cómo trate Pillow unos bytes arbitrarios.
TINY_GIF = (
    b'GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!'
    b'\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00'
    b'\x00\x02\x02D\x01\x00;'
)


class ImageSaveTests(TestCase):
    """Protege la lógica de Image.save(), invisible desde fuera del modelo."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='paula', password='x')
        cls.cat_liga = Category.objects.create(name='Cadete Femenino')
        cls.cat_local = Category.objects.create(name='Senior Femenino')
        cls.cat_visitante = Category.objects.create(name='Juvenil Femenino')
        cls.league = League.objects.create(
            name='Liga Balear', federation_id='LIG-1', season='2024-25',
        )
        cls.league.categories.add(cls.cat_liga)
        cls.local = Team.objects.create(
            name='Sant Josep', federation_id='T-1', category=cls.cat_local,
        )
        cls.visitante = Team.objects.create(
            name='Manacor', federation_id='T-2', category=cls.cat_visitante,
        )
        cls.match = Match.objects.create(
            league=cls.league,
            home_team=cls.local,
            away_team=cls.visitante,
            match_date=datetime(2024, 11, 3, 12, 0, tzinfo=dt_timezone.utc),
            federation_id='M-1',
        )

    def _crear_imagen(self, **kwargs):
        kwargs.setdefault('title', 'Saque de Paula')
        kwargs.setdefault('uploaded_by', self.user)
        kwargs.setdefault(
            'image',
            SimpleUploadedFile('punto.jpg', TINY_GIF, content_type='image/jpeg'),
        )
        return Image.objects.create(**kwargs)

    def test_year_se_toma_del_ano_del_partido(self):
        imagen = self._crear_imagen(match=self.match)
        self.assertEqual(imagen.year, 2024)

    def test_year_sin_partido_usa_el_ano_actual(self):
        imagen = self._crear_imagen()
        self.assertEqual(imagen.year, timezone.now().year)

    def test_image_type_other_pasa_a_match_al_vincular_partido(self):
        imagen = self._crear_imagen(match=self.match)
        self.assertEqual(imagen.image_type, 'match')

    def test_image_type_explicito_no_se_pisa(self):
        imagen = self._crear_imagen(match=self.match, image_type='celebration')
        self.assertEqual(imagen.image_type, 'celebration')

    def test_hereda_categorias_de_la_liga_y_de_ambos_equipos(self):
        imagen = self._crear_imagen(match=self.match)
        self.assertEqual(
            set(imagen.categories.values_list('name', flat=True)),
            {'Cadete Femenino', 'Senior Femenino', 'Juvenil Femenino'},
        )

    def test_imagen_sin_partido_no_hereda_categorias(self):
        imagen = self._crear_imagen()
        self.assertEqual(imagen.categories.count(), 0)
```

- [ ] **Step 2: Ejecutar y verificar que pasa**

Run: `docker compose -f docker-compose.dev.yml run --rm web python -m pytest videosvoley/videos/tests/test_models.py -v --create-db`
Expected: PASS, 6 tests.

Estos tests **documentan comportamiento ya existente**, así que pasan a la
primera. No es TDD: es caracterización previa a un refactor, y su valor está en
fallar más adelante si la fase 1 altera algo. Si alguno falla ahora, el modelo
no hace lo que el código aparenta y hay que investigarlo antes de seguir.

- [ ] **Step 3: Commit**

```bash
git add videosvoley/videos/tests/test_models.py
git commit -m "test(videos): caracterizar la lógica de Image.save()"
```

---

### Task 4: Tests de los managers de `Match` y `League`

**Files:**
- Modify: `videosvoley/videos/tests/test_models.py` (añadir al final)

**Interfaces:**
- Consumes: los imports ya presentes en `test_models.py` de la Task 3.
- Produces: nada que consuman tareas posteriores.

`Match.objects` excluye los partidos `withdrawn` y `Match.all_objects` no. Es
una regla invisible: si el refactor altera el orden de declaración de los
managers, el manager por defecto de Django pasa a ser otro y toda la aplicación
empieza a mostrar partidos retirados sin que nada falle.

- [ ] **Step 1: Escribir los tests**

Añadir a `videosvoley/videos/tests/test_models.py`:

```python
class MatchManagerTests(TestCase):
    """El manager por defecto oculta los partidos retirados. Regla no evidente."""

    @classmethod
    def setUpTestData(cls):
        cls.league = League.objects.create(
            name='Liga', federation_id='LIG-M', season='2024-25',
        )
        cls.a = Team.objects.create(name='A', federation_id='T-A')
        cls.b = Team.objects.create(name='B', federation_id='T-B')
        cls.jugado = Match.objects.create(
            league=cls.league, home_team=cls.a, away_team=cls.b,
            match_date=datetime(2024, 11, 3, 12, 0, tzinfo=dt_timezone.utc),
            status='finished', federation_id='M-OK',
        )
        cls.retirado = Match.objects.create(
            league=cls.league, home_team=cls.a, away_team=cls.b,
            match_date=datetime(2024, 11, 10, 12, 0, tzinfo=dt_timezone.utc),
            status='withdrawn', federation_id='M-W',
        )

    def test_manager_por_defecto_oculta_los_retirados(self):
        self.assertEqual(list(Match.objects.all()), [self.jugado])

    def test_all_objects_incluye_los_retirados(self):
        self.assertEqual(Match.all_objects.count(), 2)

    def test_el_manager_por_defecto_es_el_que_filtra(self):
        # Match._default_manager es el que usan el admin y las relaciones.
        self.assertEqual(Match._default_manager.count(), 1)


class LeagueManagerTests(TestCase):
    """visible_in_app() exige tres condiciones a la vez, no una."""

    @classmethod
    def setUpTestData(cls):
        cls.principal = League.objects.create(
            name='Principal', federation_id='L-M', season='2024-25',
            is_active=True, visibility_type='main', is_our_team_related=True,
        )
        cls.inactiva = League.objects.create(
            name='Inactiva', federation_id='L-I', season='2024-25',
            is_active=False, visibility_type='main', is_our_team_related=True,
        )
        cls.ajena = League.objects.create(
            name='Ajena', federation_id='L-E', season='2024-25',
            is_active=True, visibility_type='external', is_our_team_related=False,
        )
        cls.historica = League.objects.create(
            name='Historica', federation_id='L-H', season='2019-20',
            is_active=True, visibility_type='historical', is_historical=True,
        )

    def _nombres(self, queryset):
        return set(queryset.values_list('name', flat=True))

    def test_visible_in_app_solo_devuelve_la_que_cumple_las_tres_condiciones(self):
        self.assertEqual(self._nombres(League.objects.visible_in_app()), {'Principal'})

    def test_reference_leagues_agrupa_los_tres_tipos_no_principales(self):
        self.assertEqual(
            self._nombres(League.objects.reference_leagues()), {'Ajena', 'Historica'}
        )

    def test_historical_leagues_exige_el_flag_ademas_del_tipo(self):
        self.assertEqual(self._nombres(League.objects.historical_leagues()), {'Historica'})

    def test_external_leagues_exige_no_estar_relacionada_con_nuestro_equipo(self):
        self.assertEqual(self._nombres(League.objects.external_leagues()), {'Ajena'})
```

- [ ] **Step 2: Ejecutar**

Run: `docker compose -f docker-compose.dev.yml run --rm web python -m pytest videosvoley/videos/tests/test_models.py -v --create-db`
Expected: PASS, 13 tests acumulados.

- [ ] **Step 3: Commit**

```bash
git add videosvoley/videos/tests/test_models.py
git commit -m "test(videos): caracterizar los managers de Match y League"
```

---

### Task 5: Tests de la recursión de fases de liga y variantes de equipo

**Files:**
- Modify: `videosvoley/videos/tests/test_models.py` (añadir al final)

**Interfaces:**
- Consumes: los imports de la Task 3.
- Produces: nada que consuman tareas posteriores.

`League.get_all_phases()`, `get_combined_matches()`, `root_league`,
`Team.get_all_variants()` y `root_team` recorren cadenas padre-hijo. Son las
funciones más frágiles ante un movimiento de código porque su corrección depende
de que las clases se resuelvan entre sí.

- [ ] **Step 1: Escribir los tests**

Añadir a `videosvoley/videos/tests/test_models.py`:

```python
class LeaguePhaseTests(TestCase):
    """Fases de liga: la recursión sube al padre y agrega sus partidos."""

    @classmethod
    def setUpTestData(cls):
        cls.regular = League.objects.create(
            name='Liga Regular', federation_id='L-R', season='2024-25',
        )
        cls.oro = League.objects.create(
            name='Liga Regular', federation_id='L-ORO', season='2024-25',
            parent_league=cls.regular, phase_name='Liguilla Oro', phase_order=1,
        )
        cls.plata = League.objects.create(
            name='Liga Regular', federation_id='L-PLA', season='2024-25',
            parent_league=cls.regular, phase_name='Liguilla Plata', phase_order=2,
        )
        cls.a = Team.objects.create(name='A', federation_id='TP-A')
        cls.b = Team.objects.create(name='B', federation_id='TP-B')
        cls.partido_regular = Match.objects.create(
            league=cls.regular, home_team=cls.a, away_team=cls.b,
            match_date=datetime(2024, 10, 5, 12, 0, tzinfo=dt_timezone.utc),
            federation_id='MP-1',
        )
        cls.partido_oro = Match.objects.create(
            league=cls.oro, home_team=cls.a, away_team=cls.b,
            match_date=datetime(2025, 2, 8, 12, 0, tzinfo=dt_timezone.utc),
            federation_id='MP-2',
        )

    def test_is_phase_distingue_la_liga_raiz_de_sus_fases(self):
        self.assertFalse(self.regular.is_phase)
        self.assertTrue(self.oro.is_phase)

    def test_root_league_sube_hasta_la_raiz_desde_una_fase(self):
        self.assertEqual(self.oro.root_league, self.regular)

    def test_get_all_phases_devuelve_la_raiz_primero_y_luego_las_fases_ordenadas(self):
        self.assertEqual(
            self.regular.get_all_phases(), [self.regular, self.oro, self.plata]
        )

    def test_get_all_phases_desde_una_fase_devuelve_lo_mismo_que_desde_la_raiz(self):
        self.assertEqual(self.oro.get_all_phases(), self.regular.get_all_phases())

    def test_get_combined_matches_agrega_los_partidos_de_todas_las_fases(self):
        self.assertEqual(
            set(self.regular.get_combined_matches()),
            {self.partido_regular, self.partido_oro},
        )

    def test_get_combined_matches_desde_una_fase_agrega_igual(self):
        self.assertEqual(
            set(self.oro.get_combined_matches()),
            {self.partido_regular, self.partido_oro},
        )

    def test_display_name_prioriza_el_override_sobre_el_nombre_de_fase(self):
        self.oro.display_name_override = 'Fase de Oro 24/25'
        self.assertEqual(self.oro.display_name, 'Fase de Oro 24/25')

    def test_display_name_concatena_el_nombre_de_fase_si_no_hay_override(self):
        self.assertEqual(self.oro.display_name, 'Liga Regular - Liguilla Oro')


class TeamVariantTests(TestCase):
    """Variantes de equipo: misma recursión que las fases de liga."""

    @classmethod
    def setUpTestData(cls):
        cls.principal = Team.objects.create(name='Sant Josep', federation_id='TV-0')
        cls.groc = Team.objects.create(
            name='Sant Josep', federation_id='TV-1',
            parent_team=cls.principal, variant_type='color', variant_name='Groc',
        )
        cls.lila = Team.objects.create(
            name='Sant Josep', federation_id='TV-2',
            parent_team=cls.principal, variant_type='color', variant_name='Lila',
        )
        cls.retirado = Team.objects.create(
            name='Sant Josep', federation_id='TV-3',
            parent_team=cls.principal, variant_name='Blau', is_active=False,
        )

    def test_is_variant_distingue_el_equipo_principal_de_sus_variantes(self):
        self.assertFalse(self.principal.is_variant)
        self.assertTrue(self.groc.is_variant)

    def test_root_team_sube_hasta_el_equipo_principal(self):
        self.assertEqual(self.groc.root_team, self.principal)

    def test_get_all_variants_incluye_el_principal_y_excluye_las_inactivas(self):
        self.assertEqual(
            self.principal.get_all_variants(), [self.principal, self.groc, self.lila]
        )

    def test_get_all_variants_desde_una_variante_devuelve_lo_mismo(self):
        self.assertEqual(self.groc.get_all_variants(), self.principal.get_all_variants())

    def test_display_name_with_variant_anade_la_variante_entre_parentesis(self):
        self.assertEqual(self.groc.display_name_with_variant, 'Sant Josep (Groc)')

    def test_display_name_with_variant_no_anade_nada_al_principal(self):
        self.assertEqual(self.principal.display_name_with_variant, 'Sant Josep')
```

- [ ] **Step 2: Ejecutar**

Run: `docker compose -f docker-compose.dev.yml run --rm web python -m pytest videosvoley/videos/tests/test_models.py -v --create-db`
Expected: PASS, 27 tests acumulados.

Si `test_get_all_variants_incluye_el_principal_y_excluye_las_inactivas` falla por
el orden, comprobar que `get_all_variants()` ordena por `variant_name`: 'Groc'
precede a 'Lila' alfabéticamente.

- [ ] **Step 3: Commit**

```bash
git add videosvoley/videos/tests/test_models.py
git commit -m "test(videos): caracterizar fases de liga y variantes de equipo"
```

---

### Task 6: Tests de `Match.clean()` y `Video.get_embed_url()`

**Files:**
- Modify: `videosvoley/videos/tests/test_models.py` (añadir al final)

**Interfaces:**
- Consumes: los imports de la Task 3, más `ValidationError` y `Video`.
- Produces: nada que consuman tareas posteriores.

- [ ] **Step 1: Ampliar los imports del fichero**

En la cabecera de `videosvoley/videos/tests/test_models.py`, sustituir la línea
de import de modelos y añadir `ValidationError`:

```python
from django.core.exceptions import ValidationError

from videosvoley.videos.models import Category, Image, League, Match, Team, Video
```

- [ ] **Step 2: Escribir los tests**

Añadir al final de `videosvoley/videos/tests/test_models.py`:

```python
class MatchCleanTests(TestCase):
    """Validación propia de Match, que no cubre ningún validador de Django."""

    @classmethod
    def setUpTestData(cls):
        cls.league = League.objects.create(
            name='Liga', federation_id='L-C', season='2024-25',
        )
        cls.a = Team.objects.create(name='A', federation_id='TC-A')
        cls.b = Team.objects.create(name='B', federation_id='TC-B')

    def test_un_amistoso_no_puede_llevar_federation_id(self):
        partido = Match(
            is_friendly=True,
            federation_id='F-1',
            home_team_text='Equipo invitado',
            away_team_text='Sant Josep',
            match_date=datetime(2024, 12, 1, 12, 0, tzinfo=dt_timezone.utc),
        )
        with self.assertRaises(ValidationError):
            partido.clean()

    def test_un_partido_oficial_ya_guardado_exige_equipo_local(self):
        partido = Match.objects.create(
            league=self.league, home_team=self.a, away_team=self.b,
            match_date=datetime(2024, 12, 1, 12, 0, tzinfo=dt_timezone.utc),
            federation_id='MC-1',
        )
        partido.home_team = None
        with self.assertRaises(ValidationError):
            partido.clean()

    def test_un_partido_oficial_ya_guardado_exige_equipo_visitante(self):
        partido = Match.objects.create(
            league=self.league, home_team=self.a, away_team=self.b,
            match_date=datetime(2024, 12, 1, 12, 0, tzinfo=dt_timezone.utc),
            federation_id='MC-2',
        )
        partido.away_team = None
        with self.assertRaises(ValidationError):
            partido.clean()

    def test_un_partido_oficial_sin_guardar_no_exige_equipos(self):
        # La validación solo aplica si self.pk is not None: durante la creación
        # es el formulario quien valida.
        partido = Match(
            league=self.league,
            match_date=datetime(2024, 12, 1, 12, 0, tzinfo=dt_timezone.utc),
        )
        partido.clean()  # no debe lanzar

    def test_un_amistoso_con_equipos_en_texto_es_valido(self):
        partido = Match(
            is_friendly=True,
            home_team_text='Equipo invitado',
            away_team_text='Sant Josep',
            match_date=datetime(2024, 12, 1, 12, 0, tzinfo=dt_timezone.utc),
        )
        partido.clean()  # no debe lanzar


class VideoEmbedUrlTests(TestCase):
    """Parsing de tres formatos de URL de YouTube hacia el dominio nocookie."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='bert', password='x')

    def _video(self, url):
        return Video.objects.create(
            title='Partido', youtube_url=url, created_by=self.user
        )

    def _esperado(self, video_id):
        return (
            f'https://www.youtube-nocookie.com/embed/{video_id}'
            '?rel=0&modestbranding=1&fs=1&enablejsapi=0'
        )

    def test_url_watch_se_convierte_en_embed_nocookie(self):
        video = self._video('https://www.youtube.com/watch?v=dQw4w9WgXcQ')
        self.assertEqual(video.get_embed_url(), self._esperado('dQw4w9WgXcQ'))

    def test_url_watch_con_parametros_extra_ignora_la_cola(self):
        video = self._video('https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=42s')
        self.assertEqual(video.get_embed_url(), self._esperado('dQw4w9WgXcQ'))

    def test_url_corta_youtu_be(self):
        video = self._video('https://youtu.be/dQw4w9WgXcQ')
        self.assertEqual(video.get_embed_url(), self._esperado('dQw4w9WgXcQ'))

    def test_url_de_directo(self):
        video = self._video('https://www.youtube.com/live/AbCdEf12345')
        self.assertEqual(video.get_embed_url(), self._esperado('AbCdEf12345'))

    def test_url_no_reconocida_se_devuelve_intacta(self):
        video = self._video('https://vimeo.com/123456')
        self.assertEqual(video.get_embed_url(), 'https://vimeo.com/123456')

    def test_is_livestream_detecta_los_directos(self):
        self.assertTrue(self._video('https://www.youtube.com/live/AbC').is_livestream())
        self.assertFalse(
            self._video('https://www.youtube.com/watch?v=AbC').is_livestream()
        )

    def test_get_video_type_distingue_directo_de_video(self):
        self.assertEqual(
            self._video('https://www.youtube.com/live/AbC').get_video_type(),
            'livestream',
        )
        self.assertEqual(
            self._video('https://www.youtube.com/watch?v=AbC').get_video_type(),
            'video',
        )
```

- [ ] **Step 3: Ejecutar**

Run: `docker compose -f docker-compose.dev.yml run --rm web python -m pytest videosvoley/videos/tests/test_models.py -v --create-db`
Expected: PASS, 39 tests acumulados.

- [ ] **Step 4: Documentar la rama muerta detectada en `Match.clean()`**

`models.py:556-562` contiene:

```python
if self.is_friendly and self.federation_id:
    raise ValidationError('Los partidos amistosos no deben tener federation_id')

if self.federation_id and self.is_friendly:
    self.is_friendly = False  # Auto-corregir
```

El segundo bloque es **inalcanzable**: cualquier entrada que lo activaría ya ha
lanzado en el primero. La autocorrección nunca se ejecuta. Los tests documentan
el comportamiento real (lanza), no el pretendido.

**No arreglarlo en este plan**: las fases 0 y 1 no cambian comportamiento.
Abrir una issue describiendo el hallazgo y enlazarla desde el código con un
comentario `# NOTA: rama inalcanzable, ver issue #NN` no es necesario aquí;
basta con dejar constancia en la issue.

- [ ] **Step 5: Commit**

```bash
git add videosvoley/videos/tests/test_models.py
git commit -m "test(videos): caracterizar Match.clean() y Video.get_embed_url()"
```

---

### Task 7: CI en GitHub Actions

**Files:**
- Create: `.github/workflows/tests.yml`

**Interfaces:**
- Consumes: `requirements-dev.txt` y `pytest.ini` de la Task 1.
- Produces: la verificación automática de la que dependen todas las tareas de la
  fase 1, en particular la guarda `makemigrations --check`.

- [ ] **Step 1: Crear el workflow**

```yaml
name: Tests

on:
  push:
    branches: [main, 'refactor/**', 'feature/**']
  pull_request:

jobs:
  test:
    runs-on: ubuntu-latest

    services:
      postgres:
        image: postgres:18-alpine
        env:
          POSTGRES_DB: volleyvideos
          POSTGRES_USER: volleyuser
          POSTGRES_PASSWORD: volleypass
        ports:
          - 5432:5432
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

    env:
      SECRET_KEY: clave-solo-para-ci
      DEBUG: 'True'
      DB_HOST: localhost
      DB_NAME: volleyvideos
      DB_USER: volleyuser
      DB_PASSWORD: volleypass

    steps:
      - uses: actions/checkout@v5

      - uses: actions/setup-python@v6
        with:
          python-version: '3.13'
          cache: pip

      - name: Instalar dependencias del sistema
        run: |
          sudo apt-get update
          sudo apt-get install -y libheif-dev libde265-dev pkg-config

      - name: Instalar dependencias Python
        run: pip install -r requirements-dev.txt

      - name: Comprobaciones de Django
        run: python manage.py check

      - name: No debe haber migraciones pendientes de generar
        run: python manage.py makemigrations --check --dry-run

      - name: Tests
        run: python -m pytest --create-db -v
```

El paso `makemigrations --check --dry-run` es la guarda central de la fase 1: si
mover una clase de fichero generase una migración, este paso falla y el CI corta.

- [ ] **Step 2: Verificar el workflow en local antes de empujar**

Run:
```bash
docker compose -f docker-compose.dev.yml run --rm web python manage.py check
docker compose -f docker-compose.dev.yml run --rm web python manage.py makemigrations --check --dry-run
```
Expected: ambos sin salida de error. El segundo debe indicar que no hay cambios
pendientes. **Si ya indica cambios pendientes antes de empezar la fase 1**,
resolverlos ahora: arrancar la fase 1 con el árbol sucio impide distinguir las
migraciones que genera el refactor de las que ya estaban.

- [ ] **Step 3: Commit y comprobar el CI en verde**

```bash
git add .github/workflows/tests.yml
git commit -m "ci: ejecutar tests, check y guarda de migraciones en GitHub Actions"
git push origin refactor/models-split
```

Verificar en GitHub que el workflow termina en verde antes de continuar.

- [ ] **Step 4: Si `makemigrations --check` falla en CI pero no en local**

Causa habitual: diferencia de variables de entorno que alteran `INSTALLED_APPS`
o `DEBUG`. Comparar la salida de `python manage.py diffsettings` en ambos
entornos antes de tocar nada más.

---

### Task 8: Crear `CLAUDE.md`

**Files:**
- Create: `CLAUDE.md`
- Delete: `WARP.md` (symlink roto que apunta a un `CLAUDE.md` inexistente)

**Interfaces:**
- Consumes: los comandos validados en las Tasks 1-7.
- Produces: la documentación que acompaña al repo a cualquier máquina, y que
  sustituye a la memoria local del servidor de producción.

- [ ] **Step 1: Escribir `CLAUDE.md`**

```markdown
# CLAUDE.md

Proyecto Django de gestión de vídeos, imágenes y competiciones de voleibol,
multi-tenant por organización.

## Comandos

Todo comando Django se ejecuta dentro de Docker:

```bash
docker compose -f docker-compose.dev.yml run --rm web python manage.py <comando>
```

Tests:

```bash
docker compose -f docker-compose.dev.yml run --rm web python -m pytest --create-db
```

`--create-db` es **obligatorio**: sin él la BD de test queda desactualizada y
fallan columnas inexistentes.

**No ejecutar `docker-compose.dev.yml` en el servidor de producción.** Allí la
aplicación corre como proyecto compose `videosvoley` y el compose de desarrollo
resuelve al mismo nombre, así que reutilizaría los contenedores `db` y `redis`
de producción. Para una consulta puntual en producción se usa el compose por
defecto: `docker compose run --rm web python manage.py <comando>`.

## Restricciones

- Django fijado en **6.0.8** hasta que `django-celery-beat` soporte 6.1+.
- Las 16 tareas Celery llevan `name=` explícito. **No quitarlo**: las filas de
  `PeriodicTask` en base de datos dependen de ese nombre, no de la ruta del
  módulo.

## Testing

Un test existe solo si protege una decisión propia del producto. No basta con
que suba cobertura.

**Debe existir si**: protege una regla de negocio; cubre un caso límite que ya
falló o sería caro detectar en producción; verifica una transformación de datos
no trivial (parsing, normalización, resolución de duplicados); cubre un flujo
con efectos persistentes; comprueba manejo de errores en un camino crítico
(rollback, idempotencia); documenta una decisión ambigua.

**No debe existir si**: solo comprueba que Django o el ORM hacen lo suyo; solo
valida `status_code` sin comprobar efecto o payload; comprueba HTML decorativo o
clases CSS; duplica otro test más fuerte; mockea tanto que solo verifica el
mock; prueba getters, setters o properties simples.

**Antes de añadir un test**: si falla, ¿qué comportamiento real se habría roto?
¿Obligaría a cambiar código de producto o solo el test? ¿Prueba nuestra lógica o
la de la librería?

**Estructura**: `app_name/tests/` con `__init__.py`, separando `test_models.py`,
`test_views.py`, `test_forms.py`, `test_utils.py`, `test_templatetags.py`,
`test_admin.py` (este último solo si hay lógica propia).

**Admin**: saltar configuración de `ModelAdmin` y CRUD estándar; testear solo
métodos con lógica, `get_queryset()` complejos, acciones custom y `save_model()`
con validación.

## Refactor en curso

La app `videos` se está repartiendo en paquetes. Ver
`docs/superpowers/specs/2026-09-16-refactor-models-design.md`.

**No resucitar la rama `origin/refactor_apps`**: sus migraciones creaban tablas
nuevas y vacías y copiaban las filas a mano. Está descartada.
```

- [ ] **Step 2: Eliminar el symlink roto**

```bash
git rm WARP.md
```

- [ ] **Step 3: Verificar**

Run: `ls -la CLAUDE.md WARP.md 2>&1`
Expected: `CLAUDE.md` existe como fichero regular; `WARP.md` ya no existe.

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: crear CLAUDE.md con comandos, restricciones y guidelines de testing"
```

---

# FASE 1 — Paquetes dentro de `videos`

A partir de aquí, **todas** las tareas terminan con la misma verificación de
cuatro órdenes. Cualquier desviación aborta la tarea y se revierte el commit.

### Task 9: Convertir `models.py` en paquete

**Files:**
- Create: `videosvoley/videos/models/__init__.py`
- Create: `videosvoley/videos/models/category.py`
- Create: `videosvoley/videos/models/teams.py`
- Create: `videosvoley/videos/models/content.py`
- Create: `videosvoley/videos/models/competitions.py`
- Create: `videosvoley/videos/models/rosters.py`
- Create: `videosvoley/videos/models/legacy.py`
- Delete: `videosvoley/videos/models.py`
- Create: `videosvoley/videos/migrations/0036_alter_upload_to_paths.py` (generada)

**Interfaces:**
- Consumes: la red de tests de las Tasks 1-7.
- Produces: `videosvoley.videos.models` como paquete que reexporta exactamente
  los mismos nombres que exportaba el módulo. Los 84 imports repartidos en 38
  ficheros siguen funcionando sin modificarse, y las migraciones `0012`, `0015`,
  `0019` y `0020` siguen resolviendo `videosvoley.videos.models.<función>`.

Reparto de las 1433 líneas del `models.py` actual:

| Módulo | Contenido | Líneas origen |
|---|---|---|
| `category.py` | `Category` | 12-24 |
| `teams.py` | `Club`, `Team` | 300-423 |
| `content.py` | `image_upload_path`, `Video`, `Comment`, `Image` | 27-92, 644-882 |
| `competitions.py` | `LeagueManager`, `League`, `MatchManager`, `MatchAllManager`, `Match`, `ScrapingEndpoint`, `Standing` | 95-297, 426-641 |
| `rosters.py` | `person_photo_upload_path`, `Person`, `PlayerRole`, `StaffRole` | 1117-1433 |
| `legacy.py` | `player_photo_upload_path`, `staff_photo_upload_path`, `Player`, `Staff` | 885-1110 |

- [ ] **Step 1: Crear el directorio y extraer los bloques**

Todos los comandos se ejecutan desde la raíz del repositorio. `M` y `N` son
variables de conveniencia para no repetir rutas largas:

```bash
M=videosvoley/videos/models.py
N=videosvoley/videos/models_new
mkdir -p "$N"
sed -n '12,24p'     "$M" >  "$N/category.py"
sed -n '300,423p'   "$M" >  "$N/teams.py"
sed -n '27,92p'     "$M" >  "$N/content.py"
sed -n '644,882p'   "$M" >> "$N/content.py"
sed -n '95,297p'    "$M" >  "$N/competitions.py"
sed -n '426,641p'   "$M" >> "$N/competitions.py"
sed -n '1117,1433p' "$M" >  "$N/rosters.py"
sed -n '885,1110p'  "$M" >  "$N/legacy.py"
```

Los rangos se han verificado contra el fichero actual. Si el fichero ha cambiado
desde entonces, localizar los límites con
`grep -n '^class \|^def ' videosvoley/videos/models.py` y ajustar antes de
continuar.

- [ ] **Step 2: Añadir la cabecera de imports a cada módulo**

Insertar al principio de cada fichero, exactamente esto:

`videosvoley/videos/models_new/category.py`:
```python
from django.db import models
```

`videosvoley/videos/models_new/teams.py`:
```python
from django.db import models

from .category import Category
```

`videosvoley/videos/models_new/content.py`:
```python
import os
import re

from django.conf import settings
from django.core.validators import FileExtensionValidator
from django.db import models
from django.utils import timezone

from .category import Category
```

`videosvoley/videos/models_new/competitions.py`:
```python
from django.db import models

from .category import Category
from .teams import Team
```

`videosvoley/videos/models_new/rosters.py`:
```python
from django.contrib.auth import get_user_model
from django.db import models

from .teams import Team

User = get_user_model()
```

`videosvoley/videos/models_new/legacy.py`:
```python
import os
import re

from django.conf import settings
from django.core.validators import FileExtensionValidator
from django.db import models
from django.utils import timezone

from .teams import Team
```

El orden de dependencias es acíclico: `category` no importa a nadie; `teams`
importa `category`; `content` importa `category`; `competitions` importa
`category` y `teams`; `rosters` y `legacy` importan `teams`. Las referencias
cruzadas hacia `Match` ya usan strings (`FK('Match')`), que Django resuelve en
diferido.

- [ ] **Step 3: Arreglar el único import relativo roto**

En `videosvoley/videos/models_new/competitions.py`, dentro de `League.get_combined_matches()`, hay:

```python
            from .models import Match
```

En un paquete eso apunta a `videosvoley.videos.models.models`, que no existe.
`Match` vive ahora en este mismo módulo, así que la línea se **elimina** y el
método queda:

```python
    def get_combined_matches(self):
        """Returns matches from this league and all its phases"""
        if self.parent_league:
            return self.parent_league.get_combined_matches()
        else:
            league_ids = [self.id] + list(self.phases.values_list('id', flat=True))
            return Match.objects.filter(league_id__in=league_ids)
```

`Match` se define después de `League` en el fichero, pero el método se ejecuta
con el módulo ya cargado, así que la referencia resuelve sin problema.

Verificar que no queda ningún otro import relativo:

```bash
grep -n 'from \.models' videosvoley/videos/models_new/*.py
```
Expected: sin resultados.

- [ ] **Step 4: Escribir el `__init__.py`**

`videosvoley/videos/models_new/__init__.py`:

```python
"""Modelos de la app videos, repartidos por dominio.

Este paquete reexporta todos los nombres públicos que antes vivían en
models.py. No eliminar reexportaciones sin comprobar antes los 84 imports
del proyecto y las migraciones 0012, 0015, 0019 y 0020, que referencian
las funciones de upload por su ruta en este paquete.
"""

from .category import Category
from .teams import Club, Team
from .content import Comment, Image, Video, image_upload_path
from .competitions import (
    League,
    LeagueManager,
    Match,
    MatchAllManager,
    MatchManager,
    ScrapingEndpoint,
    Standing,
)
from .rosters import Person, PlayerRole, StaffRole, person_photo_upload_path
from .legacy import (
    Player,
    Staff,
    player_photo_upload_path,
    staff_photo_upload_path,
)

__all__ = [
    'Category',
    'Club',
    'Comment',
    'Image',
    'League',
    'LeagueManager',
    'Match',
    'MatchAllManager',
    'MatchManager',
    'Person',
    'Player',
    'PlayerRole',
    'ScrapingEndpoint',
    'Staff',
    'StaffRole',
    'Standing',
    'Team',
    'Video',
    'image_upload_path',
    'person_photo_upload_path',
    'player_photo_upload_path',
    'staff_photo_upload_path',
]
```

El orden de los imports respeta el grafo de dependencias y **no debe
reordenarse alfabéticamente**: `category` antes que `teams`, y `teams` antes que
`competitions`, `rosters` y `legacy`.

- [ ] **Step 5: Sustituir el módulo por el paquete**

```bash
git rm videosvoley/videos/models.py
mv videosvoley/videos/models_new videosvoley/videos/models
git add videosvoley/videos/models/
```

- [ ] **Step 6: Comprobar que Django arranca**

Run: `docker compose -f docker-compose.dev.yml run --rm web python manage.py check`
Expected: `System check identified no issues`.

Si aparece `RuntimeError: Model class ... doesn't declare an explicit app_label`,
falta un import en `__init__.py`: Django no ve el modelo porque nadie lo importa.

- [ ] **Step 7: Generar la única migración esperada**

Run: `docker compose -f docker-compose.dev.yml run --rm web python manage.py makemigrations videos --name alter_upload_to_paths`
Expected: una migración con **exactamente cuatro** `AlterField`, sobre
`image.image`, `player.photo`, `staff.photo` y `person.photo`. Django la genera
porque `upload_to` se serializa como `módulo.función` y el `__module__` de esas
funciones ha cambiado.

**Si propone cualquier otra operación** (`AddField`, `RemoveField`,
`AlterModelOptions`, `CreateModel`…), algo se ha alterado sin querer al mover el
código: revertir y comparar el módulo afectado con `git show HEAD:videosvoley/videos/models.py`.

- [ ] **Step 8: Verificar que la migración no toca la base de datos**

Run: `docker compose -f docker-compose.dev.yml run --rm web python manage.py sqlmigrate videos 0036`
Expected: **sin una sola sentencia DDL**. `upload_to` es lógica de Python, no una
columna. Si aparece cualquier `ALTER TABLE`, detenerse e investigar: significa
que el campo ha cambiado de verdad.

- [ ] **Step 9: Verificar que ya no quedan migraciones pendientes**

Run: `docker compose -f docker-compose.dev.yml run --rm web python manage.py makemigrations --check --dry-run`
Expected: sin cambios pendientes.

- [ ] **Step 10: Ejecutar toda la suite**

Run: `docker compose -f docker-compose.dev.yml run --rm web python -m pytest --create-db -v`
Expected: PASS, mismo recuento que tras la Task 6. `--create-db` reproduce las 36
migraciones desde cero, lo que además confirma que las migraciones `0012`,
`0015`, `0019` y `0020` siguen resolviendo las funciones de upload.

- [ ] **Step 11: Comprobar que el diff es solo movimiento**

Run: `git diff --cached --stat`
Expected: las líneas eliminadas de `models.py` deben coincidir aproximadamente
con las añadidas entre los seis módulos nuevos, más la cabecera de imports de
cada uno y el `__init__.py`. Una diferencia grande indica código perdido o
duplicado.

- [ ] **Step 12: Commit**

```bash
git add videosvoley/videos/models/ videosvoley/videos/migrations/0036_alter_upload_to_paths.py
git commit -m "refactor(videos): repartir models.py en un paquete por dominio"
```

---

### Task 10: Convertir `admin.py` en paquete

**Files:**
- Create: `videosvoley/videos/admin/__init__.py`
- Create: `videosvoley/videos/admin/category.py`
- Create: `videosvoley/videos/admin/teams.py`
- Create: `videosvoley/videos/admin/content.py`
- Create: `videosvoley/videos/admin/competitions.py`
- Create: `videosvoley/videos/admin/rosters.py`
- Create: `videosvoley/videos/admin/legacy.py`
- Delete: `videosvoley/videos/admin.py`

**Interfaces:**
- Consumes: `videosvoley.videos.models` como paquete (Task 9).
- Produces: `videosvoley.videos.admin` como paquete cuyo `__init__.py` importa
  todos los submódulos, de modo que los decoradores `@admin.register` se ejecuten
  al cargar la app.

- [ ] **Step 1: Reparto exacto de las 22 clases**

Verificado contra el fichero actual. Las líneas incluyen el decorador
`@admin.register` cuando lo hay:

| Módulo destino | Clases | Líneas origen |
|---|---|---|
| `category.py` | `CategoryAdmin` | 17-34 |
| `teams.py` | `ClubAdmin`, `TeamAdmin` | 232-295, 310-446 |
| `content.py` | `VideoAdmin`, `ImageInline`, `ImageAdmin` | 35-43, 454-474, 660-940 |
| `competitions.py` | `LeagueAdmin`, `ScrapingEndpointInline`, `ScrapingEndpointAdmin`, `MatchAdmin`, `StandingAdmin` | 44-231, 447-453, 475-499, 500-631, 632-659 |
| `rosters.py` | `PlayerRoleInline`, `StaffRoleInline`, `PersonAdmin`, `PlayerRoleAdmin`, `StaffRoleAdmin` | 1226-1234, 1235-1243, 1244-1323, 1324-1362, 1363-fin |
| `legacy.py` | `PlayerInline`, `StaffInline`, `PlayerAdmin`, `StaffAdmin` | 296-302, 303-309, 1088-1151, 1152-1225 |
| `periodic_tasks.py` | `CustomPeriodicTaskAdmin` | 941-1087 |

**`periodic_tasks.py` es un séptimo módulo no previsto en la spec.**
`CustomPeriodicTaskAdmin` registra `PeriodicTask`, un modelo de
`django_celery_beat`, y no pertenece a ningún dominio de `videos`. Meterlo en
cualquiera de los seis sería arbitrario.

**Dos acoplamientos que hay que aceptar entre módulos del admin:**

- `teams.py` importa `PlayerInline` y `StaffInline` desde `legacy.py`, porque
  `TeamAdmin` los usa. Cuando la fase 3 elimine `legacy.py`, habrá que quitar
  esos inlines de `TeamAdmin`. Dejarlo anotado en el commit.
- `competitions.py` importa `ImageInline` desde `content.py` si `MatchAdmin` lo
  usa. Comprobarlo al mover `MatchAdmin` y añadir el import si hace falta.

- [ ] **Step 2: Extraer los bloques a los siete módulos**

Cada módulo empieza importando lo que necesite de `django.contrib.admin`,
`unfold` y `..models`. Ejemplo de cabecera para `admin/competitions.py`:

```python
from django.contrib import admin
from unfold.admin import ModelAdmin

from ..models import League, Match, ScrapingEndpoint, Standing
```

Los imports desde los modelos usan `..models` (dos puntos: subir de `admin/` a
`videos/`), no `.models`.

- [ ] **Step 3: Escribir el `__init__.py`**

```python
"""Configuración del admin de la app videos, repartida por dominio.

Importar los submódulos aquí es lo que ejecuta los decoradores
@admin.register. No eliminar ningún import: el modelo dejaría de
aparecer en el admin sin que nada falle.
"""

from . import category  # noqa: F401
from . import content  # noqa: F401
from . import legacy  # noqa: F401
from . import teams  # noqa: F401
from . import competitions  # noqa: F401
from . import rosters  # noqa: F401
from . import periodic_tasks  # noqa: F401
```

El orden importa: `legacy` antes que `teams` (que importa sus inlines) y
`content` antes que `competitions` (que puede importar `ImageInline`).

- [ ] **Step 4: Sustituir el módulo por el paquete**

```bash
git rm videosvoley/videos/admin.py
git add videosvoley/videos/admin/
```

- [ ] **Step 5: Verificar que todos los modelos siguen registrados**

Run:
```bash
docker compose -f docker-compose.dev.yml run --rm web python manage.py shell -c "
from django.contrib import admin
registrados = sorted(m._meta.label for m in admin.site._registry)
print(len(registrados))
for r in registrados:
    print(r)
"
```
Expected: la lista debe contener los mismos modelos que antes del cambio. Anotar
el recuento **antes** de empezar la tarea ejecutando el mismo comando sobre
`HEAD`, y comparar. Un modelo que desaparece del admin no rompe ningún test.

- [ ] **Step 6: Verificación estándar de fase 1**

```bash
docker compose -f docker-compose.dev.yml run --rm web python manage.py check
docker compose -f docker-compose.dev.yml run --rm web python manage.py makemigrations --check --dry-run
docker compose -f docker-compose.dev.yml run --rm web python -m pytest --create-db
git diff --cached --stat
```
Expected: `check` limpio, **ninguna** migración pendiente (a diferencia de la
Task 9, aquí no hay funciones serializadas en migraciones), tests en verde, y el
diff solo movimiento.

- [ ] **Step 7: Commit**

```bash
git commit -m "refactor(videos): repartir admin.py en un paquete por dominio"
```

---

### Task 11: Convertir `forms.py` en paquete

**Files:**
- Create: `videosvoley/videos/forms/__init__.py`
- Create: `videosvoley/videos/forms/content.py`
- Create: `videosvoley/videos/forms/competitions.py`
- Create: `videosvoley/videos/forms/rosters.py`
- Delete: `videosvoley/videos/forms.py`

**Interfaces:**
- Consumes: `videosvoley.videos.models` (Task 9).
- Produces: `videosvoley.videos.forms` reexportando todas las clases de
  formulario, para que `views.py` y `admin/` sigan importándolas igual.

- [ ] **Step 1: Reparto exacto de los 13 formularios**

Verificado contra el fichero actual:

| Módulo destino | Formularios | Líneas origen |
|---|---|---|
| `content.py` | `VideoForm`, `CommentForm`, `ImageUploadForm`, `ImageModerationForm`, `ImageFilterForm`, `VideoEntryForm`, `VideoBulkSharedForm` | 9-114, 115-130, 196-349, 350-382, 383-473, 1028-1049, 1050-fin |
| `competitions.py` | `MatchAdminForm`, `FriendlyMatchForm`, `MatchResultForm` | 131-195, 474-762, 911-964 |
| `rosters.py` | `PersonForm`, `PlayerRoleForm`, `StaffRoleForm` | 763-840, 841-910, 965-1027 |

**No hay ningún formulario de `teams`**, así que este paquete tiene tres
módulos, no cuatro. No crear un `teams.py` vacío.

- [ ] **Step 2: Extraer los bloques con sus cabeceras de import**

Ejemplo de cabecera para `forms/content.py`:

```python
from django import forms

from ..models import Category, Image, Video
```

- [ ] **Step 3: Escribir el `__init__.py`**

A diferencia del admin, aquí hay que **reexportar nombres**, no solo importar
módulos, porque otros ficheros hacen `from .forms import XForm`:

```python
"""Formularios de la app videos, repartidos por dominio."""

from .content import *  # noqa: F401,F403
from .competitions import *  # noqa: F401,F403
from .rosters import *  # noqa: F401,F403
```

Cada submódulo declara su propio `__all__` con las clases que expone, para que
el `import *` sea explícito y no arrastre los imports de Django. Por ejemplo, al
final de `forms/rosters.py`:

```python
__all__ = ['PersonForm', 'PlayerRoleForm', 'StaffRoleForm']
```

- [ ] **Step 4: Comprobar que no falta ningún nombre**

Antes de borrar el fichero original, comparar:

```bash
git show HEAD:videosvoley/videos/forms.py | grep -oE '^class [A-Za-z0-9_]+' | sed 's/class //' | sort > /tmp/forms_antes.txt
docker compose -f docker-compose.dev.yml run --rm web python -c "
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()
import videosvoley.videos.forms as f
print('\n'.join(sorted(n for n in dir(f) if n[0].isupper())))
" | sort > /tmp/forms_despues.txt
diff /tmp/forms_antes.txt /tmp/forms_despues.txt
```
Expected: sin líneas que falten en `forms_despues.txt`. Que sobren nombres es
aceptable (clases importadas de Django); que falte alguno no lo es.

- [ ] **Step 5: Sustituir y verificar**

```bash
git rm videosvoley/videos/forms.py
git add videosvoley/videos/forms/
docker compose -f docker-compose.dev.yml run --rm web python manage.py check
docker compose -f docker-compose.dev.yml run --rm web python manage.py makemigrations --check --dry-run
docker compose -f docker-compose.dev.yml run --rm web python -m pytest --create-db
```
Expected: todo en verde, sin migraciones pendientes.

- [ ] **Step 6: Commit**

```bash
git commit -m "refactor(videos): repartir forms.py en un paquete por dominio"
```

---

### Task 12: Convertir `views.py` en paquete

**Files:**
- Create: `videosvoley/videos/views/__init__.py`
- Create: `videosvoley/videos/views/content.py`
- Create: `videosvoley/videos/views/moderation.py`
- Create: `videosvoley/videos/views/competitions.py`
- Create: `videosvoley/videos/views/teams.py`
- Create: `videosvoley/videos/views/rosters.py`
- Create: `videosvoley/videos/views/pages.py`
- Delete: `videosvoley/videos/views.py`

**Interfaces:**
- Consumes: `videosvoley.videos.models` (Task 9) y `videosvoley.videos.forms`
  (Task 11).
- Produces: `videosvoley.videos.views` reexportando todas las vistas, para que
  `videosvoley/videos/urls.py` **no necesite ningún cambio**.

Es el fichero más grande del proyecto (2797 líneas) y el de mayor beneficio.

- [ ] **Step 1: Inventariar las vistas que `urls.py` referencia**

Run: `grep -oE 'views\.[a-z_]+' videosvoley/videos/urls.py | sort -u > /tmp/vistas_en_urls.txt && cat /tmp/vistas_en_urls.txt`

Esta lista es el contrato: todos esos nombres deben seguir accesibles como
`videosvoley.videos.views.<nombre>` al terminar.

- [ ] **Step 2: Reparto exacto de las 45 vistas**

Verificado contra el fichero actual. Las 45 funciones se reparten así:

| Módulo destino | Vistas | Nº |
|---|---|---|
| `content.py` | `video_list`, `video_create`, `video_bulk_create`, `video_detail`, `image_gallery`, `image_gallery_albums`, `image_upload`, `image_bulk_upload`, `image_detail`, `match_images`, `album_group_images` | 11 |
| `moderation.py` | `image_moderation`, `image_moderate_action`, `image_moderate_bulk`, `moderation_counts_api`, `moderation_panel`, `approve_user_api`, `reject_user_api`, `moderate_image_api` | 8 |
| `competitions.py` | `league_list`, `league_detail`, `match_detail`, `calendar_view`, `friendly_match_create`, `ajax_search_teams`, `ajax_add_match_result`, `ajax_acta_lineup`, `standings_view`, `ajax_matches_by_category`, `ajax_teams_by_league_category` | 11 |
| `teams.py` | `ajax_register_team`, `team_list`, `team_roster` | 3 |
| `rosters.py` | `roster_overview`, `person_list`, `person_detail`, `person_create`, `person_edit`, `player_role_create`, `staff_role_create`, `player_role_edit`, `staff_role_edit`, `player_role_toggle_active`, `staff_role_toggle_active` | 11 |
| `pages.py` | `about` | 1 |

**El total debe ser 45.** Contarlo al terminar:
`grep -c '^def ' videosvoley/videos/views/*.py | awk -F: '{s+=$2} END {print s}'`

**`moderation.py` es un módulo no previsto en la spec.** La moderación atraviesa
dominios: modera imágenes y también usuarios (`approve_user_api`,
`reject_user_api`). Repartir esas ocho vistas entre `content` y un hipotético
`users` las separaría de un flujo que se lee y se cambia junto.

Las funciones auxiliares privadas viajan con la vista que las usa. Si varias
vistas de módulos distintos comparten una, va a `views/helpers.py` y se añade a
la lista de módulos, anotándolo en el commit.

Cabecera tipo para `views/competitions.py`:

```python
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from ..forms import FriendlyMatchForm
from ..models import League, Match, Standing, Team
```

Ajustar los imports a lo que use realmente cada módulo.

- [ ] **Step 3: Escribir el `__init__.py`**

```python
"""Vistas de la app videos, repartidas por dominio.

urls.py importa este paquete y espera encontrar aquí todos los nombres de
vista que referencia. Ver el contrato en la Task 12 del plan de refactor.
"""

from .content import *  # noqa: F401,F403
from .moderation import *  # noqa: F401,F403
from .competitions import *  # noqa: F401,F403
from .teams import *  # noqa: F401,F403
from .rosters import *  # noqa: F401,F403
from .pages import *  # noqa: F401,F403
```

Cada submódulo declara `__all__` con sus vistas públicas. Por ejemplo, al final
de `views/pages.py`:

```python
__all__ = ['about']
```

- [ ] **Step 4: Verificar el contrato con `urls.py`**

```bash
docker compose -f docker-compose.dev.yml run --rm web python -c "
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()
import videosvoley.videos.views as v
faltan = [n.split('.')[1] for n in open('/tmp/vistas_en_urls.txt').read().split()
          if not hasattr(v, n.split('.')[1])]
print('FALTAN:', faltan or 'ninguna')
"
```
Expected: `FALTAN: ninguna`. Si falta alguna, no está reexportada y las URLs que
la usan darían error al arrancar.

- [ ] **Step 5: Verificar que todas las URLs resuelven**

```bash
docker compose -f docker-compose.dev.yml run --rm web python -c "
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()
from django.urls import get_resolver
resolver = get_resolver()
print(len(resolver.reverse_dict), 'entradas resueltas')
"
```
Expected: sin excepción. Un `ImportError` aquí significa que `urls.py` no
encuentra una vista.

- [ ] **Step 6: Verificación estándar de fase 1**

```bash
docker compose -f docker-compose.dev.yml run --rm web python manage.py check
docker compose -f docker-compose.dev.yml run --rm web python manage.py makemigrations --check --dry-run
docker compose -f docker-compose.dev.yml run --rm web python -m pytest --create-db
```
Expected: todo en verde.

- [ ] **Step 7: Commit**

```bash
git rm videosvoley/videos/views.py
git add videosvoley/videos/views/
git commit -m "refactor(videos): repartir views.py en un paquete por dominio"
```

---

### Task 13: Convertir `tasks.py` en paquete

**Files:**
- Create: `videosvoley/videos/tasks/__init__.py`
- Create: `videosvoley/videos/tasks/scraping.py`
- Create: `videosvoley/videos/tasks/enrichment.py`
- Create: `videosvoley/videos/tasks/rfevb.py`
- Delete: `videosvoley/videos/tasks.py`

**Interfaces:**
- Consumes: `videosvoley.videos.models` (Task 9) y `videosvoley.videos.scraping`
  (aún módulo en este punto; la Task 14 lo convierte en paquete después).
- Produces: `videosvoley.videos.tasks` reexportando las 16 tareas, para que
  `config/celery.py:20` (`from videosvoley.videos.tasks import *`) siga
  registrándolas y para que `videosvoley/videos/admin/` siga importándolas.

**Las 16 tareas llevan `name=` explícito** (`@shared_task(name='scrape_league')`),
así que el nombre registrado no depende de la ruta del módulo y las filas de
`PeriodicTask` en base de datos **no se ven afectadas**. No quitar ni renombrar
ningún `name=`.

Reparto por responsabilidad:

| Módulo | Tareas |
|---|---|
| `scraping.py` | `scrape_all_leagues`, `scrape_league`, `scrape_calendar`, `scrape_results`, `scrape_clubs`, `scrape_teams`, `handle_withdrawn_teams` |
| `enrichment.py` | `enrich_matches_json`, `enrich_single_league_json`, `enrich_upcoming_matches`, `scrape_and_enrich_all`, `scrape_json_results`, `scrape_json_upcoming`, `process_json_unified` |
| `rfevb.py` | `scrape_rfevb_competition`, `scrape_rfevb_final_classification` |

- [ ] **Step 1: Extraer los bloques**

Localizar los límites con `grep -n '@shared_task' videosvoley/videos/tasks.py` y
mover cada tarea completa, con las funciones auxiliares que solo ella use.

- [ ] **Step 2: Escribir el `__init__.py`**

```python
"""Tareas Celery de la app videos, repartidas por responsabilidad.

config/celery.py hace `from videosvoley.videos.tasks import *` para forzar
el registro. Las 16 tareas llevan name= explícito: ese nombre es el que
guardan las filas de PeriodicTask, y no debe cambiarse nunca.
"""

from .scraping import *  # noqa: F401,F403
from .enrichment import *  # noqa: F401,F403
from .rfevb import *  # noqa: F401,F403
```

- [ ] **Step 3: Verificar que Celery registra las 16 tareas con el mismo nombre**

```bash
docker compose -f docker-compose.dev.yml run --rm web python -c "
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()
from config.celery import app
propias = sorted(n for n in app.tasks if not n.startswith('celery.'))
print(len(propias))
for n in propias:
    print(n)
"
```
Expected: **16** tareas, con exactamente los mismos nombres que antes del
cambio. Ejecutar este mismo comando sobre `HEAD` antes de empezar y comparar las
dos listas. Si algún nombre cambia, las tareas periódicas guardadas en base de
datos dejarían de encontrar su función.

- [ ] **Step 4: Verificar que los tests de tareas siguen parcheando bien**

`videosvoley/videos/tests/test_scraping.py` usa
`@patch('videosvoley.videos.tasks.scrape_rfevb_fases')`. El reexport mantiene ese
path válido.

Run: `docker compose -f docker-compose.dev.yml run --rm web python -m pytest videosvoley/videos/tests/test_scraping.py -v --create-db`
Expected: PASS.

Si algún `patch` falla con `AttributeError`, el nombre no está reexportado en el
`__init__.py`.

- [ ] **Step 5: Verificación estándar de fase 1**

```bash
docker compose -f docker-compose.dev.yml run --rm web python manage.py check
docker compose -f docker-compose.dev.yml run --rm web python manage.py makemigrations --check --dry-run
docker compose -f docker-compose.dev.yml run --rm web python -m pytest --create-db
```
Expected: todo en verde.

- [ ] **Step 6: Commit**

```bash
git rm videosvoley/videos/tasks.py
git add videosvoley/videos/tasks/
git commit -m "refactor(videos): repartir tasks.py en un paquete por responsabilidad"
```

---

### Task 14: Convertir `scraping.py` en paquete

**Files:**
- Create: `videosvoley/videos/scraping/__init__.py`
- Create: `videosvoley/videos/scraping/base.py`
- Create: `videosvoley/videos/scraping/parsers.py`
- Create: `videosvoley/videos/scraping/federation.py`
- Create: `videosvoley/videos/scraping/acta.py`
- Create: `videosvoley/videos/scraping/rfevb.py`
- Delete: `videosvoley/videos/scraping.py`

**Interfaces:**
- Consumes: `videosvoley.videos.models` (Task 9).
- Produces: `videosvoley.videos.scraping` reexportando `RFEVBPhaseParser`,
  `RFEVBTeamsParser` y todo lo que importan `tasks/` y los comandos de
  `management/commands/`.

Va el último porque es el fichero con más acoplamiento y porque un fallo aquí
corrompe datos scrapeados en silencio, sin que ninguna página dé error. Llega con
la red de tests RFEVB ya en su sitio.

- [ ] **Step 1: Inventariar el contrato público**

```bash
grep -rhoE 'from (videosvoley\.videos\.)?\.?scraping import [A-Za-z0-9_, ]+' \
  --include=*.py videosvoley | sort -u
```

Esta lista de nombres es lo que el `__init__.py` debe reexportar sin falta.

- [ ] **Step 2: Reparto exacto de los 14 elementos**

Verificado contra el fichero actual:

| Módulo destino | Contenido | Líneas origen |
|---|---|---|
| `base.py` | `validate_volleyball_score`, `ScrapingError`, `BaseParser` | 18-61, 62-66, 67-96 |
| `parsers.py` | `StandingsParser`, `MatchesParser`, `CalendarParser`, `JSONMatchesParser`, `JSONUnifiedParser` | 97-170, 171-290, 291-436, 437-577, 578-744 |
| `federation.py` | `FederationScraper` | 745-2125 |
| `acta.py` | `_extract_player_text_from_cell`, `_parse_lineup_table`, `_parse_set_table`, `parse_acta_lineup` | 2126-2340 |
| `rfevb.py` | `RFEVBPhaseParser`, `RFEVBTeamsParser` | 2341-2489, 2490-fin |

**`federation.py` incumplirá el criterio de ~400 líneas y es la excepción
justificada prevista en el plan.** `FederationScraper` es una sola clase de unas
1380 líneas. Partirla exige decidir qué métodos forman subunidades coherentes,
lo cual es reescritura de diseño y no movimiento mecánico: queda fuera del
alcance de la fase 1. Anotarlo en el mensaje del commit y abrir una issue de
seguimiento.

- [ ] **Step 3: Escribir el `__init__.py`**

```python
"""Scraping de la app videos, repartido por fuente de datos."""

from .base import *  # noqa: F401,F403
from .parsers import *  # noqa: F401,F403
from .acta import *  # noqa: F401,F403
from .federation import *  # noqa: F401,F403
from .rfevb import *  # noqa: F401,F403
```

Cada submódulo declara `__all__`. El orden respeta las dependencias: `base` no
importa a nadie; `parsers`, `acta` y `rfevb` usan `BaseParser` de `base`; y
`federation` usa los parsers.

`acta.py` expone solo `parse_acta_lineup` en su `__all__`: las tres funciones con
prefijo `_` son auxiliares suyas y no forman parte del contrato público.

- [ ] **Step 4: Verificar el contrato público**

Comprobar que cada nombre del inventario del Step 1 sigue importable:

```bash
docker compose -f docker-compose.dev.yml run --rm web python -c "
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()
from videosvoley.videos.scraping import RFEVBPhaseParser, RFEVBTeamsParser
print('contrato mínimo OK')
"
```
Expected: `contrato mínimo OK`. Ampliar la línea de import con el resto de
nombres del inventario.

- [ ] **Step 5: Verificar que los comandos de management siguen arrancando**

```bash
docker compose -f docker-compose.dev.yml run --rm web python manage.py help 2>&1 | grep -A40 '\[videos\]'
```
Expected: la lista completa de comandos de la app `videos`. Django los descubre
importándolos, así que un `ImportError` en cualquiera los haría desaparecer de
esta lista sin dar error.

- [ ] **Step 6: Verificación estándar de fase 1**

```bash
docker compose -f docker-compose.dev.yml run --rm web python manage.py check
docker compose -f docker-compose.dev.yml run --rm web python manage.py makemigrations --check --dry-run
docker compose -f docker-compose.dev.yml run --rm web python -m pytest --create-db
```
Expected: todo en verde, con los 30 tests de scraping RFEVB incluidos.

- [ ] **Step 7: Commit y cierre de la fase 1**

```bash
git rm videosvoley/videos/scraping.py
git add videosvoley/videos/scraping/
git commit -m "refactor(videos): repartir scraping.py en un paquete por fuente de datos"
git push origin refactor/models-split
```

Verificar que el CI de GitHub Actions termina en verde.

---

## Verificación final de las fases 0 y 1

- [ ] **Ningún fichero de `videosvoley/videos/` supera las ~400 líneas**

```bash
find videosvoley/videos -name '*.py' -not -path '*/migrations/*' | xargs wc -l | sort -rn | head -20
```
Expected: ningún fichero por encima de ~400 líneas salvo justificación explícita
anotada en el commit correspondiente.

- [ ] **Los 84 imports originales siguen intactos**

```bash
git diff main --stat -- '*.py' | grep -vE 'videos/(models|admin|forms|views|tasks|scraping)/|tests/|migrations/'
```
Expected: ningún fichero de la aplicación fuera de los paquetes refactorizados
debería haber cambiado sus imports.

- [ ] **Una sola migración nueva y sin DDL**

```bash
git diff main --name-only -- videosvoley/videos/migrations/
docker compose -f docker-compose.dev.yml run --rm web python manage.py sqlmigrate videos 0036
```
Expected: un único fichero nuevo (`0036_alter_upload_to_paths.py`) y `sqlmigrate`
sin salida DDL.

- [ ] **La suite completa en verde y el CI también**

```bash
docker compose -f docker-compose.dev.yml run --rm web python -m pytest --create-db -v
```

## Fuera del alcance de este plan

- **Fase 2** (apps Django reales con `SeparateDatabaseAndState`), **fase 3**
  (retirada de `Player`/`Staff` y `League.category`) y **fase 4** (mudanza de
  vistas, URLs y templates). Cada una tendrá su propio plan, escrito cuando su
  precondición sea real.
- Arreglar la rama inalcanzable de `Match.clean()` detectada en la Task 6.
- Cualquier reescritura del contenido de las funciones movidas. Las fases 0 y 1
  reparten código; no lo reescriben.
