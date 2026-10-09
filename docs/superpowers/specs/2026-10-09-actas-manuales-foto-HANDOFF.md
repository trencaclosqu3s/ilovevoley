# HANDOFF #462 — Actas manuales (foto): por dónde empezar

Para un agente que llega sin contexto. **Lee esto primero (5 min), luego la spec solo en las secciones que se citan.**
Rama: `feature-leer-actas-manuales-foto-en-pdf-con-visi` · Issue: https://github.com/trencaclosqu3s/ilovevoley/issues/462
Spec completa: `2026-10-09-actas-manuales-foto-design.md` (misma carpeta). Si algo choca, **manda §12 de la spec**.

---

## 1. El objetivo en 4 líneas
Algunos partidos no tienen acta HTML; la federación solo publica **una foto del acta en papel**. Queremos:
**bajar la foto → que Gemini (gratis) la lea → una persona la corrige y valida en el admin → se guarda con `store_match_lineups`** para las estadísticas por jugador.
**Solo para partidos de equipos de los tenants** (~2-3 a la semana). Nada se guarda sin aprobación humana.

## 2. Lo que YA está decidido (no lo discutas, no lo cambies)
1. Modelo con visión: **Gemini, nivel gratuito**, por REST con `requests`. **Sin dependencia nueva, sin Claude/Anthropic, sin dinero.**
2. **Solo partidos de tenants:** `Match.objects.for_tenant(tenant)`. Las ~945 actas históricas **no se procesan**.
3. **La revisión se hace en el admin de Unfold y la construye el usuario.** **TÚ NO CONSTRUYES NINGUNA PANTALLA.**
4. El modelo **no es fiable leyendo parciales** (acertó 2-3 de 9). Los parciales los publica la federación (`Match.set_scores`): son la verdad y la comprobación. Ver spec §11.
5. El campo `confidence` del modelo **no sirve** (siempre decía «high»). No lo uses para decidir.
6. Para las estadísticas importa el **dorsal**, no el apellido (`build_match_lineups` busca a la persona por `(equipo, dorsal)`).
7. **Nunca guardar la imagen original ni EXIF/GPS.** Solo un JPEG limpio, lado largo ≈ 1600 px.
8. **No commitear fotos reales de actas** (llevan nombres y firmas de menores). Los tests usan imágenes **sintéticas** (Pillow).

## 3. Reglas del proyecto que rompen cosas si se ignoran
- Comandos Django **siempre en Docker**: `docker compose -f docker-compose.dev.yml run --rm web python manage.py <cmd>`.
- Tests: `docker compose -f docker-compose.dev.yml run --rm web python -m pytest --create-db <ruta> --tb=short` (lanza solo los tests que tocas, no toda la suite).
- **Migraciones:** `makemigrations` y **PARA: avisa al usuario** para que las revise y aplique. No las escribas a mano ni edites las existentes.
- **Tests:** antes de escribir uno, justifica en 1 línea por qué protege una regla de negocio (`docs/ai-guidelines/testing-guidelines.md`). Nada de tests que solo comprueban `status_code` o que mockean todo.
- **Git:** **no commit/push/PR sin que el usuario lo pida.** (En este repo el usuario permite commits por fases; ante la duda, pregunta.)
- **Logging:** nada de `print(` / `.debug(` / `logger.info` (los hooks pre-commit lo bloquean). Solo `logger.warning/error` en errores reales.
- **Celery:** toda tarea con `name=` explícito.
- Código en **inglés**; comentarios, docs y mensajes al usuario en **castellano**. Nunca el prefijo `ponytail:` en comentarios.
- Cadenas nuevas de cara al usuario: `_()` y luego `makemessages -l ca`.

