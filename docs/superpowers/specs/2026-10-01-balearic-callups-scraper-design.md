# Scraper de Convocatorias Selección Balear y Cruce con Plantillas

**Fecha:** 2026-10-01  
**Estado:** Propuesta aprobada para especificación  
**Issue:** [#287](https://github.com/trencaclosqu3s/ilovevoley/issues/287)  
**Apps afectadas:** `ilovevoley.competitions`, `ilovevoley.rosters`, `ilovevoley.users`

---

## 1. Contexto y Diagnóstico del Problema

### El Problema
Los clubes federados de voleibol en Baleares deben revisar periódicamente de forma manual las circulares emitidas por la Federació de Voleibol de les Illes Balears (FVBIB / `voleibolib.net`) para comprobar si algún jugador o jugadora de su cantera ha sido convocado/a con las selecciones autonómicas (pista o vóley playa, categorías infantil, cadete, juvenil/sub-19, etc.).

Esta operativa manual presenta múltiples fricciones:
1. **Detección tardía**: Las convocatorias se publican con pocos días de antelación para entrenamientos o concentraciones; perder una circular puede provocar inasistencias o falta de coordinación.
2. **Pérdida del historial deportivo**: Los clubes no disponen de un registro centralizado y automático del historial de selecciones autonómicas de sus jugadores en la plataforma.
3. **Falta de visibilidad y orgullo de club**: No existe difusión automática a los socios o familias del club para celebrar las convocatorias de cantera.
4. **Variabilidad en actas y formatos**: Los documentos federativos presentan variaciones en cómo escriben los nombres (ej. omitir el segundo nombre de pila, abreviar el segundo apellido, erratas tipográficas en apellidos o nombres de clubes abreviados). Un cruce ingenuo de cadenas completas falla sistemáticamente.

### Beneficio Esperado
Detección automática e inmediata de cada nueva circular federativa, descarga y extracción del documento PDF oficial, categorización de metadatos, cruce inteligente de identidades contra las plantillas activas del club tenant, persistencia estructurada y envío de alertas Web Push diferenciadas por rol (noticia general para confirmados, alerta de revisión para dudas).

---

## 2. Decisiones de Arquitectura

### 2.1. Ubicación de Modelos y Servicios en `competitions`
Siguiendo las pautas de arquitectura de `GEMINI.md`, la app `competitions` centraliza la relación con las federaciones, los scrapers (`voleibolib`, RFEVB) y las notificaciones de competición.
- Los modelos de persistencia de convocatorias federativas se ubicarán en `ilovevoley/competitions/models/callups.py` y se exportarán en `ilovevoley/competitions/models/__init__.py`.
- La lógica de scraping, parseo y cruce residirá en servicios modulares dentro de `ilovevoley/competitions/services/`.

### 2.2. Modelos de Dominio
1. **`FederationCallUp`**:
   - Representa la convocatoria/circular oficial descargada desde la federación.
   - Vinculada a `core.Season`.
   - Clave única de idempotencia `source_url` (nombre del fichero PDF remoto, ej. `1785324870_3735.pdf`).
   - Almacena archivo PDF descargado, hash SHA-256 para detectar re-subidas, texto extraído en bruto y metadatos clasificados (modalidad, categoría, género, número de convocatoria).
2. **`CallUpPlayer`**:
   - Cada jugador/a individual que figura en el documento oficial.
   - Almacena los datos textuales brutos extraídos del PDF (`raw_club`, `raw_last_name`, `raw_first_name`, `raw_birth_year`).
   - Registra el resultado del cruce: `organization` (tenant detectado), `person` (FK opcional a `rosters.Person`), `match_status` (`confirmed`, `suspected`, `rejected`, `unmatched`), `match_score` y notas explicativas del cruce.
   - Campos de auditoría de moderación (`reviewed_by`, `reviewed_at`).

### 2.3. Cliente Federativo e Idempotencia
- **Endpoint**: `https://www.voleibolib.net/JSON/get_circulares.asp?tipo=7&pag=0&temp={temp}`
- **Parámetro `temp`**: Derivado de `Season` (formato `YY(YY+1)`, ej. para 2025-26 -> `2526`).
- **Descargas**: `https://voleibolib.federatio.com/upload/descargas/{URL}`.
- **Idempotencia**: Si ya existe una `FederationCallUp` con el mismo `source_url` y el SHA-256 no ha cambiado, se omite el re-procesamiento salvo con el flag `--force`.

### 2.4. Extracción PDF con `pypdf`
- Se utiliza la librería ligera `pypdf>=6.19.0` (ya presente en `requirements.txt`).
- Modo de extracción posicional: `page.extract_text(extraction_mode="layout")` para mantener la separación espacial de columnas (`CLUB`, `LLINATGES`, `NOM`, `ANY`).
- Parser estructurado con expresiones regulares posicionales tolerantes a columnas y multiconvocatorias en un mismo PDF.

### 2.5. Cruce Antroponímico Token-Based (Solución a Nombres Compuestos y Variantes)
Para evitar los fallos del fuzzy ingenuo, el cruce divide la evaluación en componentes:
1. **Club Match**: Limpieza de prefijos comunes (`CV`, `C.V.`, `Club Voleibol`, `VC`) y cotejo de tokens raíz contra `org.club.name`, `org.name` y los alias en `org.club_team_names`.
2. **Nombre de Pila (First Name)**: Análisis por tokens. Si el nombre del PDF (`"Lluc"`) coincide con el token inicial de un nombre compuesto (`"Lluc Aleix"`) o es un subconjunto, se asigna **1.0 (100%)**.
3. **Apellidos (Last Name)**: Si el PDF contiene un único apellido que coincide con el **primer apellido canónico** de la ficha en base de datos, se asigna una puntuación alta (**0.95**) en lugar de penalizar la ausencia del segundo apellido.
4. **Ancla Determinista del Año de Nacimiento (`ANY`)**: Si el año extraído del PDF coincide exactamente con el año de `birth_date` de la ficha, actúa como confirmación determinante antifallos.

### 2.6. Notificaciones Web Push Diferenciadas
- **Confirmados (`confirmed`)**: Notificación general a los usuarios de la organización (canal de orgullo/noticias) indicando nombre del jugador, categoría y modalidad.
- **Dudas (`suspected`)**: Notificación dirigida exclusivamente a administradores y managers del tenant solicitando confirmación o descarte en el panel.

---

## 3. Especificación Detallada de Modelos y Componentes

### 3.1. Modelos (`ilovevoley/competitions/models/callups.py`)

```python
from django.conf import settings
from django.db import models


class FederationCallUp(models.Model):
    MODALITY_BEACH = 'beach'
    MODALITY_INDOOR = 'indoor'
    MODALITY_CHOICES = [
        (MODALITY_BEACH, 'Vóley Playa'),
        (MODALITY_INDOOR, 'Vóley Pista'),
    ]

    GENDER_MALE = 'M'
    GENDER_FEMALE = 'F'
    GENDER_MIXED = 'X'
    GENDER_CHOICES = [
        (GENDER_MALE, 'Masculino'),
        (GENDER_FEMALE, 'Femenino'),
        (GENDER_MIXED, 'Mixto / No especificado'),
    ]

    season = models.ForeignKey(
        'core.Season',
        on_delete=models.PROTECT,
        related_name='callups',
        verbose_name='Temporada',
    )
    title = models.CharField(max_length=255, verbose_name='Título de la circular')
    circular_date = models.DateField(null=True, blank=True, verbose_name='Fecha de circular')
    source_url = models.CharField(
        max_length=255,
        unique=True,
        verbose_name='Archivo PDF / URL de origen',
        help_text='Nombre del fichero PDF remoto (ej: 1785324870_3735.pdf)',
    )
    pdf_file = models.FileField(
        upload_to='callups/pdfs/%Y/',
        null=True,
        blank=True,
        verbose_name='Archivo PDF local',
    )
    pdf_sha256 = models.CharField(max_length=64, blank=True, verbose_name='SHA256 del PDF')

    modality = models.CharField(max_length=20, choices=MODALITY_CHOICES, default=MODALITY_INDOOR, verbose_name='Modalidad')
    category_name = models.CharField(max_length=50, blank=True, verbose_name='Categoría')
    gender = models.CharField(max_length=10, choices=GENDER_CHOICES, default=GENDER_MIXED, verbose_name='Género')
    callup_number = models.CharField(max_length=50, blank=True, verbose_name='Número de convocatoria')

    raw_text = models.TextField(blank=True, verbose_name='Texto extraído del PDF')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'competitions_federation_callup'
        verbose_name = 'Convocatoria Federativa'
        verbose_name_plural = 'Convocatorias Federativas'
        ordering = ['-circular_date', '-created_at']

    def __str__(self):
        return self.title


class CallUpPlayer(models.Model):
    STATUS_CONFIRMED = 'confirmed'
    STATUS_SUSPECTED = 'suspected'
    STATUS_REJECTED = 'rejected'
    STATUS_UNMATCHED = 'unmatched'
    STATUS_CHOICES = [
        (STATUS_CONFIRMED, 'Confirmado'),
        (STATUS_SUSPECTED, 'Dudoso / Requiere Revisión'),
        (STATUS_REJECTED, 'Descartado'),
        (STATUS_UNMATCHED, 'Sin Coincidencia (Otro Club)'),
    ]

    callup = models.ForeignKey(
        FederationCallUp,
        on_delete=models.CASCADE,
        related_name='players',
        verbose_name='Convocatoria',
    )
    raw_club = models.CharField(max_length=150, blank=True, verbose_name='Club en PDF')
    raw_last_name = models.CharField(max_length=150, blank=True, verbose_name='Apellidos en PDF')
    raw_first_name = models.CharField(max_length=150, blank=True, verbose_name='Nombre en PDF')
    raw_birth_year = models.PositiveSmallIntegerField(null=True, blank=True, verbose_name='Año nacimiento en PDF')

    organization = models.ForeignKey(
        'core.Organization',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='callup_players',
        verbose_name='Organización / Tenant',
    )
    person = models.ForeignKey(
        'rosters.Person',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='callups',
        verbose_name='Persona Vinculada',
    )
    match_status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_UNMATCHED,
        verbose_name='Estado del cruce',
    )
    match_score = models.FloatField(default=0.0, verbose_name='Puntuación de coincidencia')
    match_notes = models.CharField(max_length=255, blank=True, verbose_name='Notas del cruce')
    notification_sent = models.BooleanField(default=False, verbose_name='Notificación enviada')

    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        verbose_name='Revisado por',
    )
    reviewed_at = models.DateTimeField(null=True, blank=True, verbose_name='Fecha de revisión')

    class Meta:
        db_table = 'competitions_callup_player'
        verbose_name = 'Jugador Convocado'
        verbose_name_plural = 'Jugadores Convocados'
        ordering = ['callup', 'raw_last_name', 'raw_first_name']

    @property
    def raw_full_name(self):
        return f"{self.raw_first_name} {self.raw_last_name}".strip()

    def __str__(self):
        return f"{self.raw_full_name} ({self.raw_club})"
```

---

### 3.2. Normalización de Títulos (`callup_parser.py`)

Función `parse_callup_title(title: str) -> dict`:
- **Modalidad**:
  - `beach`: si contiene `\bVP\b`, `VOLEI PLATJA`, `VOLEY PLAYA` o `BEACH`.
  - `indoor`: por defecto.
- **Categoría**:
  - `Infantil`: `\bINF\b`, `INFANTIL`, o códigos de circular `IF` / `IM`.
  - `Cadete`: `\bCAD\b`, `CADET`, `CADETE`, o `CF` / `CM`.
  - `Juvenil / Sub-19`: `\bSUB19\b`, `\bJUV\b`, `JUVENIL`, o `JF` / `JM`.
  - `Sub-21`: `\bSUB21\b`.
  - `Senior`: `\bSEN\b`, `SENIOR`.
- **Género**:
  - `F`: `\b(FEM|F|FEMENI|FEMENÍ|FEMENINA)\b`, o sufijos `IF`, `CF`, `JF`.
  - `M`: `\b(MASC|M|MASCULI|MASCULÍ|MASCULINA)\b`, o sufijos `IM`, `CM`, `JM`.
  - `X`: si no se puede determinar.
- **Número de convocatoria**:
  - Extrae secuencias tipo `3ª`, `9ª Y 10ª`, `23-30`, etc.

---

### 3.3. Extracción de Jugadores desde PDF (`callup_parser.py`)

Función `extract_callup_players_from_pdf(pdf_bytes: bytes) -> tuple[str, list[dict]]`:
1. Carga `pypdf.PdfReader(io.BytesIO(pdf_bytes))`.
2. Itera páginas usando `page.extract_text(extraction_mode="layout")`.
3. Detecta inicio de sección de convocados por cabeceras (`CLUB`, `LLINATGES`, `NOM`, `ANY`, `JUGADORES CONVOCADES`).
4. Parsea líneas tabulares identificando columnas:
   - Número opcional al inicio (`\d+`).
   - Club: texto hasta espacio amplio (`\s{2,}`).
   - Apellidos (Llinatges): texto hasta siguiente separación amplia.
   - Nombre (Nom): texto hasta fin de línea o año de 4 dígitos.
   - Año: 4 dígitos numéricos (`19\d{2}|20\d{2}`).
5. Devuelve `(raw_text_completo, lista_jugadores_dict)`.

---

### 3.4. Algoritmo de Cruce Antroponímico (`callup_matcher.py`)

Función `match_callup_player(player_data: dict, season: Season) -> dict`:
1. **Club Matching**:
   - Normaliza `raw_club`: minúsculas, sin acentos, eliminando prefijos (`cv`, `c v`, `club voleibol`, `vc`, `vòlei`).
   - Compara contra todas las `Organization` activas en la BD:
     - `org.club.name`
     - `org.name`
     - Diccionario `org.club_team_names`
   - Si la raíz de tokens coincide o `SequenceMatcher >= 0.80`, `club_matched = True` para esa organización.
2. **Player Matching** (para organizaciones candidatas):
   - Consulta `Person` de esa organización con rol activo en la temporada:
     `Person.objects.filter(organization=org, player_roles__season=season, player_roles__is_active=True).distinct()`
   - **First name score**:
     - Si el primer token del nombre en PDF es idéntico al primer token de la ficha (`Lluc` == `Lluc` en `Lluc Aleix`), score = 1.0.
     - Si los tokens de nombre son subconjunto uno de otro, score = 1.0.
     - En otro caso, similitud difusa `SequenceMatcher(raw_first, db_first).ratio()`.
   - **Last name score**:
     - Si todos los apellidos coinciden, score = 1.0.
     - Si el PDF aporta un único apellido y coincide exactamente con el primer apellido de la ficha (`Riera` == `Riera` en `Riera Martín`), score = 0.95.
     - En otro caso, similitud difusa sobre apellidos.
   - **Validación del Año**:
     - Si `raw_birth_year` y `person.birth_date.year` coinciden: bono determinante de confirmación.
     - Si difieren en más de 1 año (estando ambos presentes): penalización de 0.30.
   - **Score ponderado**: `(first_score * 0.40) + (last_score * 0.60)`.
3. **Clasificación**:
   - `club_matched = True` y `score >= 0.85` -> `confirmed`.
   - `club_matched = True` y `score >= 0.70` (o `score >= 0.65` con año coincidente) -> `confirmed` si año coincide, `suspected` si año no coincide o está ausente.
   - `club_matched = False` pero `score >= 0.95` y año coincide -> `suspected` (posible cesión o filial).
   - Resto -> `unmatched`.

---

### 3.5. Notificaciones y Tareas

#### Servicio de Notificaciones (`ilovevoley/competitions/services/notifications.py`)
- `notify_callup_confirmed(callup_player: CallUpPlayer) -> bool`:
  - Envía Web Push a través de `notify_web_push_organization_task`.
  - `notification_type='callup_confirmed'`
  - Categorías asociadas: categorías de los equipos del jugador en esa temporada.
- `notify_callup_suspected(callup_player: CallUpPlayer) -> bool`:
  - Envía Web Push / alerta con `notification_type='admin_alert'` exclusivamente a usuarios con membresía `manager` o `admin` en la organización.
  - Incluye enlace a `/core/moderacion/#convocatorias` (accesible para managers sin permisos de Django Admin).

#### Tarea Celery (`ilovevoley/competitions/tasks.py`)
```python
@shared_task(name='scrape_balearic_callups')
def scrape_balearic_callups_task(season_id=None, force=False):
    """Descarga y procesa convocatorias federativas de la selección balear."""
    ...
```

#### Management Command (`scrape_balearic_callups`)
```bash
python manage.py scrape_balearic_callups [--season 2025-26] [--temp 2526] [--dry-run] [--force] [--no-notify]
```

---

### 3.6. Panel de Moderación Descentralizada (`/core/moderacion/`) y Django Admin

#### Panel de Moderación para Managers del Club (`/core/moderacion/`)
Dado que los usuarios con rol `manager` no tienen permisos en el Django Admin / Unfold, se habilita una sección específica en el panel de moderación descentralizada del tenant:
- **Consulta**: `CallUpPlayer.objects.filter(organization=tenant, match_status='suspected').select_related('callup', 'person')`.
- **Contador en API**: Se añade `pending_callups` en `moderation_counts_api` y se suma al `total_pending`.
- **Interfaz en `core/moderation_panel.html`**:
  - Tarjeta resumen de convocatorias pendientes.
  - Bloque `#convocatorias` con tarjetas para cada jugador detectado:
    - Nombre y club según PDF oficial.
    - Ficha de jugador sugerida (`Person.full_name`, foto, edad).
    - Metadatos de la convocatoria (fecha, título, categoría, modalidad).
    - Nota de por qué es sospechoso (ej. "Club coincide, nombre parcial").
    - **Botón "Confirmar convocatoria"**: Envía POST a `/core/api/callups/<id>/confirm/`. Marca `match_status='confirmed'`, asigna `reviewed_by=request.user`, `reviewed_at=now()` y despacha la notificación Web Push a los socios del club.
    - **Botón "Descartar"**: Envía POST a `/core/api/callups/<id>/reject/`. Marca `match_status='rejected'`, asigna `reviewed_by=request.user` y `reviewed_at=now()`.

#### Django Admin Unfold (`/admin/competitions/callupplayer/`)
Para superusuarios y administradores globales de la plataforma:
- `FederationCallUpAdmin` con visualización de circulares, PDFs y tabla inline de convocados.
- `CallUpPlayerAdmin` con filtros avanzados, búsqueda y acciones masivas `confirm_matches`, `reject_matches` y `re_evaluate_matches`.

---

## 4. Plan de Pruebas (Testing)

Siguiendo la guía de testing de `GEMINI.md`:
1. **`test_callup_parser.py`**:
   - Prueba de normalización de títulos: `VP INF MASC`, `VP CAD FEM`, `CONVOCATORIA 23-30 IF`, `SUB19 FEM`, `SENIOR MASC`.
   - Prueba de extracción de PDF con layouts reales (espaciados amplios, una y múltiples convocatorias por documento, omisión de año).
2. **`test_callup_matcher.py`**:
   - Caso real de nombre compuesto: `LLUC` + `RIERA MARTÍN` vs `Lluc Aleix Riera Martín` -> `confirmed`.
   - Caso de apellido único: `LLUC` + `RIERA` vs `Lluc Aleix Riera Martín` con año 2013 -> `confirmed`.
   - Caso con errata tipográfica menor: `LLUCH` + `RIERA MARTI` con año 2013 -> `confirmed`.
   - Caso de club con prefijos: `CV SANT JOSEP` vs `Sant Josep Obrer` -> `club_matched = True`.
   - Caso de homónimo en otro club -> `unmatched` o `suspected` según score y año.
   - Caso de jugador de otro club sin relación -> `unmatched`.
3. **`test_callup_notifications.py`**:
   - Comprueba que un `confirmed` encola el Web Push con los parámetros correctos.
   - Comprueba que un `suspected` alerta solo a managers/admins.
   - Comprueba idempotencia (`notification_sent = True` no duplica envíos).
4. **`test_scrape_balearic_callups_command.py`**:
   - Mock del endpoint HTTP federativo y descarga de PDF.
   - Comprueba ejecución con `--dry-run` (no modifica BD).
   - Comprueba persistencia con ejecución normal e idempotencia ante ejecuciones sucesivas.
