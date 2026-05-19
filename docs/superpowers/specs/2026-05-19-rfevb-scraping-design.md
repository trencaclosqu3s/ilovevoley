# Diseño: Scraping RFEVB — Campeonato de España de Clubs

**Fecha:** 2026-05-19  
**Competición de referencia:** CEIM 2025-26 (IdCompeticion=9041)  
**Estado:** Aprobado

---

## Contexto

La web de la Real Federación Española de Voleibol (RFEVB) es un sitio PHP clásico que devuelve HTML. Su estructura difiere del sistema JSON de la federación balear (`voleibolib.net`), por lo que necesita un nuevo parser. El objetivo es reutilizar el mismo parser para cualquier campeonato nacional futuro.

Los torneos nacionales (CEIM, CBAL nacional, etc.) se estructuran en fases (`auxIdFase`). Cada fase puede contener grupos (primera fase) o brackets de clasificación (fases posteriores). Los partidos de fases posteriores usan placeholders del tipo `#= 1 Grupo A` hasta que los resultados de la fase anterior determinan los participantes reales.

**Alcance:** solo se procesan partidos con equipos reales (se descartan los placeholders). Los partidos se crean o actualizan en el momento en que la web muestra datos reales.

---

## URLs y estructura HTML

### Endpoints

| Propósito | URL |
|-----------|-----|
| Equipos participantes | `webCompeticion-equipos.php?IdCompeticion={id}` |
| Fase (partidos + clasificación) | `webCompeticion-campeonatosFase.php?auxIdFase={id}` |
| Clasificación general | `webCompeticion-clasificacion.php?IdCompeticion={id}` |

Base: `https://intranet.rfevb.com/rfevbcom/includes-html/competiciones/`

### Estructura de una página de fase

```html
<div class="card">
  <h4> Grupo A</h4>
  <!-- tabla de partidos -->
  <table class="table table-responsive">
    <tr>
      <th>1</th>
      <td>AD Eliocroca - Ube L'Illa Grau</td>
      <td>27/05/26 (17:00)</td>
      <td>Pabellón Ciudad Deportiva</td>
      <td>0 - 0</td>
      <td>(0-0/0-0/0-0/0-0/0-0)</td>
    </tr>
    ...
  </table>
  <!-- tabla de clasificación -->
  <table width="80%">
    <thead>
      <tr>
        <th colspan="2">CLASIFICACIÓN</th>
        <th>Ptos</th><th>J</th><th>G3</th><th>G2</th>
        <th>P1</th><th>P0</th><th>SF</th><th>SC</th><th>PF</th><th>PC</th>
      </tr>
    </thead>
    <tbody>
      <tr>
        <td>1</td>
        <td><img ...> AD Eliocroca</td>
        <td>0</td><td>0</td>...
      </tr>
    </tbody>
  </table>
</div>
```

### Particularidades del HTML

- Encoding: `iso-8859-1` — pasar `response.content` + `response.encoding` a BeautifulSoup
- Score `0 - 0` con todos los parciales `(0-0/0-0/0-0/0-0/0-0)` = partido no jugado
- Año en fechas de 2 dígitos: `27/05/26` → `strptime(..., "%d/%m/%y (%H:%M)")` — Python lo convierte a 2026 ✓
- Placeholder: nombre de equipo que empieza por `#` (ej: `#= 1 Grupo A`)
- Separador entre equipos: `" - "` (espacio-guión-espacio) — usar `split(" - ", 1)`

---

## Componentes

### 1. `RFEVBPhaseParser(BaseParser)` — `scraping.py`

Parser reutilizable para cualquier página de fase RFEVB.

**Método principal:** `parse_content(html: str) -> Dict`

**Retorna:**
```python
{
    'groups': [
        {
            'name': 'Grupo A',
            'matches': [
                {
                    'rfevb_match_number': 1,
                    'home_team_name': 'AD Eliocroca',
                    'away_team_name': "Ube L'Illa Grau",
                    'match_date': datetime(2026, 5, 27, 17, 0, tzinfo=Madrid),
                    'venue': 'Pabellón Ciudad Deportiva',
                    'home_score': None,   # int si jugado
                    'away_score': None,
                    'status': 'scheduled',  # o 'finished'
                }
            ],
            'standings': [
                {
                    'position': 1,
                    'team_name': 'AD Eliocroca',
                    'played': 0,
                    'won': 0,    # G3 + G2
                    'lost': 0,   # P1 + P0
                    'sets_for': 0,
                    'sets_against': 0,
                }
            ]
        }
    ]
}
```

