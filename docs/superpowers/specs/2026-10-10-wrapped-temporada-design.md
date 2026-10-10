# Wrapped de temporada personal (#458)

## Objetivo

Que cada jugador, o su familia, tenga una vez al año un resumen compartible de su
temporada, al estilo Spotify Wrapped. Sin rankings ni comparativas entre jugadores
(distinto de #216, cerrada como «won't do»).

Quién lo ve: el propio jugador, su familia y los gestores, con las mismas reglas
que el cromo (`_card_person`).

## Decisiones

- **Snapshot persistido** (no cálculo al vuelo): se corrigen pocas actas a final de
  temporada, y el cierre es un momento explícito.
- **Oculto hasta el cierre**: lo lanza un admin (o una tarea programada). Ese
  momento es también el de la notificación a jugadores y padres.
- **Formato**: visor HTML con una pantalla por vista + un PNG por pantalla
  (Pillow), reutilizando la infraestructura del cromo.

## Modelo y generación

**`SeasonWrapped`** (app `rosters`), único por (`person`, `season`, `modality`):
- `modality`: `indoor` o `beach`, con los valores de `League.modality`.
- `stats` (JSON): partidos oficiales, sets jugados, partidos ganados en los que
  estuvo, rival más repetido, nº de fotos y ids de fotos candidatas.
- `created_at`.

Mientras no exista la fila, el jugador no ve nada: existir es lo que lo hace
visible. No hay estados de borrador.

**Tarea Celery `generate_season_wrappeds(season_id)`**, con `name=` explícito:
- Se lanza desde una acción del admin de `Season` o con un `PeriodicTask`.
- Recorre los jugadores con rol de jugador en esa temporada y calcula las cifras con
  `_played_official_lineups`, `get_season_rivals` e `Image.persons`.
- Idempotente: relanzarla no duplica filas ni vuelve a notificar a quien ya tiene
  la suya.
- Al crear cada fila notifica al jugador y a sus padres por push y email, en el
  idioma de cada destinatario (`push_message`, `send_notification_email`).
- Sin actas ni fotos, no se crea fila.
- Genera un wrapped **por modalidad**: filtra los partidos por
  `match__league__modality`. Hoy solo hay datos de pista, así que solo se crean
  filas `indoor`. Si la federación sirviera datos de playa, saldría un wrapped
  `beach` aparte, sin mezclar cifras.

**Consentimiento de imagen**: el snapshot guarda solo ids candidatos de foto. El
consentimiento (`card_photo_allowed`) se comprueba al mostrar, de modo que retirar
el consentimiento después oculta la foto aunque las cifras sigan fijas.

**Correcciones posteriores**: no hay recálculo automático. Si se corrige un acta
tras el cierre, el admin borra la fila y relanza la tarea.

**Etiqueta «partidos oficiales»**: `get_player_season_stats` no filtra por oficial,
así que el cálculo parte de `_played_official_lineups`. Ese helper y
`get_season_rivals` necesitan un parámetro `modality` (hoy no lo tienen).

**Playa, supuesto abierto**: las alineaciones y el formato de actas de playa
(parejas) no existen hoy. El diseño solo reserva la separación; cómo se calculan
sus cifras se decide si llega a haber datos.

## Visor, PNG, permisos y selector

**URLs** (en `rosters`, como las del cromo):
- `personas/<id>/wrapped/`: visor HTML, con `?season=<id>`.
- `personas/<id>/wrapped/<n>.png`: PNG de la pantalla `n`; con `?preview=1`, WebP
  reducido.

**Pantallas**: `rosters/season_wrapped.py` convierte `SeasonWrapped.stats` en una
lista de pantallas (título, cifra, subtítulo). Esa lista alimenta el visor y los
PNG. Orden: portada, partidos oficiales, sets, victorias, rival más repetido,
nº de fotos, foto más votada, cierre.
- Las pantallas con cifras de actas llevan la etiqueta «partidos oficiales»; sin
  acta se omiten.
- Las pantallas de fotos se omiten si no queda ninguna foto visible tras comprobar
  el consentimiento.
- La foto más votada sale de `ImageFavorite` (`match_top_images` como modelo).

**Render**: `render_wrapped_screen(...)` con Pillow, reutilizando fondos, fuentes y
utilidades de `rosters/player_card.py` y `competitions/result_card.py`. Formato Story.

**Visor**: plantilla con una pantalla por vista, que avanza con toque o swipe y tiene
indicador de progreso. HTML/CSS/JS ligero, sin librerías. Botón «Compartir» con la
Web Share API siguiendo `static/js/player_card.js` (genera el PNG y comparte tras el
segundo toque) y «Compartir todas» con varios archivos.

**Permisos**: jugador, familia y gestores, como `_card_person`. Sin fila para esa
temporada, 404.

**Modalidad**: las URLs aceptan `?modality=indoor|beach` (por defecto `indoor`).
El selector solo muestra la modalidad si la persona tiene wrapped de más de una.
Las fotos no tienen modalidad: van en el wrapped `indoor`, y solo en el `beach`
si el `Image` está vinculado a un partido de playa.

**Selector de temporada**: lista solo las temporadas con `SeasonWrapped` de esa
persona (en la modalidad elegida), vía `?season=`. No se usa `resolve_season_filter` porque aquí no tiene
sentido ofrecer «todas».

**Entrada**: enlace al Wrapped en `my_profile` y `child_profile` cuando existe, más el
enlace de la notificación.

## Tests

Solo reglas de negocio (`docs/ai-guidelines/testing-guidelines.md`):
- Cálculo: solo cuenta partidos oficiales y de la modalidad pedida (un partido de
  playa no suma al wrapped indoor); rival más repetido y victorias.
- Consentimiento: una foto con consentimiento retirado no sale.
- Idempotencia de la tarea y sin doble notificación.
- Permisos del visor y de los PNG.

## Fuera de alcance

Rankings o comparativas, informe PDF para el entrenador, recálculo automático tras
el cierre, caché.
