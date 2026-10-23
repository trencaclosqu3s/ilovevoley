# Integración marcador ↔ ilovevoley

**Fecha:** 2026-10-23
**Issues:** #575, #576, #577, #578, #579, #603
**Repos:** `ilovevoley` (este) y `trencaclosqu3s/voley-scoreboard` (marcador de grada: Flask + MediaMTX + ffmpeg → YouTube Live)

El marcador habla con ilovevoley por HTTP con un token Bearer compartido. Todo es best-effort: si ilovevoley no responde o no hay partido elegido, el panel y la emisión siguen funcionando a mano.

## Endpoints (`ilovevoley/competitions/scoreboard_api.py`)

Todos cuelgan de `/competitions/` y exigen `Authorization: Bearer <SCOREBOARD_STREAM_TOKEN>` (comparado con `hmac.compare_digest`), salvo el GET público de la ficha.

| Método y ruta | Quién llama | Qué hace |
|---|---|---|
| `GET api/matches/today/` | panel del marcador | Partidos abiertos de hoy del club: id, equipos, escudos, colores, hora. |
| `POST api/stream/live/` | `start_stream.sh` y reaviso del panel | Guarda `stream_url` (resuelto a `watch?v=<id>` si puede) y envía push de directo, una sola vez (`stream_notified_at`). |
| `POST api/match/result/` | botón «Finalizar partido» | Valida con `validate_volleyball_score`, rellena `home_score`, `away_score` y `set_scores`, push de resultado idempotente (`result_notified_at`). 409 si ya hay resultado federativo. |
| `POST api/match/live-state/` | hilo `live-pusher` | Guarda el marcador en vivo en Redis (TTL 90 s). |
| `POST api/stream/ended/` | hilo vigilante | Crea un único `Video` vinculado al partido (`get_or_create`). Exige `match_id`. |
| `GET match/<id>/live-state/` | ficha del partido | Público; devuelve el estado en vivo solo dentro de la ventana de directo. |

Resolución del partido: si el aviso trae `match_id` se usa ese; si no, el único partido en ventana de directo (`Match.is_live_window`, −30 min / +3 h); con 0 o varios devuelve 409. Token y resolución viven en un único helper compartido por todos los endpoints.

Topes del contrato: 99 puntos, 9 sets, 9 parciales. Códigos: 200, 400, 403, 404, 409, 503.

## Flujo de un partido

1. **Elegir partido.** El operador lo elige en «Partido de hoy»; se rellenan equipos, colores y escudos y se guarda `match_id` en `state.json` y `/shm/match_id.txt`. Si la emisión ya estaba activa, el marcador reavisa `stream/live` con ese `match_id`.
2. **Iniciar emisión.** `start_stream.sh` avisa a los ~10 s con `match_id`. ilovevoley resuelve `@canal/live` a `watch?v=<id>` (con `safe_get`, anti-SSRF); si falla, queda `@canal/live` y el latido de directo lo reintenta como máximo cada 120 s (clave de caché `scoreboard:live-resolve:{match_id}`).
3. **Marcador en vivo.** Cada cambio se empuja con coalescencia y hay un latido de 30 s. La ficha hace polling (5 s en directo, 30 s si no) y oculta la tarjeta con 404/409.
4. **Finalizar.** El botón envía sets y parciales. Tras el 200 el marcador fija `match_closed` en `state.json` y deja de empujar latidos; `api_match_pick` y `api_match_clear` lo resetean.
5. **Fin de emisión.** Un hilo vigilante detecta N minutos sin `ffmpeg_progress.txt` (`SCOREBOARD_END_GRACE_MINUTES`, 10 por defecto, para no confundir cortes de 4G) y avisa una vez a `stream/ended`.

## Decisiones

- **La federación manda.** El resultado del marcador es provisional; el scraping federativo lo sobrescribe sin reenviar push y registra `MatchChangeLog(change_type='score')`.
- **Push desde el marcador a Redis, no pull.** Un endpoint público de lectura en el marcador expondría el marcador sin PIN.
- **Un club, token global.** Quien tenga el token puede poner un directo en un partido de otro club. Techo conocido; token por club queda para v2.
- **Sin API de YouTube ni OAuth** (`SOCIALACCOUNT_STORE_TOKENS = False`): solo el HTML público.

## Configuración

| Variable | Dónde | Efecto |
|---|---|---|
| `SCOREBOARD_STREAM_TOKEN` | ilovevoley | Debe coincidir con `ILOVEVOLEY_STREAM_TOKEN` del marcador. Vacío: todo responde 403. |
| `SCOREBOARD_VIDEO_USER_ID` | ilovevoley | `created_by` de los `Video`. Sin él, `stream/ended` da 503 y se registra `logger.error`; el vídeo se crea a mano. |
| `SCOREBOARD_END_GRACE_MINUTES` | marcador | Minutos sin cámara antes del aviso de fin (10). |
| `SCOREBOARD_LIVE_HEARTBEAT_SECONDS` | marcador | Latido del empuje en vivo (30). |

## Despliegue

- Desplegar siempre **ilovevoley antes que el marcador**; los campos nuevos que envía el marcador son opcionales en el servidor.
- **Recrear `mediamtx` corta la emisión:** desplegar el marcador solo fuera de partido.
- Ningún endpoint nuevo necesita migración.

## Límites conocidos

- Si `finish` recibe 409 por acta federativa, el marcador no marca `match_closed` y el latido recibe 409 cada 30 s hasta elegir otro partido (inocuo, sin pérdida de datos).
- Los latidos fuera de la ventana de directo reciben 409 sin límite de reintentos.
- `stream/ended` usa el `match_id` vigente (D-18): sin partido elegido no se crea `Video`, y si tras finalizar A se elige B con la emisión activa, el `Video` se crea para B. Se crea a mano si hace falta.
- Pendiente en producción: verificación visual del panel en móvil y de la tarjeta «Marcador en directo» con partidos reales.
