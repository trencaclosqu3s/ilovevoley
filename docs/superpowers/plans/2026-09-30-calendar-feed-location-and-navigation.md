# Dirección y Ruta Navegable en Feed de Calendario Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implementar el soporte para que los eventos de partidos en el feed iCal (`.ics`) incluyan la dirección completa normalizada (`venue`, `field_address`, `city`) y enlace directo de navegación en la descripción, permitiendo a los clientes de calendario móvil (iOS Calendar / Apple Maps, Google Calendar y Outlook) resolver la ubicación geográfica nativa, calcular tiempos de desplazamiento ("Hora de salir") y ofrecer rutas de navegación en un clic.

**Architecture:**
- El estándar iCalendar (RFC 5545 §3.8.1.7) define `LOCATION` como texto descriptivo. Los clientes móviles (iOS mediante CoreLocation / Apple Maps, Android / Google Calendar mediante Google Maps) realizan geocodificación nativa sobre este campo si contiene la dirección postal completa.
- `GEO:lat;lon` y `X-APPLE-STRUCTURED-LOCATION` exigen coordenadas numéricas que actualmente no se almacenan en el modelo `Match`, y su geocodificación en tiempo de ejecución del feed añadiría latencias y rate-limits inasumibles. Además, `LOCATION` completo cubre el 100% de la experiencia de usuario (mapa integrado, alertas de salida y ruta) sin necesidad de lat/lon.
- Se implementa una función de utilidad de formateo y normalización para ubicación y enlace de mapas (`format_match_location`, `get_match_maps_url`), integrándola en `UserMatchesFeed.item_location` y `item_description`.

**Tech Stack:** Django 6.0.8, django-ical 1.9.2, icalendar, Pytest.

**Issue:** [#263](https://github.com/trencaclosqu3s/ilovevoley/issues/263)

---

## Global Constraints

- Django version fijada en 6.0.8.
- App de dominio: `competitions`.
- Tests ejecutados con `pytest --create-db`.
- Código en inglés (funciones, parámetros, tests); comentarios, docs y plantillas en castellano.
- Git: no realizar commits ni push sin confirmación previa del usuario con imputación de tiempo y número de issue (#263).

---

### Task 1: Helpers de Formateo y Normalización de Ubicación

**Files:**
- Modify: `ilovevoley/competitions/calendar_feed.py`
- Test: `ilovevoley/competitions/tests/test_calendar_feed.py` (o `test_views.py`)

**Interfaces:**
- Produces:
  - `format_match_location(match: Match) -> str`
  - `get_match_maps_url(match: Match) -> str | None`

- [ ] **Step 1: Escribir tests unitarios para `format_match_location` y `get_match_maps_url`**

Casos de prueba a cubrir:
1. `Match` con `venue`, `field_address` y `city`: genera `"Poliesportiu Germans Escalas, C/ Son Gibert s/n, Palma"`.
2. `Match` con `venue` y `city` (sin `field_address`): genera `"Poliesportiu Germans Escalas, Palma"`.
3. `Match` con `field_address` y `city` (sin `venue`): genera `"C/ Son Gibert s/n, Palma"`.
4. `Match` con solo `venue`: genera `"Poliesportiu Germans Escalas"`.
5. `Match` sin ningún dato de ubicación: retorna `'Por confirmar'`.
6. Limpieza de duplicidades/redundancias: si `field_address` ya contiene el nombre de `city` o `venue` al final/inicio, evitar repeticiones innecesarias (ej. `"Calle Mayor 1, Palma"` y ciudad `"Palma"`).
7. `get_match_maps_url`: genera URL válida de Google Maps search (`https://www.google.com/maps/search/?api=1&query=...`) con parámetros codificados; retorna `None` si la ubicación es vacía o `'Por confirmar'`.

- [ ] **Step 2: Ejecutar los tests para comprobar que fallan**

```bash
docker compose -f docker-compose.dev.yml run --rm web python -m pytest ilovevoley/competitions/tests/test_views.py -k test_format_match_location --tb=short
```

- [ ] **Step 3: Implementar `format_match_location` y `get_match_maps_url`**

Implementar funciones puras y reutilizables en `ilovevoley/competitions/calendar_feed.py` (o módulo helper correspondiente):
- Limpieza de espacios en blanco en cada componente.
- Deduplicación sensible al caso si un componente está contenido íntegramente en otro adyacente.
- Ensamblado con comas y espacios.
- Retorno de fallback `'Por confirmar'`.
- Construcción de URL con `urllib.parse.quote_plus`.

- [ ] **Step 4: Ejecutar tests y comprobar que pasan**

```bash
docker compose -f docker-compose.dev.yml run --rm web python -m pytest ilovevoley/competitions/tests/test_views.py -k test_format_match_location --tb=short
```

---

### Task 2: Integración en `UserMatchesFeed` (`LOCATION` y `DESCRIPTION`)

**Files:**
- Modify: `ilovevoley/competitions/calendar_feed.py`
- Test: `ilovevoley/competitions/tests/test_views.py`

**Interfaces:**
- Updates:
  - `UserMatchesFeed.item_location(self, item)`
  - `UserMatchesFeed.item_description(self, item)`

- [ ] **Step 1: Escribir tests para el feed iCal (.ics)**

Verificar:
1. Que el feed renderizado incluya la propiedad `LOCATION:` con la dirección completa (`venue, field_address, city`).
2. Que la propiedad `DESCRIPTION:` incluya el bloque de ubicación legible y el enlace `"Cómo llegar: https://www.google.com/maps/search/?api=1&query=..."` cuando haya ubicación disponible.
3. Que no rompa partidos cancelados, provisionales o amistosos.

- [ ] **Step 2: Ejecutar los tests para comprobar que fallan**

```bash
docker compose -f docker-compose.dev.yml run --rm web python -m pytest ilovevoley/competitions/tests/test_views.py -k test_calendar_feed_location --tb=short
```

- [ ] **Step 3: Actualizar métodos en `UserMatchesFeed`**

En `ilovevoley/competitions/calendar_feed.py`:
- Actualizar `item_location` para delegar en `format_match_location(item)`.
- En `item_description`: añadir bloque con información de ubicación y enlace de mapas si hay datos disponibles.

- [ ] **Step 4: Ejecutar la suite completa de tests de calendario con `--create-db`**

```bash
docker compose -f docker-compose.dev.yml run --rm web python -m pytest --create-db ilovevoley/competitions/tests/test_views.py -k test_calendar --tb=short
```

---

### Task 3: Verificación y Documentación de Criterios

- [ ] **Step 1: Ejecutar suite de pruebas completa de la app `competitions`**

```bash
docker compose -f docker-compose.dev.yml run --rm web python -m pytest ilovevoley/competitions/tests/ --tb=short
```

- [ ] **Step 2: Documentar resolución de los 4 criterios de aceptación de la issue #263**
- Responder detalladamente en el cierre del issue sobre RFC 5545, campos analizados, evaluación de geocodificación y validación en clientes móviles.
