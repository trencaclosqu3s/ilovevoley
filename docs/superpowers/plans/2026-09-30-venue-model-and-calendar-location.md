# Catálogo de Pabellones (`Venue`) y Ubicación Navegable en Feed de Calendario Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implementar el modelo canónico `Venue` en `competitions`, relacionarlo con `Club.default_venue` y `Match.venue_ref`, precargar el catálogo balear (~35 pabellones) mediante migración `RunPython`, e integrarlo en `UserMatchesFeed` para que el feed iCal (.ics) emita la dirección física estructurada en `LOCATION` y el enlace de navegación directa a Google Maps en `DESCRIPTION`.

**Architecture:**
- Se crea el modelo `Venue` en `competitions` para centralizar nombres oficiales, direcciones, municipios, enlaces directos de Google Maps y alias/variantes de la federación.
- Se añade la FK opcional `Match.venue_ref` en `Match` (preservando los campos de texto `venue`, `field_address`, `city` para scraping e histórico) y la FK opcional `Club.default_venue` en `Club`.
- Se crea el servicio `venue_service.py` con `get_match_location_info(match)` que implementa la resolución en orden estricto de prioridades (1: `venue_ref` asignado; 2: texto de `match.venue` coincidente con `Venue`; 3: fallback a `match.home_team.club.default_venue`; 4: texto plano de `Match`).
- Se precarga el catálogo mediante una migración de datos con `RunPython` (cumpliendo la regla del proyecto) que inserta los pabellones base, vincula los clubes existentes y ejecuta un backfill sobre los partidos en base de datos.
- Se actualiza `UserMatchesFeed` (`calendar_feed.py`) para emitir la dirección completa en `LOCATION` y el enlace directo en `DESCRIPTION`.

**Tech Stack:** Django 6.0.8, django-ical 1.9.2, icalendar, PostgreSQL, Pytest.

