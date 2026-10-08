# Competiciones de vóley playa y auto-descubrimiento estacional

**Fecha:** 2026-10-08  
**Estado:** Propuesto para revisión  
**Issue:** [#372](https://github.com/trencaclosqu3s/ilovevoley/issues/372)  
**Apps afectadas:** `ilovevoley.competitions`, `ilovevoley.videos.scraping`

---

## 1. Contexto y motivación

El vóley playa en Baleares tiene una dinámica marcadamente estacional (concentrada en mayo-agosto) y actualmente la federación (`voleibolib.net`) no mantiene una competición estructurada continua durante el invierno.

En la verificación técnica contra los endpoints federativos se ha constatado:
1. **Histórico estructurado disponible:** En la temporada 2024-25 existen 11 competiciones infantiles de vóley playa (3 masculinas y 8 femeninas, sumando 70 partidos disputados en junio de 2025).
2. **Tablas de clasificación vacías:** Los endpoints de clasificación (`get_clasificacion.asp?id=...`) en playa devuelven tablas HTML sin filas de equipos, lo que provocaba que el servicio de descubrimiento de ligas existente descartara estas competiciones por no encontrar equipos. En cambio, los endpoints de calendario (`get_calendario.asp?id=...`) y resultados sí contienen todos los equipos participantes (incluyendo clubes de tenants como `CV SANT JOSEP`).
3. **Ausencia de soporte de modalidad en ligas:** Aunque `FederationCallUp` soporta `modality` (`indoor`/`beach`), `League` y `LeagueCandidate` carecen de dicho campo y todo el scraping asumía vóley pista.
4. **Requisito de visibilidad admin-only:** Dado el estado incipiente y la incertidumbre de publicación federativa año a año, el sistema debe estar preparado para descubrir y gestionar competiciones de playa pero manteniéndolas **exclusivamente visibles en el admin de Django** (`visibility_type='reference'` o `'historical'`), sin exponerlas en las vistas públicas de los tenants hasta que el producto decida abrirlas.

---

## 2. Decisiones de arquitectura

1. **Modalidad explícita (`indoor` vs `beach`):**
   Incorporar `modality` en `League` y `LeagueCandidate` con valores estándar `indoor` (Vóley Pista) y `beach` (Vóley Playa), manteniendo `default='indoor'` para compatibilidad retroactiva total.
2. **Visibilidad conservadora (Admin-only):**
   Al aprobar candidatas con `modality == 'beach'`, se asigna automáticamente `visibility_type='reference'` si es activa o `'historical'` si es de temporadas pasadas. Ambas garantizan que `should_show_in_app` sea `False`, impidiendo que aparezcan en los menús o páginas públicas del tenant.
3. **Fallback resiliente de extracción de equipos:**
   Si la clasificación no devuelve filas (comportamiento habitual en torneos de playa y fases concentradas de un solo día), `fetch_team_names` consulta el calendario (`get_calendario.asp?id=...`) para extraer los nombres de los equipos y permitir el emparejamiento con tenants (`matching_tenants`).
4. **Auto-descubrimiento estacional de verano:**
   Nueva función `discover_seasonal_beach` que consulta el endpoint de desglose de partidos por fechas (`get_partidos_desglose_competiciones.asp?op=2&fini=...&ffin=...`) para la ventana de verano de la temporada (01/06 al 31/08), detectando torneos de playa y registrándolos en la cola unificada de `LeagueCandidate`.
5. **Formato de partido específico:**
   Las ligas de playa aprobadas se configuran con `match_format='tournament_3sets'` (3 sets máximo, ganar 2) de forma predeterminada.

---

## 3. Modelo de datos

### 3.1. `League` (`ilovevoley.competitions.models.competitions`)

- Nuevas constantes:
  ```python
  MODALITY_BEACH = 'beach'
  MODALITY_INDOOR = 'indoor'
  MODALITY_CHOICES = [
      (MODALITY_BEACH, _('Vóley Playa')),
      (MODALITY_INDOOR, _('Vóley Pista')),
  ]
  ```
- Nuevo campo:
  ```python
  modality = models.CharField(
      max_length=20,
      choices=MODALITY_CHOICES,
      default=MODALITY_INDOOR,
      db_index=True,
      verbose_name=_('Modalidad'),
      help_text=_('Modalidad de la competición: pista o playa'),
  )
  ```

### 3.2. `LeagueCandidate` (`ilovevoley.competitions.models.competitions`)

- Nuevo campo:
  ```python
  modality = models.CharField(
      max_length=20,
      choices=League.MODALITY_CHOICES,
      default=League.MODALITY_INDOOR,
      db_index=True,
      verbose_name=_('Modalidad'),
  )
  ```
- Método `approve()`:
  - Propaga `modality=self.modality`.
  - Si `self.modality == League.MODALITY_BEACH`:
    - `visibility_type = 'historical' if self.is_historical else 'reference'`
    - `match_format = 'tournament_3sets'`
  - Si `self.modality == League.MODALITY_INDOOR`:
    - `visibility_type = 'historical' if self.is_historical else 'main'`
    - `match_format = 'standard'`

---

## 4. Servicio de descubrimiento (`ilovevoley.competitions.services.discovery`)

### 4.1. Detección de modalidad
- Función `detect_modality(section='', category_label='', phase_label='') -> str`:
  - Devuelve `'beach'` si la sección normalizada contiene `'voleyplaya'` o si alguna etiqueta incluye los términos `'playa'` o `'platja'`.
  - En cualquier otro caso devuelve `'indoor'`.

### 4.2. Fallback de nombres de equipo desde el calendario
- `fetch_team_names_from_calendar(federation_id, session=requests) -> list[str]`:
  - Lee `JSON/get_calendario.asp?id={federation_id}`.
  - Extrae los nombres de los equipos de las filas de partidos (`<table class='calendario-completo'>...<tr><td>...</td><td>...</td><td><strong>...</strong></td>`).
  - Limpia espacios, decodifica entidades HTML y excluye términos no válidos como `'descansa'`.
- `fetch_team_names(federation_id, session=requests)`:
  - Intenta primero desde `get_clasificacion.asp`.
  - Si no hay filas de clasificación, recurre a `fetch_team_names_from_calendar`.

### 4.3. Descubrimiento estacional (`discover_seasonal_beach`)
- Firma: `discover_seasonal_beach(season, fini=None, ffin=None, session=requests) -> list[LeagueCandidate]`
- Lógica:
  - Ventana temporal por defecto: `fini = 01/06/{season.end_year}`, `ffin = 31/08/{season.end_year}`.
  - Petición a `JSON/get_partidos_desglose_competiciones.asp?op=2&fini={fini}&ffin={ffin}`.
  - Itera categorías filtrando aquellas con modalidad playa (`detect_modality`).
  - Por cada fase/grupo:
    - Extrae equipos de los partidos (`ELOCAL`, `EVISITANTE`).
    - Si el `federation_id` ya existe en `League` o `LeagueCandidate`, se omite (idempotencia).
    - Cruza con `matching_tenants(teams, organizations)`.
    - Si casa con algún tenant: crea `LeagueCandidate(modality='beach', section='VOLEYPLAYA', status='pending', is_historical=(season != Season.objects.current()), ...)`.
    - Si no casa con ningún tenant: registra `LeagueCandidate(status='rejected', ...)`.

---

## 5. Panel de administración y tareas Celery / Comandos

### 5.1. Django Admin (`ilovevoley/competitions/admin/competitions.py`)
- `LeagueAdmin`:
  - Añadir `'modality'` a `list_display` y `list_filter`.
- `LeagueCandidateAdmin`:
  - Añadir `'modality'` a `list_display` y `list_filter`.
  - Nueva acción de cabecera / botón `discover_beach_now` (permiso superuser) que lanza la búsqueda estacional de playa.

### 5.2. Comando management `discover_leagues`
- Añadir opciones:
  - `--seasonal` / `--beach`: ejecuta el descubrimiento estacional de playa para la temporada indicada.
  - `--date-range <fini> <ffin>`: rango opcional personalizado en formato DD/MM/YYYY.

### 5.3. Tarea periódica / Celery
- Nueva tarea `@shared_task(name='discover_seasonal_beach_leagues')` en `competitions.tasks` para permitir ejecuciones en segundo plano desde el admin.

---

## 6. Ingesta histórica (Temporada 2024-25)

En `ilovevoley/videos/management/commands/scrape_historical_leagues.py`:
- Incorporar las 11 competiciones infantiles verificadas de 2024-25:
  - Masculino: `7932` (Grup A), `7933` (Grup B), `7934` (Grup C).
  - Femenino: `7924` (Grup A) a `7931` (Grup H).
- Configuradas con `modality='beach'`, `match_format='tournament_3sets'`, `visibility_type='historical'`.

---

## 7. Estrategia de testing (según `docs/ai-guidelines/testing-guidelines.md`)

Todos los tests propuestos protegen decisiones propias del producto y casos límite reales:

| Test | Justificación técnica |
| --- | --- |
| `test_detect_modality` | Verifica la normalización de datos no trivial que distingue pista de playa según secciones (`VOLEYPLAYA`) y etiquetas multilingües (`playa`/`platja`). |
| `test_fetch_team_names_calendar_fallback` | Cubre el caso límite verificado en producción donde la federación devuelve clasificaciones con 0 filas pero calendario completo. |
| `test_discover_seasonal_beach` | Protege el flujo con efectos persistentes de ingesta estacional por JSON de fechas e idempotencia. |
| `test_league_candidate_approve_beach_admin_only` | Protege la regla de negocio crítica: las ligas de playa aprobadas quedan en `visibility_type='reference'` / `'historical'` y nunca en `'main'`. |