**Lógica de parseo:**
- Un `<div class="card">` = un grupo
- `<h4>` dentro del card = nombre del grupo (strip de espacios)
- Primera tabla del card (`class="table table-responsive"`) = partidos
- Segunda tabla del card (`width="80%"`) = clasificación — puede no existir (fases cruzadas no tienen clasificación, solo partidos); el parser la omite silenciosamente si no está presente
- Partido descartado si `home_team_name.startswith('#')` o `away_team_name.startswith('#')`
- Score: `"X - Y".split(" - ")` → `(int(X), int(Y))`; si ambos son 0 → `scheduled`, si no → validar con `validate_volleyball_score()` → `finished`
- Nombre de equipo en standings: texto del `<td>` que contiene el `<img>`, con `.get_text(strip=True)` (BeautifulSoup ignora el img)
- Mapping columnas standings: `J`→played, `G3+G2`→won, `P1+P0`→lost, `SF`→sets_for, `SC`→sets_against (puntos no se almacenan, son calculables)

### 2. Comando `scrape_rfevb_fase` — `management/commands/scrape_rfevb_fase.py`

Comando genérico, reutilizable para cualquier competición RFEVB.

**Argumentos:**
```
--competition-id   ID de competición RFEVB (ej: 9041)
--fase-ids         IDs de fase separados por coma (ej: 2193,2194,2195,2196)
--parent-league    federation_id de la liga padre en BD (ej: ceim_2526)
--dry-run          Ejecutar sin guardar cambios
--delay            Segundos entre fases (default: 2.0)
```

**Flujo por fase:**

```
Para cada auxIdFase:
  fetch → parse → para cada grupo:
    1. Buscar/crear sub-liga
    2. Para cada partido no-placeholder:
       a. Resolver equipos
       b. Crear/actualizar Match
    3. Actualizar Standings
  rate_limit(delay)
```

#### Sub-liga: buscar o crear

```python
League.objects.get_or_create(
    parent_league=parent,
    phase_name=group_name,          # ej: "Grupo A", "1 al 16"
    defaults={
        'federation_id': f'{parent.federation_id}_{slugify(group_name)}',
        'name': f'{parent.name} - {group_name}',
        'competition_type': parent.competition_type,
        'match_format': parent.match_format,
        'season': parent.season,
        'visibility_type': parent.visibility_type,
        'is_our_team_related': parent.is_our_team_related,
    }
)
```

Sin hardcoding: cualquier nombre de grupo del HTML genera la sub-liga correcta.

#### Resolución de equipos (en cascada)

1. Búsqueda exacta: `Team.objects.filter(name=name).first()`
2. Búsqueda normalizada: `unidecode(name).lower().strip()` contra todos los equipos del torneo (precargados en memoria al inicio)
3. No encontrado → crear equipo con `federation_id=f'rfevb_{competition_id}_{slugify(name)}'` + warning en log

#### Match get-or-create

```python
rfevb_id = f'rfevb_{competition_id}_{match_number}'

match = Match.objects.filter(federation_id=rfevb_id).first()
if not match:
    # Buscar partido creado manualmente (sin federation_id aún)
    match = Match.objects.filter(
        league=league,
        home_team=home_team,
        away_team=away_team,
    ).first()
    if match:
        match.federation_id = rfevb_id   # anclar para lookups futuros
    else:
        match = Match(
            league=league,
            home_team=home_team,
            away_team=away_team,
            federation_id=rfevb_id,
            match_date=match_date,
            venue=venue,
            status='scheduled',
        )

if status == 'finished':
    match.home_score = home_score
    match.away_score = away_score
    match.status = 'finished'

match.save()
```

#### Output del comando

```
[Fase 2193]
  Grupo A: 6 partidos — 0 jugados, 6 pendientes
  Grupo B: 6 partidos — 0 jugados, 6 pendientes
  ...
[Fase 2194]
  1 al 16: todos placeholders, sin datos reales todavía
  17 al 32: todos placeholders, sin datos reales todavía

RESUMEN: 2 fases procesadas | 48 partidos encontrados | 0 actualizados | 0 errores
```

---

## Manejo de errores

- Fetch fallido → log error, continuar con siguiente fase
- Partido con fecha inválida → log warning, descartar partido
- Score inválido (no supera `validate_volleyball_score`) → log warning, mantener `scheduled`
- Equipo no encontrado y no se puede crear (federation_id colisión) → log error, descartar partido

---

## Uso para el CEIM 2025-26

```bash
# Durante el torneo (27-30 mayo 2026)
docker compose run --rm web python manage.py scrape_rfevb_fase \
  --competition-id 9041 \
  --fase-ids 2193,2194,2195,2196 \
  --parent-league ceim_2526

# Verificar sin guardar
docker compose run --rm web python manage.py scrape_rfevb_fase \
  --competition-id 9041 \
  --fase-ids 2193 \
  --parent-league ceim_2526 \
  --dry-run
```

---

## Fuera de alcance

- Scraping de equipos participantes (`webCompeticion-equipos.php`) — los equipos ya existen en BD
- Clasificación general final (`webCompeticion-clasificacion.php`) — se puede añadir en el futuro
- Tarea Celery periódica — se puede añadir en el futuro si se necesita scraping automático
- Actas de partido individuales