## 4. Mapa del código (léelo, no lo reescribas)
| Qué | Dónde |
|---|---|
| Esquema JSON del acta (el contrato) | `ilovevoley/videos/scraping/acta.py` → `parse_acta_lineup` (docstring) |
| Guardar un acta ya validada | `ilovevoley/competitions/services/lineups.py` → `store_match_lineups(match, data)` |
| Cómo se resuelve dorsal → persona | `lineups.py` → `_roles_lookup`, `build_match_lineups` |
| Marcadores por set | `ilovevoley/competitions/services/sets.py` → `extract_set_scores` |
| Modelo `Match` (campos `acta_html`, `acta_data`, `set_scores`, `federation_id`) | `ilovevoley/competitions/models/competitions.py` (`class Match`, ~línea 422) |
| Scraping de resultados (HTML con los iconos «Ver Acta» / «Ver Foto Acta») | `ilovevoley/videos/scraping/federation.py` (`_fetch_round_map`, ~líneas 100-170) |
| Ejemplo de admin Unfold con aprobar/rechazar | `ilovevoley/competitions/admin/competitions.py` → `LeagueCandidateAdmin` |
| Ámbito por tenant | `ilovevoley/core/tenancy.py` |

## 5. Material ya descargado (NO volver a bajarlo: la federación va lenta)
Carpeta `.local/actas-2025-26/` en el worktree (no está en git, no la commitees):
`scan.json` (1908 partidos), `samples/` (4 PDF reales y sus imágenes), `batch2/` (9 fotos más), `gemini_test.py` y `gemini_batch.py` (scripts de prueba con Gemini).
El CSV `2026-10-09-actas-manuales-foto-datos-2025-26.csv` (sí en git) lista los 947 partidos solo-foto con su enlace.
La clave de Gemini **no está en ningún fichero del repo**: se pide al usuario y va en la variable de entorno `GEMINI_API_KEY`.

## 6. Orden de trabajo — haz UN paso, comprueba, y para a informar

### Paso 0 — Verificar una hipótesis (30 min, sin escribir código de producto)
**Hipótesis:** en `https://www.voleibolib.net/pdf.asp?o=81768.jpeg` el número (81768) es el **ID del partido** de la federación, o sea `Match.federation_id`.
1. Abre un shell Django (comando de §3 con `shell`) y busca partidos de un tenant **de la temporada pasada** con foto: coge 3 filas del CSV (`match_id_guess`) y mira si existe `Match.all_objects.filter(federation_id=<número>)`.
2. Resultado: «coincide» o «no coincide» + 3 ejemplos. **Si no coincide**, el plan es emparejar por id de club + jornada (como hace `_fetch_round_map`); díselo al usuario antes de seguir.

### Paso 1 — Guardar el enlace + modelo `MatchActaPhoto`
- Modelo nuevo en `competitions` (campos: spec §5.1 y §12.1.5). **Cuando acabes: `makemigrations` y PARA, avisa al usuario.**
- En el scraping, al leer los resultados (HTML), si un partido **de un tenant** no tiene «Ver Acta» y sí «Ver Foto Acta» con URL tipo `pdf.asp?o=<número>.<ext>` (NO `o=<número>_<número>.pdf`): crear `MatchActaPhoto(source_url=<URL completa>, status='pending_download')`. Idempotente.
- **Hecho cuando:** un test justificado comprueba que (a) se crea 1 registro para un partido de tenant solo-foto, (b) no se crea para un partido con acta HTML, (c) no se crea para un partido que no es de un tenant, (d) repetir el scraping no duplica ni pisa un `approved`.

### Paso 2 — Descargar y preparar la imagen (`competitions/services/acta_photo.py`)
Detalle y trampas reales en spec **§2.3, §2.4 y §5.3**. Resumen:
- `GET` con redirección y User-Agent de navegador; si la respuesta **no empieza por `%PDF`** → estado `expired` («El acta no se ha guardado en el servidor»).
- Sacar las imágenes del PDF con `pypdf`; **deduplicar** (hay PDFs de 2 páginas con la misma imagen); ignorar máscaras; si no hay imagen (HEIC vacío) → `unreadable`.
- **El truco de «bytes entre `FF D8` y `FF D9`» NO vale para PNG/HEIC.** No lo uses como única vía.
- Pillow: enderezar (`ImageOps.exif_transpose`), RGB, lado largo ≈ 1600 px, guardar JPEG **sin EXIF/GPS**.
- **Hecho cuando:** tests con PDFs **sintéticos** (los generas con Pillow + pypdf) cubren: JPEG normal, PDF de 2 páginas iguales, PNG con máscara, PDF sin imágenes, respuesta de texto «caducada».