**Spec:** [`docs/superpowers/specs/2026-09-30-venue-model-and-calendar-location-design.md`](file:///Users/jamartinmari/orca/workspaces/videosvoley/task-direcci-n-y-ruta-navegable-en-feed-de-calen/docs/superpowers/specs/2026-09-30-venue-model-and-calendar-location-design.md)

---

## Global Constraints

- Django versión fijada en 6.0.8.
- Apps de dominio: `competitions` y `teams`.
- Tests ejecutados con `docker compose -f docker-compose.dev.yml run --rm web python -m pytest --create-db`.
- Código en inglés (modelos, campos, funciones, tests); comunicación, docs y admin en castellano.
- Git: No realizar commit ni push sin petición explícita del usuario. Preguntar siempre por imputación de tiempo (`@time 1h` propuesto) y referenciar issue `#263`.
- Backfills de datos: migración vacía con `RunPython`, nunca management commands sueltos.
- No editar migraciones existentes: generar nuevas con `makemigrations` y avisar para revisión.

---

### Task 1: Modelo `Venue` en `competitions` y FK `Match.venue_ref`

**Files:**
- Modify: `ilovevoley/competitions/models/competitions.py`
- Modify: `ilovevoley/competitions/models/__init__.py`
- Modify: `ilovevoley/competitions/admin/competitions.py`
- Test: `ilovevoley/competitions/tests/test_models.py`

**Interfaces:**
- Produces:
  - `Venue(name, short_name, address, city, postal_code, google_maps_url, aliases, latitude, longitude, is_active)`
  - `Venue.full_address -> str`
  - `Venue.maps_url -> str | None`
  - `Venue.matches_text(text: str) -> bool`
  - `Match.venue_ref -> ForeignKey(Venue, null=True, blank=True)`

- [ ] **Step 1: Escribir tests unitarios para `Venue` y `Match.venue_ref`**

En `ilovevoley/competitions/tests/test_models.py`, añadir la clase `VenueModelTest`:
```python
from ilovevoley.competitions.models import Venue, Match

class VenueModelTest(TestCase):
    def test_venue_creation_and_str(self):
        venue = Venue.objects.create(
            name="Pavelló Joan Pericás Riera",
            city="Bunyola",
            address="Son Serra s/n",
            google_maps_url="https://maps.app.goo.gl/sample123",
            aliases="Pav. Juan Pericas Riera, Pav. Bunyola"
        )
        self.assertEqual(str(venue), "Pavelló Joan Pericás Riera (Bunyola)")
        self.assertEqual(venue.full_address, "Pavelló Joan Pericás Riera, Son Serra s/n, Bunyola")
        self.assertEqual(venue.maps_url, "https://maps.app.goo.gl/sample123")

    def test_venue_full_address_avoids_duplicate_fragments(self):
        venue = Venue.objects.create(
            name="Poliesportiu Germans Escalas",
            address="Germans Escalas, Mare de Deu de Monserrat 66",
            city="Palma"
        )
        # No debe duplicar "Germans Escalas"
        self.assertIn("Mare de Deu de Monserrat 66", venue.full_address)
        self.assertEqual(venue.full_address.count("Germans Escalas"), 1)

    def test_venue_maps_url_fallback_when_empty(self):
        venue = Venue.objects.create(
            name="Pavelló Municipal Alaró",
            city="Alaró"
        )
        self.assertIn("https://www.google.com/maps/search/?api=1&query=", venue.maps_url)
        self.assertIn("Alar%C3%B3", venue.maps_url)

    def test_venue_matches_text(self):
        venue = Venue.objects.create(
            name="Pav. Son Angelats",
            city="Sóller",
            aliases="Poliesportiu Son Angelats, Pavelló Sóller"
        )
        self.assertTrue(venue.matches_text("Pav. Son Angelats"))
        self.assertTrue(venue.matches_text("Poliesportiu Son Angelats"))
        self.assertTrue(venue.matches_text("pav. son angelats"))
        self.assertFalse(venue.matches_text("Pav. Germans Escalas"))

    def test_match_venue_ref_relation(self):
        venue = Venue.objects.create(name="Pabellón Central", city="Palma")
        match = Match.objects.create(
            match_date=timezone.now(),
            venue_ref=venue,
            home_team_text="Local",
            away_team_text="Visitante"
        )
        self.assertEqual(match.venue_ref, venue)
        self.assertIn(match, venue.matches.all())
```

- [ ] **Step 2: Ejecutar los tests para comprobar que fallan**

```bash
DEV_DB_PORT=5546 DEV_REDIS_PORT=6481 docker compose -f docker-compose.dev.yml run --rm web python -m pytest ilovevoley/competitions/tests/test_models.py -k test_venue --tb=short
```
*Resultado esperado: ImportError o AttributeError (Venue no definido).*

- [ ] **Step 3: Implementar `Venue` y campo `venue_ref` en `competitions`**

1. En `ilovevoley/competitions/models/competitions.py`:
   - Definir `class Venue(models.Model)` con campos `name`, `short_name`, `address`, `city`, `postal_code`, `google_maps_url`, `aliases`, `latitude`, `longitude`, `is_active`, timestamps, `@property full_address`, `@property maps_url` y `matches_text()`.
   - En `class Match(models.Model)`, añadir `venue_ref = models.ForeignKey(Venue, on_delete=models.SET_NULL, null=True, blank=True, related_name='matches', verbose_name='Pabellón')`.
2. En `ilovevoley/competitions/models/__init__.py`:
   - Añadir `Venue` a los imports y `__all__`.
3. En `ilovevoley/competitions/admin/competitions.py`:
   - Registrar `VenueAdmin` (con Unfold si aplica) con `list_display = ('name', 'city', 'address', 'google_maps_url', 'is_active')`, `search_fields = ('name', 'city', 'aliases', 'address')`, `list_filter = ('city', 'is_active')`.
   - Añadir `venue_ref` al `fieldsets` y `autocomplete_fields` de `MatchAdmin`.
4. Generar migración:
```bash
DEV_DB_PORT=5546 DEV_REDIS_PORT=6481 docker compose -f docker-compose.dev.yml run --rm web python manage.py makemigrations competitions
```

- [ ] **Step 4: Ejecutar tests y comprobar que pasan**

```bash
DEV_DB_PORT=5546 DEV_REDIS_PORT=6481 docker compose -f docker-compose.dev.yml run --rm web python -m pytest --create-db ilovevoley/competitions/tests/test_models.py -k test_venue --tb=short
```

---

### Task 2: Relación `Club.default_venue` en `teams`

**Files:**
- Modify: `ilovevoley/teams/models/teams.py`
- Modify: `ilovevoley/teams/admin.py`
- Test: `ilovevoley/teams/tests/test_models.py`

**Interfaces:**
- Produces: `Club.default_venue -> ForeignKey('competitions.Venue', null=True, blank=True)`

- [ ] **Step 1: Escribir failing test para `Club.default_venue`**

En `ilovevoley/teams/tests/test_models.py`:
```python
def test_club_default_venue_relation(self):
    from ilovevoley.competitions.models import Venue
    venue = Venue.objects.create(name="Pavelló Blanquerna", city="Marratxí")
    club = Club.objects.create(
        federation_id="999",
        official_name="Club Voleibol Pòrtol",
        default_venue=venue
    )
    self.assertEqual(club.default_venue, venue)
    self.assertIn(club, venue.clubs.all())
```

- [ ] **Step 2: Ejecutar test para verificar fallo**

```bash
DEV_DB_PORT=5546 DEV_REDIS_PORT=6481 docker compose -f docker-compose.dev.yml run --rm web python -m pytest ilovevoley/teams/tests/test_models.py -k test_club_default_venue --tb=short
```

- [ ] **Step 3: Implementar `default_venue` en `Club` y generar migración**

1. En `ilovevoley/teams/models/teams.py`:
   ```python
   default_venue = models.ForeignKey(
       'competitions.Venue',
       on_delete=models.SET_NULL,
       null=True,
       blank=True,
       related_name='clubs',
       verbose_name='Pabellón habitual'
   )
   ```
2. En `ilovevoley/teams/admin.py`:
   - Añadir `default_venue` a `ClubAdmin` (en `fields` / `autocomplete_fields`).
3. Generar migración de `teams`:
```bash
DEV_DB_PORT=5546 DEV_REDIS_PORT=6481 docker compose -f docker-compose.dev.yml run --rm web python manage.py makemigrations teams
```

- [ ] **Step 4: Ejecutar tests y verificar que pasan**

```bash
DEV_DB_PORT=5546 DEV_REDIS_PORT=6481 docker compose -f docker-compose.dev.yml run --rm web python -m pytest --create-db ilovevoley/teams/tests/test_models.py -k test_club_default_venue --tb=short
```

---

### Task 3: Servicio de Resolución de Sedes (`venue_service.py`)

**Files:**
- Create: `ilovevoley/competitions/services/venue_service.py`
- Modify: `ilovevoley/competitions/services/__init__.py`
- Test: `ilovevoley/competitions/tests/test_venue_service.py`

**Interfaces:**
- Produces: `get_match_location_info(match: Match) -> dict`
  - Retorna `{'venue': Venue | None, 'location_text': str, 'maps_url': str | None, 'is_inferred': bool}`

- [ ] **Step 1: Escribir tests unitarios exhaustivos para la resolución**

Crear `ilovevoley/competitions/tests/test_venue_service.py`:
```python
from django.test import TestCase
from django.utils import timezone
from ilovevoley.competitions.models import Venue, Match
from ilovevoley.teams.models import Club, Team
from ilovevoley.competitions.services.venue_service import get_match_location_info

class VenueServiceTest(TestCase):
    def setUp(self):
        self.venue_soller = Venue.objects.create(
            name="Pav. Son Angelats",
            address="Carretera a Deià, s/n",
            city="Sóller",
            google_maps_url="https://maps.app.goo.gl/soller",
            aliases="Poliesportiu Son Angelats"
        )
        self.venue_mayurqa = Venue.objects.create(
            name="Pav. Col. Sta. Magdalena Sofia",
            address="Carrer de Francesc Martí i Móra, 42",
            city="Palma",
            google_maps_url="https://maps.app.goo.gl/mayurqa"
        )
        self.club_mayurqa = Club.objects.create(
            federation_id="100",
            official_name="CV Mayurqa",
            default_venue=self.venue_mayurqa
        )
        self.team_mayurqa = Team.objects.create(
            federation_id="100-1",
            name="Voley Palma Mayurqa",
            club=self.club_mayurqa
        )

    def test_priority_1_direct_venue_ref(self):
        match = Match.objects.create(
            match_date=timezone.now(),
            venue_ref=self.venue_soller,
            home_team=self.team_mayurqa
        )
        info = get_match_location_info(match)
        self.assertEqual(info['venue'], self.venue_soller)
        self.assertEqual(info['location_text'], self.venue_soller.full_address)
        self.assertEqual(info['maps_url'], "https://maps.app.goo.gl/soller")
        self.assertFalse(info['is_inferred'])

    def test_priority_2_match_venue_text_overrides_home_club_default(self):
        # Caso real: Mayurqa juega de local pero en Sóller (Son Angelats)
        match = Match.objects.create(
            match_date=timezone.now(),
            venue="Pav. Son Angelats",
            home_team=self.team_mayurqa
        )
        info = get_match_location_info(match)
        self.assertEqual(info['venue'], self.venue_soller)
        self.assertEqual(info['location_text'], self.venue_soller.full_address)
        self.assertEqual(info['maps_url'], "https://maps.app.goo.gl/soller")
        self.assertFalse(info['is_inferred'])

    def test_priority_3_fallback_to_home_club_default_when_venue_empty(self):
        # Partido sin datos de pista en federación
        match = Match.objects.create(
            match_date=timezone.now(),
            venue="",
            city="",
            home_team=self.team_mayurqa
        )
        info = get_match_location_info(match)
        self.assertEqual(info['venue'], self.venue_mayurqa)
        self.assertEqual(info['location_text'], self.venue_mayurqa.full_address)
        self.assertEqual(info['maps_url'], "https://maps.app.goo.gl/mayurqa")
        self.assertTrue(info['is_inferred'])

    def test_priority_4_fallback_to_match_raw_text(self):
        # Partido en pabellón no registrado en Venue
        match = Match.objects.create(
            match_date=timezone.now(),
            venue="Polideportivo Desconocido",
            field_address="Calle Mayor 1",
            city="Inca"
        )
        info = get_match_location_info(match)
        self.assertIsNone(info['venue'])
        self.assertEqual(info['location_text'], "Polideportivo Desconocido, Calle Mayor 1, Inca")
        self.assertIn("https://www.google.com/maps/search/?api=1&query=", info['maps_url'])
        self.assertFalse(info['is_inferred'])

    def test_fallback_when_completely_empty(self):
        match = Match.objects.create(
            match_date=timezone.now(),
            venue="",
            field_address="",
            city=""
        )
        info = get_match_location_info(match)
        self.assertIsNone(info['venue'])
        self.assertEqual(info['location_text'], "Por confirmar")
        self.assertIsNone(info['maps_url'])
```

- [ ] **Step 2: Ejecutar test para verificar fallo**

```bash
DEV_DB_PORT=5546 DEV_REDIS_PORT=6481 docker compose -f docker-compose.dev.yml run --rm web python -m pytest ilovevoley/competitions/tests/test_venue_service.py --tb=short
```

- [ ] **Step 3: Implementar `venue_service.py`**

Crear `ilovevoley/competitions/services/venue_service.py`:
```python
import urllib.parse
from ilovevoley.competitions.models import Venue

def get_match_location_info(match) -> dict:
    # 1. Asignación directa
    if match.venue_ref_id:
        v = match.venue_ref
        return {
            'venue': v,
            'location_text': v.full_address,
            'maps_url': v.maps_url,
            'is_inferred': False,
        }

    # 2. Matching por texto de match.venue
    venue_text = (match.venue or '').strip()
    if venue_text:
        # Búsqueda exacta primero
        venues = list(Venue.objects.filter(is_active=True))
        matched = next((v for v in venues if v.matches_text(venue_text)), None)
        if matched:
            return {
                'venue': matched,
                'location_text': matched.full_address,
                'maps_url': matched.maps_url,
                'is_inferred': False,
            }

    # 3. Fallback por club local
    if match.home_team_id and match.home_team.club_id:
        club = match.home_team.club
        if club.default_venue_id:
            dv = club.default_venue
            return {
                'venue': dv,
                'location_text': dv.full_address,
                'maps_url': dv.maps_url,
                'is_inferred': True,
            }

    # 4. Fallback a texto plano de Match
    parts = []
    if match.venue:
        parts.append(match.venue.strip())
    if match.field_address:
        fa = match.field_address.strip()
        if not match.venue or fa.lower() not in match.venue.lower():
            parts.append(fa)
    if match.city:
        c = match.city.strip()
        if not any(c.lower() in p.lower() for p in parts):
            parts.append(c)

    if parts:
        loc_str = ', '.join(parts)
        q = urllib.parse.quote_plus(loc_str)
        return {
            'venue': None,
            'location_text': loc_str,
            'maps_url': f'https://www.google.com/maps/search/?api=1&query={q}',
            'is_inferred': False,
        }

    return {
        'venue': None,
        'location_text': 'Por confirmar',
        'maps_url': None,
        'is_inferred': False,
    }
```
Reexportar en `ilovevoley/competitions/services/__init__.py`.

- [ ] **Step 4: Ejecutar tests y comprobar que pasan**

```bash
DEV_DB_PORT=5546 DEV_REDIS_PORT=6481 docker compose -f docker-compose.dev.yml run --rm web python -m pytest ilovevoley/competitions/tests/test_venue_service.py --tb=short
```

---

### Task 4: Migración de Datos (`RunPython`) con Catálogo Balear y Backfill

**Files:**
- Create: migración de datos en `competitions`
- Test: `ilovevoley/competitions/tests/test_venue_migration.py`

**Interfaces:**
- Produces: precarga de ~35 pabellones canónicos, vinculación de `Club.default_venue` para clubes existentes y backfill de `Match.venue_ref`.

- [ ] **Step 1: Preparar catálogo canónico de pabellones**

Consolidar los datos recopilados (Mayurqa + BD existente):
- Alaró: `Pav. Municipal d'Alaró` (Aliases: `Poliesportiu Municipal d'Alaró, Pista 1, Pista 2, Pista 3, Pista 4, Pista 5, Pista 6`), maps: `https://maps.app.goo.gl/Z66hZm83iKSNzi3f9`
- Algaida: `Pav. Andreu Trobat`, `Carrer Tanqueta, 14`, Algaida, maps: `https://maps.app.goo.gl/wTQiRiLduquRbF9s7`
- Artà: `Na Caragol`, Artà, maps: `https://maps.app.goo.gl/rNDxacvpHnYcKJgY7`
- Bunyola: `Pav. Joan Pericás Riera`, `Son Serra s/n`, Bunyola, maps: `https://maps.app.goo.gl/G6ZnG2b3tyY3Gjvb6`
- Campos: `Pavelló Municipal de Campos`, `Camí Vell de Ciutat, 0`, Campos, maps: `https://maps.app.goo.gl/T6jG21erGXGw3xDMA`
- Cide: `Pav. Col. Cide`, `C/ Arner, 3 (Son Rapinya)`, Palma, maps: `https://maps.app.goo.gl/wakHoeUHh4BQAG358`
- Esporles: `IES Josep Font i Tries / Pav. Esporles`, `C/ Ca l'Amet, 5`, Esporles, maps: `https://maps.app.goo.gl/fTaNxNZWiwgRjpPh7`
- Germans Escales: `Poliesportiu Germans Escalas`, `Carrer de Son Gibert s/n`, Palma, maps: `https://maps.app.goo.gl/V59GDYSWXNZUYUto9`
- Manacor: `Na Capellera`, `C/ Ronda de l'Institut, 52`, Manacor, maps: `https://maps.app.goo.gl/tec54UgFASEvwykj7`
- Marratxí/Pòrtol: `Pavelló Blanquerna`, `Carrer des Caülls, 1`, Marratxí, maps: `https://maps.app.goo.gl/j2o5nsb5rwEFyEj77`
- Madre Alberta: `Pav. Col. Madre Alberta`, `Camí dels Reis, 102`, Palma, maps: `https://maps.app.goo.gl/YVNo5u8yFVjL31vx8`
- Muro: `Pol. Municipal de Muro`, Muro, maps: `https://maps.app.goo.gl/paTrshtehpKm9DBXA`
- Porto Cristo: `Pav. IES Porto Cristo`, `Carretera Porto Cristo - Son Carrió`, Porto Cristo, maps: `https://maps.app.goo.gl/jRjFjSLA5VGBic4Q8`
- Sant Joan: `Pavelló Son Juny`, Sant Joan
- Sant Josep Obrer: `Pav. Col. Sant Josep Obrer`, `C/ Sebastià Arrom, 3`, Palma, maps: `https://maps.app.goo.gl/tu27jjSavfm7AoT18`
- Sóller: `Pav. Son Angelats`, `Carretera a Deià, s/n`, Sóller, maps: `https://maps.app.goo.gl/YEmNpjuDQWUyx5QT7`
- Son Moix: `Palau Municipal d'Esports Son Moix`, `Camí de la Vileta, 40`, Palma
- UIB: `CampusEsport UIB`, `Carretera de Valldemossa, km 7.5`, Palma, maps: `https://maps.app.goo.gl/hscF6gydw1WhdWF28`
- Valldemossa: `Pav. Municipal Valldemossa`, `C/ Venerable Sor Aina s/n`, Valldemossa

- [ ] **Step 2: Crear migración con `RunPython`**

Crear migración vacía:
```bash
DEV_DB_PORT=5546 DEV_REDIS_PORT=6481 docker compose -f docker-compose.dev.yml run --rm web python manage.py makemigrations competitions --empty -n "seed_venues_and_backfill"
```
En la función `RunPython`:
1. `Venue.objects.get_or_create(...)` para cada pabellón.
2. Asignar `Club.default_venue` para los clubes cuyo nombre o sede coincida.
3. Para cada `Match` sin `venue_ref`: si `match.venue` coincide con los alias de un `Venue`, asignar `match.venue_ref`.

- [ ] **Step 3: Ejecutar migración y comprobar que pasa limpia**

```bash
DEV_DB_PORT=5546 DEV_REDIS_PORT=6481 docker compose -f docker-compose.dev.yml run --rm web python -m pytest --create-db ilovevoley/competitions/tests/test_models.py --tb=short
```

---

### Task 5: Integración en `UserMatchesFeed` (`calendar_feed.py`)

**Files:**
- Modify: `ilovevoley/competitions/calendar_feed.py`
- Test: `ilovevoley/competitions/tests/test_views.py`

**Interfaces:**
- Updates:
  - `UserMatchesFeed.item_location(self, item)`
  - `UserMatchesFeed.item_description(self, item)`

- [ ] **Step 1: Escribir failing tests para el feed iCal con el nuevo sistema**

En `ilovevoley/competitions/tests/test_views.py`:
```python
def test_calendar_feed_location_uses_venue_full_address(self):
    from ilovevoley.competitions.models import Venue
    venue = Venue.objects.create(
        name="Pavelló Joan Pericás Riera",
        address="Son Serra s/n",
        city="Bunyola",
        google_maps_url="https://maps.app.goo.gl/bunyola"
    )
    self.match.venue_ref = venue
    self.match.save(update_fields=['venue_ref'])

    token = self.user.get_or_create_calendar_token()
    url = reverse('competitions:calendar_feed', args=[token])
    response = self.client.get(url, HTTP_HOST='testclub.ilovevoley.es')
    content = response.content.decode('utf-8')

    self.assertIn("LOCATION:Pavelló Joan Pericás Riera\\, Son Serra s/n\\, Bunyola", content)
    self.assertIn("https://maps.app.goo.gl/bunyola", content)
    self.assertIn("📍 Ubicación:", content)

def test_calendar_feed_location_infers_from_home_club_default_venue(self):
    from ilovevoley.competitions.models import Venue
    venue = Venue.objects.create(
        name="Pavelló Blanquerna",
        address="Carrer des Caülls, 1",
        city="Marratxí"
    )
    self.match.venue = ""
    self.match.venue_ref = None
    self.match.home_team.club.default_venue = venue
    self.match.home_team.club.save(update_fields=['default_venue'])
    self.match.save()

    token = self.user.get_or_create_calendar_token()
    url = reverse('competitions:calendar_feed', args=[token])
    response = self.client.get(url, HTTP_HOST='testclub.ilovevoley.es')
    content = response.content.decode('utf-8')

    self.assertIn("Pavelló Blanquerna", content)
```

- [ ] **Step 2: Ejecutar tests para comprobar que fallan**

```bash
DEV_DB_PORT=5546 DEV_REDIS_PORT=6481 docker compose -f docker-compose.dev.yml run --rm web python -m pytest ilovevoley/competitions/tests/test_views.py -k test_calendar_feed_location --tb=short
```

- [ ] **Step 3: Actualizar `calendar_feed.py`**

En `ilovevoley/competitions/calendar_feed.py`:
1. Importar `get_match_location_info` desde `ilovevoley.competitions.services.venue_service`.
2. Actualizar `item_location`:
   ```python
   def item_location(self, item):
       """Ubicación del evento normalizada para clientes de calendario (RFC 5545)."""
       info = get_match_location_info(item)
       return info['location_text']
   ```
3. Actualizar `item_description`:
   ```python
   # Bloque de ubicación y enlace a mapa
   info = get_match_location_info(item)
   if info['location_text'] and info['location_text'] != 'Por confirmar':
       description_parts.append('')
       description_parts.append(f'📍 Ubicación: {info["location_text"]}')
       if info['maps_url']:
           description_parts.append(f'🗺️ Cómo llegar: {info["maps_url"]}')
   ```

- [ ] **Step 4: Ejecutar tests y verificar que pasan**

```bash
DEV_DB_PORT=5546 DEV_REDIS_PORT=6481 docker compose -f docker-compose.dev.yml run --rm web python -m pytest ilovevoley/competitions/tests/test_views.py -k test_calendar --tb=short
```

---

### Task 6: Verificación Global de la Suite

- [ ] **Step 1: Ejecutar la suite completa de pruebas**

```bash
DEV_DB_PORT=5546 DEV_REDIS_PORT=6481 docker compose -f docker-compose.dev.yml run --rm web python -m pytest --create-db ilovevoley/competitions/ ilovevoley/teams/ --tb=short
```

- [ ] **Step 2: Revisar estado git y preparar propuesta de commit**
Verificar `git status` y formular la propuesta con imputación de tiempo y referencia a issue `#263`.
