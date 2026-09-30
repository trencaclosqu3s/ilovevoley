# Catálogo de Pabellones (`Venue`) y Ubicación Navegable en Feed de Calendario

**Fecha:** 2026-09-30  
**Estado:** Propuesta aprobada para especificación  
**Issue:** [#263](https://github.com/trencaclosqu3s/ilovevoley/issues/263)  
**Apps afectadas:** `ilovevoley.competitions`, `ilovevoley.teams`

---

## 1. Contexto y Diagnóstico del Problema

### El Problema
Actualmente, los eventos de partidos exportados en el feed iCal (`.ics`) en `UserMatchesFeed` solo emiten en la propiedad `LOCATION` la concatenación de `Match.venue` y `Match.city`, omitiendo completamente `Match.field_address`. Esto provoca que los clientes de calendario móvil (iOS Calendar / Apple Maps y Google Calendar) no reconozcan la dirección física para:
1. Mostrar la vista previa y el mapa interactivo del pabellón.
2. Calcular tiempos de desplazamiento y alertas proactivas ("Hora de salir" en iOS).
3. Ofrecer un botón nativo de "Ruta" o "Cómo llegar".

### Auditoría de Datos en Base de Datos Real
De 806 partidos almacenados:
- **472 partidos (58%)** tienen `venue`.
- **374 partidos (46%)** tienen `city`.
- Solo **241 partidos (30%)** tienen `field_address`.
- **291 partidos (36%)** no tienen **ningún dato de ubicación** (creados por scraping de jornadas `get_resultados.asp` que solo incluye el municipio en HTML o procedentes de históricos).
- Pabellones con alto volumen como Alaró (63 partidos), Sant Joan (36 partidos) o Algaida (9 partidos) tienen `field_address` 100% vacío.

Además:
- En la federación (`voleibolib`), el endpoint de próximas jornadas (`upcoming`) concatena texto plano para generar enlaces de búsqueda en Google Maps (`google.es/maps/search/Municipio+Campo+Direccion/`).
- En el modelo `teams.Club`, ya existen 44 clubes con `venue_name` y `venue_address` poblados en su ficha.
- Clubes de la liga como CV Mayurqa ya disponen de un catálogo consolidado con los ~35 pabellones habituales de Baleares y sus enlaces directos a Google Maps (`https://maps.app.goo.gl/...`).

---

## 2. Decisiones de Arquitectura

1. **Modelo `Venue` en `ilovevoley.competitions`**:
   Crear un modelo canónico de sedes/pabellones administrable desde Django Admin con Unfold. Permite registrar nombres normalizados, direcciones postales completas, municipios, enlaces directos a Google Maps y alias/variantes que utiliza la federación.

2. **Relación con `Match` y `Club`**:
   - `Match.venue_ref`: ForeignKey opcional a `competitions.Venue`. Se conservan los campos de texto `venue`, `city` y `field_address` para compatibilidad de scraping y auditoría de cambios (`delta_detector`).
   - `Club.default_venue`: ForeignKey opcional a `competitions.Venue` que define la pista habitual del club para partidos como local.

3. **Lógica de resolución con orden de prioridad estricto**:
   - **Prioridad 1 (Asignación directa)**: Si `match.venue_ref` está asignado manualmente o por scraping, se utiliza ese `Venue`.
   - **Prioridad 2 (Pabellón del partido)**: Si el partido tiene texto en `match.venue` (ej: `"Pav. Son Angelats"`), se busca coincidencia por nombre o por `aliases` en el catálogo de `Venue`. **La pista del partido siempre manda sobre la sede del club** (cubre casos donde el local juega en otra sede por logística o permuta de campo).
   - **Prioridad 3 (Fallback por Club Local)**: Si `match.venue` está vacío (partidos antiguos o recién programados), se recurre al `default_venue` del club local (`match.home_team.club.default_venue`).
   - **Prioridad 4 (Texto plano residual)**: Si no se reconoce ninguna sede, se compone la ubicación con los campos de texto del propio `Match` (`venue`, `field_address`, `city`). Si todo está vacío, fallback a `'Por confirmar'`.

4. **Poblado inicial mediante migración `RunPython` (Regla de proyecto)**:
   Los ~35 pabellones base se precargan mediante una migración de datos con `RunPython`, asociando de forma automática los `Club.default_venue` y aplicando un backfill sobre los partidos existentes en `Match`.

5. **Feed iCal (`UserMatchesFeed`)**:
   - `item_location(item)`: Genera la cadena formateada completa para `LOCATION` (`"<Nombre Pabellón>, <Dirección>, <Municipio>"`). En iOS activa la geocodificación local de CoreLocation, la alerta de salida y el botón nativo de navegación.
   - `item_description(item)`: Añade un bloque legible con el nombre del pabellón, la dirección y un enlace directo a Google Maps (`https://maps.app.goo.gl/...` o URL de búsqueda codificada).

---

## 3. Especificación Detallada de Modelos y Componentes

### 3.1. Modelo `Venue` (`ilovevoley/competitions/models/competitions.py`)

```python
class Venue(models.Model):
    name = models.CharField(
        max_length=200,
        unique=True,
        verbose_name='Nombre oficial',
        help_text='Nombre canónico del pabellón o instalación deportiva'
    )
    short_name = models.CharField(
        max_length=100,
        blank=True,
        verbose_name='Nombre corto',
        help_text='Nombre abreviado para listados compactos'
    )
    address = models.CharField(
        max_length=500,
        blank=True,
        verbose_name='Dirección',
        help_text='Dirección física completa (calle, número)'
    )
    city = models.CharField(
        max_length=100,
        blank=True,
        verbose_name='Municipio'
    )
    postal_code = models.CharField(
        max_length=10,
        blank=True,
        verbose_name='Código postal'
    )
    google_maps_url = models.URLField(
        max_length=500,
        blank=True,
        verbose_name='Enlace Google Maps',
        help_text='Enlace corto o directo a la ubicación en Google Maps (ej. https://maps.app.goo.gl/...)'
    )
    aliases = models.TextField(
        blank=True,
        verbose_name='Nombres alternativos / Alias',
        help_text='Variaciones de nombre separadas por coma o salto de línea usadas en federación (ej: Pav. Municipal Alaró, Pista 1, Pista 2)'
    )
    latitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
        verbose_name='Latitud'
    )
    longitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
        verbose_name='Longitud'
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name='Activo'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'videos_venue'
        ordering = ['city', 'name']
        verbose_name = 'Pabellón / Sede'
        verbose_name_plural = 'Pabellones / Sedes'

    def __str__(self):
        if self.city:
            return f'{self.name} ({self.city})'
        return self.name

    @property
    def full_address(self) -> str:
        """Devuelve la dirección física completa limpia para geocodificación RFC 5545."""
        parts = []
        if self.name:
            parts.append(self.name.strip())
        if self.address:
            # Evitar repetir el nombre si la dirección lo contiene
            addr = self.address.strip()
            if addr.lower() not in self.name.lower():
                parts.append(addr)
        if self.city:
            city_str = self.city.strip()
            if not any(city_str.lower() in p.lower() for p in parts):
                parts.append(city_str)
        return ', '.join(parts) if parts else 'Por confirmar'

    @property
    def maps_url(self) -> str | None:
        """Devuelve la URL directa a Maps o una URL de búsqueda como fallback."""
        if self.google_maps_url:
            return self.google_maps_url
        if self.full_address and self.full_address != 'Por confirmar':
            import urllib.parse
            query = urllib.parse.quote_plus(self.full_address)
            return f'https://www.google.com/maps/search/?api=1&query={query}'
        return None

    def matches_text(self, text: str) -> bool:
        """Verifica si un texto coincide con el nombre o alguno de los alias."""
        if not text:
            return False
        clean_text = text.strip().lower()
        if clean_text == self.name.strip().lower():
            return True
        if self.short_name and clean_text == self.short_name.strip().lower():
            return True
        if self.aliases:
            for alias in self.aliases.replace('\n', ',').split(','):
                alias_clean = alias.strip().lower()
                if alias_clean and (clean_text == alias_clean or alias_clean in clean_text or clean_text in alias_clean):
                    return True
        return False
```

### 3.2. Relaciones en `Match` y `Club`

- En `ilovevoley/competitions/models/competitions.py` (`Match`):
  ```python
  venue_ref = models.ForeignKey(
      'competitions.Venue',
      on_delete=models.SET_NULL,
      null=True,
      blank=True,
      related_name='matches',
      verbose_name='Pabellón'
  )
  ```
- En `ilovevoley/teams/models/teams.py` (`Club`):
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

### 3.3. Servicio de Resolución (`ilovevoley/competitions/services/venue_service.py`)

Función principal: `get_match_location_info(match: Match) -> dict`:
Retorna:
```python
{
    'venue': Venue | None,
    'location_text': str,     # Formateado completo para iCal LOCATION
    'maps_url': str | None,   # URL para iCal DESCRIPTION
    'is_inferred': bool,      # True si se obtuvo por fallback del club local
}
```

Algoritmo de resolución:
1. Si `match.venue_ref_id`: usar `match.venue_ref`.
2. Si `match.venue`: buscar en `Venue.objects.filter(is_active=True)` usando coincidencia exacta o alias.
3. Si no hay coincidencia y `match.home_team_id` y `match.home_team.club_id` y `match.home_team.club.default_venue_id`:
   Usar `match.home_team.club.default_venue` (marcado como `is_inferred=True`).
4. Si no se resuelve `Venue`:
   Construir `location_text` a partir de `match.venue`, `match.field_address`, `match.city`.
   Construir `maps_url` con búsqueda en Google Maps si hay texto disponible.

### 3.4. Integración en `UserMatchesFeed` (`calendar_feed.py`)

```python
def item_location(self, item):
    info = get_match_location_info(item)
    return info['location_text']

def item_description(self, item):
    # ... información existente ...
    info = get_match_location_info(item)
    if info['location_text'] and info['location_text'] != 'Por confirmar':
        description_parts.append('')
        description_parts.append(f'📍 Ubicación: {info["location_text"]}')
        if info['maps_url']:
            description_parts.append(f'🗺️ Cómo llegar: {info["maps_url"]}')
    # ... enlace web existente ...
    return '\n'.join(description_parts)
```

---

## 4. Migraciones y Backfill

1. **Migración de esquema en `competitions`**:
   Creación de la tabla `videos_venue` y adición de `Match.venue_ref`.
2. **Migración de esquema en `teams`**:
   Adición de `Club.default_venue`.
3. **Migración de datos (`RunPython`)**:
   - Insertar los ~35 pabellones (Alaró, Bunyola, Sóller, Sant Joan, Marratxí, Palma, Manacor, etc.) con sus direcciones y enlaces a Google Maps.
   - Asignar `Club.default_venue` para los 44 clubes según coincidencia de nombre o municipio.
   - Ejecutar backfill sobre `Match.objects.all()`: para cada partido con `venue` conocido, asignar `venue_ref`.

---

## 5. Pruebas y Criterios de Aceptación

1. **Unit tests para `Venue`**:
   - Cálculo correcto de `full_address` sin duplicados.
   - Generación de `maps_url` tanto con enlace explícito como con fallback URL-encoded.
   - Método `matches_text()` contra nombre, short_name y alias.
2. **Unit tests para `get_match_location_info`**:
   - Caso 1: Partido con `venue_ref` asignado explícitamente.
   - Caso 2: Partido con `venue="Pav. Son Angelats"` y club local Mayurqa (verifica que prima Son Angelats sobre Mayurqa).
   - Caso 3: Partido sin `venue` ni `field_address` pero con club local que tiene `default_venue`.
   - Caso 4: Partido sin ningún dato reconocible (retorna `'Por confirmar'`).
3. **Unit tests para `UserMatchesFeed`**:
   - Verifica que el feed `.ics` generado contiene `LOCATION:` con la dirección estructurada.
   - Verifica que la propiedad `DESCRIPTION:` contiene la sección de ubicación y el enlace de mapas.
4. **Verificación en clientes de calendario**:
   - Formato conforme a RFC 5545 para clientes iOS (Apple Calendar), Android (Google Calendar) y Outlook.