### Paso 3 — Lectura con Gemini (`competitions/services/acta_vision.py`)
- Una función `read_acta(image_bytes, context) -> dict`. Un modelo, por REST, `x-goog-api-key`, `responseMimeType: application/json`, `temperature: 0`.
- Modelo a usar: `gemini-3.5-flash-lite` (**los 2.5 dan 404 para cuentas nuevas**; `3.8-flash` va lento y da 503). Prompt de ejemplo: `.local/actas-2025-26/gemini_batch.py`.
- Contexto en el prompt: nombres de los dos equipos; para el equipo propio, la plantilla `dorsal → apellido` (de `PlayerRole`); **pedir que solo confirme/corrija, que no invente**.
- Detrás del setting `ACTA_VISION_ENABLED` (por defecto `False`). Errores 429/503 → dejar la foto para la siguiente ejecución, **nunca perderla**.
- Tarea Celery con `name=` explícito y límite de partidos por ejecución.
- **Hecho cuando:** hay tests con la respuesta HTTP **simulada** de Gemini que cubren: JSON válido, JSON roto, 503, y que el parser del resultado produce el esquema de `parse_acta_lineup`.

### Paso 4 — Validar y dejar listo para el admin
- Validación (spec **§5.5**): parciales leídos vs `Match.set_scores`; **si no coinciden se ignora lo leído y se avisa, sin bloquear**; resultado sancionado (`is_penalty_result`) → marcar «revisar», nunca descartar ni tocar `set_scores` oficial; dorsales enteros 0-99 sin repetir; equipos casan con `resolve_acta_team`.
- Servicios para el admin del usuario: `approve_acta_photo(photo, data, user)`, `reject_acta_photo(photo, user)` y la comparación por dorsal «leído · plantilla · coincide».
- **Hecho cuando:** `approve_acta_photo` con datos válidos deja `MatchLineup` creados y estado `approved`; con datos inválidos no guarda nada (test de la regla de negocio).

### Paso 5 — #455
La tarea que reintenta actas por la vía HTML debe **saltarse** los partidos que tienen `MatchActaPhoto` y no tienen `acta_html`.

## 7. Qué NO hacer (errores tentadores)
- ❌ Construir la pantalla de revisión o cualquier vista/plantilla nueva (la hace el usuario en el admin).
- ❌ Añadir `anthropic`, `google-genai` u otro SDK. REST con `requests`.
- ❌ Procesar actas de equipos que no son de un tenant, o bajar las ~945 históricas.
- ❌ Fiarte de `confidence` o de los parciales que lea el modelo.
- ❌ Sobrescribir `Match.set_scores` con lo leído de la foto.
- ❌ Guardar el JPEG original, el EXIF o el GPS. Commitear fotos reales de actas.
- ❌ Pegar la clave de API en un fichero, test o commit.
- ❌ Hacer varios pasos a la vez. **Un paso → tests → informa al usuario → siguiente.**

## 8. Cómo informar al usuario al acabar cada paso (3 líneas)
1. Qué quedó hecho y qué tests lo prueban (nombre de los tests). 2. Qué decisión tomaste que no estaba escrita. 3. Qué necesitas de él (migración que aplicar, clave, etc.).
Si te atascas más de 2 intentos con lo mismo (p. ej. un PDF raro), **para y cuéntalo**: no inventes una solución a medias.

## 9. Prompt para copiar en el agente nuevo
```
Lee docs/superpowers/specs/2026-10-09-actas-manuales-foto-HANDOFF.md entero y, de la spec
2026-10-09-actas-manuales-foto-design.md, solo §12 y las secciones que cite el handoff.
Empieza por el Paso 0 (verificar la hipótesis del ID del partido). No escribas código de
producto hasta informarme del resultado. Respeta las reglas del §3 y la lista del §7.
```
