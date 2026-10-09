# Spec #462 — Leer actas manuales (foto) con visión y revisión humana

Fecha: 2026-10-09 · Issue: https://github.com/trencaclosqu3s/ilovevoley/issues/462
Rama de trabajo: `feature-leer-actas-manuales-foto-en-pdf-con-visi` (worktree). **Nada está commiteado.**
Documento pensado para que lo continúe **otro agente sin contexto previo**. Léelo entero antes de tocar código.

> ⚠️ **El alcance y el flujo definitivos están en §12 (decisión del usuario, 2026-10-09) y prevalecen sobre §5 y §6 donde haya diferencias.**
> Resumen: solo partidos de equipos de los tenants, volumen mínimo (~2-3 a la semana), el modelo propone, **una persona corrige y valida** en una página con la foto,
> y los nombres se rellenan desde la plantilla por dorsal. Léase §10 y §11 para saber qué falla y qué no del modelo.

---

## 1. La idea en cinco frases

1. Algunos partidos **no tienen acta digital** (HTML). La federación publica en su lugar **una foto del acta en papel**.
2. Hoy esa foto **no se guarda** y esos partidos **no cuentan** en las estadísticas por jugador (#455, #457, #458, #459).
3. Queremos: **bajar la foto → leerla con un modelo con visión → comprobar que los números cuadran → que una persona la revise mirando la foto → guardarla** como cualquier otra acta.
4. Si los números no cuadran, **se descarta** (nunca se guarda algo dudoso).
5. **Nada entra en la base de datos de estadísticas sin aprobación humana.**

---

## 2. Qué hemos descubierto (datos reales, temporada 2025-26)

Se recorrieron **todas las jornadas de todos los grupos alevín e infantil** (75 grupos, 1908 partidos).

| | alevín | infantil |
|---|---|---|
| Solo «Ver Foto Acta», **sin** acta HTML | **495** | **450** |
| Sin ningún enlace (jugados) | 130 | 60 |
| Acta HTML + foto | 75 | 658 |

→ **~945 partidos del año pasado eran solo foto.** No son «pocos»: en alevín es lo normal.
Lista completa en `2026-10-09-actas-manuales-foto-datos-2025-26.csv` (947 filas, misma carpeta).
Script que la generó: `2026-10-09-actas-manuales-foto-scan.py` (necesita `menu2526.html`, que se baja con
`curl "https://www.voleibolib.net/JSON/get_Menu_Competiciones.asp?temp=2526"`; usa `curl` por subprocess porque
`urllib` falla con los certificados de este Python).

### 2.1 Dónde está el enlace

En el HTML de resultados `https://www.voleibolib.net/JSON/get_resultados.asp?id={liga}&jor={jornada}` cada partido
(`<div class='estado_partido'>`) puede traer **dos iconos**:

```html
<a href='https://voleibolib.federatio.com/actas/84847/acta_9742.html' title='Ver Acta'>…
<a href='https://www.voleibolib.net/pdf.asp?o=81768.jpeg'             title='Ver Foto Acta'>…
```

- Partido con acta HTML: aparece «Ver Acta» y su «Foto Acta» es de otro tipo (`pdf.asp?o=1777712907_1085.pdf`, un PDF
  del acta HTML). **No nos interesa.**
- Partido solo foto: aparece **solo** «Ver Foto Acta» con `o={número}.{extensión}`.
- Ese `{número}` **es casi seguro el `ID` del partido** de la federación (mismo rango que el `ID` del JSON unificado,
  p. ej. 86112, y que la carpeta del acta HTML `actas/84847/`). **Hipótesis a verificar** (ver §6, paso 0).
- El HTML de resultados **no trae el ID del partido** (el código ya empareja por id de club del escudo + jornada, ver
  `_fetch_round_map` en `ilovevoley/videos/scraping/federation.py`).
- El JSON unificado (`get_partidos_desglose_competiciones.asp`) trae `ID` y `acta_html`, **pero no el enlace de la foto**.

### 2.2 La extensión del enlace NO es siempre `.jpeg`

Entre los 945 sin acta HTML: `.jpg` 511 · `.jpeg` 409 · `.png` 11 · `.HEIC` 4 · `.pdf` 12.
**Guarda el enlace completo, no solo el número.**

### 2.3 Qué responde `pdf.asp`

- `GET https://www.voleibolib.net/pdf.asp?o=81768.jpeg` → **302** → `https://www.voleibolib.net/pdfs/<ddmmaaaahhmmss>_<n>.pdf`
  (PDF generado en cada petición; no cachear la URL de destino).
- **Enlaces `….pdf` (los 12 de infantil)**: **ya no devuelven PDF**; devuelven 200 + texto de 69 bytes:
  `El acta no se ha guardado en el servidor.Consulte con la federacion.` → tratar como **«sin acta»**, no como error.
- No hay URL directa al JPEG (404 en `/{ID}.jpeg`, `/actas/`, `/pdfs/`, `/imagenes/`, `/fotos/`).

### 2.4 ⚠️ El truco de la issue («bytes entre `FF D8 FF` y `FF D9`») NO basta

Solo funciona si el PDF lleva el JPEG sin recomprimir (`/Filter /DCTDecode`). Probado:

| Enlace | Qué contiene el PDF |
|---|---|
| `.jpeg` (alevín) | 1 página, JPEG `DCTDecode` 1600×1184 ✅ truco válido |
| `.jpg` (alevín) | **2 páginas con la misma imagen** JPEG 1152×2048 (extraer una sola vez) |
| `.png` (alevín) | PNG **recomprimido** (`FlateDecode`) + máscara alfa (`SMask`) 794×1123 ❌ truco inválido |
| `.HEIC` (alevín) | PDF de 1 página **sin ninguna imagen** extraíble ❌ (tratar como «no legible») |

→ Usar **`pypdf`** (ya está en `requirements.txt`, `pypdf>=6.19.0`) para listar `page.images` de todas las páginas,
**deduplicar por contenido** (hash) y convertir con **Pillow** (`Pillow==12.3.0`, `pillow-heif==1.8.0` ya instalados).
Con el entorno local de pruebas también va `pdfimages -all` (poppler), pero **no asumir poppler en el contenedor**.

### 2.5 Tres formatos de contenido distintos

1. **Hoja en papel «Acta de partido Alevín/Benjamín» (FVBIB)** — la más común en alevín. Contiene: competición, lugar,
   fecha, hora, equipos local/visitante, **tabla DEPORTISTAS** (nº + apellido, **sin nombre de pila**, capitán marcado
   con «(C)»), **parciales por set**, total, ganador, resultado (p. ej. `3-0`), cuerpo técnico, árbitro, firmas.
   **NO tiene sextetos iniciales ni cambios.** Cada set tiene además una columna de puntos tachados (no leer, no hace falta).
2. **Foto de esa misma hoja, mal orientada** y con mucho fondo (un caso salió girada 90° con el cinturón del coche
   delante). El EXIF no siempre resuelve la orientación → **hay que pedir al modelo que detecte la rotación** o probar
   las 4 rotaciones.
3. **Captura de pantalla de la app de acta digital** (`.png`): títulos tipo «ALEVIN MASCULINO 4X4», parciales, jugadores
   con dorsal, **«Alineación inicial» por set (IV III II / V VI I), sustituciones y tiempos muertos**. Aquí **sí** hay
   sextetos y cambios, y encaja con el esquema de `parse_acta_lineup`.
   El infantil «hoja completa» del ejemplo de la issue (Esporles–Sant Josep, 5 sets con sextetos y cambios) es similar.

> **Consecuencia de diseño:** el esquema de salida debe admitir **sets sin `lineup`**. Con formato 1 solo se puede
> rellenar *convocados + parciales*: sirve para «convocatorias» y «partidos convocado», **no** para «sets como
> titular». Está bien: no inventar datos que el papel no tiene.

---

## 3. Qué hay ya construido (no reinventar)

Todo bajo `ilovevoley/` (paquete raíz). Comandos Django **siempre en Docker**:
`docker compose -f docker-compose.dev.yml run --rm web python manage.py <cmd>` (ver `CLAUDE.md`).

| Pieza | Dónde | Para qué |
|---|---|---|
| Parser del acta HTML | `videos/scraping/acta.py` → `parse_acta_lineup(html)` | **Define el esquema JSON de salida** (§4) |
| Guardado | `competitions/services/lineups.py` → `store_match_lineups(match, data)` | Guarda `Match.acta_data`, `Match.set_scores` y reconstruye `MatchLineup` |
| Marcadores por set | `competitions/services/sets.py` → `extract_set_scores(data, home_name, away_name)` | Lee `sets[].teams[].points` y empareja por nombre |
| Resolución de equipo | `lineups.py` → `resolve_acta_team(name, home, away)` | Casa nombre de acta con local/visitante por palabras |
| Modelo | `competitions/models/competitions.py`: `Match.acta_html` (CharField 200), `Match.acta_data` (JSON), `Match.federation_id` (unique, null), `MatchLineup` | |
| Normalizar URL | `videos/scraping/base.py` → `build_acta_url` | Solo sabe de `acta_html` |
| Scraping resultados | `videos/scraping/federation.py` (`_fetch_round_map`, `enrich_matches_with_json`, líneas ~120, ~389, ~1129, ~1416) y `videos/scraping/parsers.py` (~442, ~493, ~636) | Aquí se captura `acta_html`; **la foto se descarta** |
| Validación de marcador | `validate_volleyball_score(home, away, league)` (regla del proyecto, `CLAUDE.md`) | Antes de marcar un partido finalizado |
| Reintento HTML | #455 (tarea que reintenta actas que fallan) | Debe **dejar de reintentar** los partidos solo-foto |
| Backfill existente | `competitions/management/commands/backfill_acta_lineups.py` | Referencia de cómo se recorre `Match.all_objects` |

Dependencias: `pypdf`, `Pillow`, `pillow-heif`, `requests`, `beautifulsoup4` ya están. **Hay `google-cloud-vision` pero NO el
SDK de Anthropic** (`anthropic`). Añadirlo es **una decisión pendiente** (§7).

---

## 4. Esquema de salida (el contrato)

Mismo JSON que `parse_acta_lineup` (campos a `''`/`[]` si no se leen):

```json
{
  "home_team": "ALGAIDA V.C GROC",
  "away_team": "S'ALTELL CV VILAFRANCA",
  "home_captain": "Crespi",
  "away_captain": "Matas",
  "home_convocados": ["1 Fumero", "11 Gallardo", "15 Vives"],
  "away_convocados": ["1 Salas", "3 Adrover"],
  "sets": [
    {"title": "Set 1", "time": "",
     "teams": [
       {"name": "ALGAIDA V.C GROC", "points": 25, "lineup": []},
       {"name": "S'ALTELL CV VILAFRANCA", "points": 14, "lineup": []}
     ]}
  ],
  "observations": "",
  "home_coach": "", "away_coach": "",
  "referees": ["Juan González"],
  "officials": []
}
```

Reglas del formato (mira `build_match_lineups`):
- `*_convocados` = cadenas `"<dorsal> <apellido>"` (regex `^(\d+)\s+(.+)$`). Sin dorsal legible → se guarda solo el texto.
- `sets[].teams[].lineup` (si existe) = 6 dicts `{"position": "I".."VI", "number": int|null, "sub": {"number": int, "score": "(15-21)"}|null}`.
  **Formato 1 (papel alevín): `lineup: []`.**
- `points` = int. El orden de `teams` no importa: se empareja por **nombre** (`extract_set_scores`).
- **Añadir (nuevo, no existe en el parser HTML):** metadatos fuera del JSON de partido, en el registro de revisión (§5):
  `confidence` (`high|medium|low`), `format` (`paper_alevin|app_screenshot|paper_full`), `notes`.

---

## 5. Diseño propuesto (mínimo, en este orden)

**No guardar nada en `Match.acta_data` ni `MatchLineup` hasta que una persona apruebe.**

### 5.1 Modelo nuevo `MatchActaPhoto` (app `competitions`)
Un registro por partido (OneToOne a `Match`), con:
- `source_url` (URL completa del enlace «Ver Foto Acta», con extensión y mayúsculas tal cual).
- `status`: `pending_download` → `pending_review` → `approved` | `rejected` | `unreadable` | `expired`
  (`expired` = respuesta «El acta no se ha guardado en el servidor»; `unreadable` = HEIC vacío, sin imagen o ilegible).
- `image` (ImageField/FileField, JPEG ya **enderezado y sin EXIF/GPS**; **no guardar el original**, igual que #86).
- `extracted_data` (JSON del §4) · `extraction_meta` (JSON: `confidence`, `format`, `notes`, modelo usado) ·
  `validation_errors` (JSON, lista de textos) · `reviewed_by`, `reviewed_at`.
- Crear con `makemigrations` y **avisar al usuario para que la revise y aplique** (regla suya; no editar migraciones
  existentes ni escribirlas a mano).

### 5.2 Scraping — guardar el enlace (paso más barato y seguro)
- En el parseo de `get_resultados.asp` (ya se recorre para `_fetch_round_map`): al leer cada bloque `info_partido`,
  capturar el `href` con `title='Ver Foto Acta'` **solo si no hay «Ver Acta»** (`acta_html` vacío) y la URL **no** casa con
  `pdf.asp?o=\d+_\d+\.pdf`.
- Guardar en `MatchActaPhoto(source_url=…, status='pending_download')`. Emparejar el partido por la pareja de ids de
  club + jornada (igual que `round_map`) o, si se verifica la hipótesis del §2.1, por `Match.federation_id == número`.
- **Idempotente**: si ya existe, no pisar estados `approved/rejected`.
- Si el partido gana después un acta HTML válida, el HTML manda (la foto pasa a `rejected`/se ignora).

### 5.3 Descarga y preparación (`competitions/services/acta_photo.py`, nuevo)
`fetch_acta_image(source_url) -> bytes | None`:
1. `requests.get(source_url, allow_redirects=True, timeout=…)` con cabecera de navegador (User-Agent normal).
2. Si la respuesta no es `application/pdf` (o el cuerpo no empieza por `%PDF`) → `expired`.
3. `pypdf.PdfReader(...)` → todas las `page.images`; **deduplicar por hash**; ignorar máscaras `SMask`; si no queda ninguna → `unreadable`.
4. Pillow: `ImageOps.exif_transpose`, convertir a RGB, **no copiar EXIF/GPS** al guardar (JPEG limpio), lado largo ≈ **1600 px**
   (a 1600 px se lee bien; no subir de 2000).
5. Sin librería de PDF externa ni poppler.

### 5.4 Lectura con visión (`competitions/services/acta_vision.py`, nuevo)
- Llamada a un modelo con visión con la imagen + un prompt que pida **solo JSON** del §4, indicando:
  detectar la **orientación** (girar si hace falta), el **formato** (1/2/3 del §2.5), `confidence` y `notes`; **no inventar**:
  lo que no se lea, vacío. Pasar los **nombres de los dos equipos y la fecha del partido** como contexto.
- Reintento 1 vez con otra rotación si no parsea JSON. Errores de red/modelo → dejar en `pending_download` (no perder la foto).
- Reglas de coste: una llamada por foto, solo cuando hay estado `pending_download`. Tarea Celery con **`name=` explícito**
  (regla del proyecto) y límite de partidos por ejecución.

### 5.5 Validación automática (obligatoria; si falla → `rejected`/revisión con aviso, nunca aprobada sola)
1. **(Cambiado tras §11)** Los **parciales leídos se comparan set a set con `Match.set_scores`** (la federación ya publica los parciales,
   p. ej. `25-10/25-11/25-11`) y con el resultado. Además cumplen las reglas de voleibol (usar la lógica de `validate_volleyball_score` / `extract_set_scores`).
2. El **número de sets ganados** por cada equipo coincide con el **resultado del partido** (`Match.home_score/away_score`).
3. La **suma de puntos** coincide con el «TOTAL» leído, si se leyó.
4. Los **dorsales** de convocados son enteros 0–99, sin repetidos dentro del mismo equipo.
5. Los dos nombres de equipo casan con los del partido (`resolve_acta_team`); fecha leída ≈ fecha del partido (±2 días).
Si 2 o 3 fallan → estado `rejected` con `validation_errors` (sirve para depurar el prompt).

### 5.6 Pantalla de revisión
- Vista solo para quien tenga permiso de moderación (ver patrón de `/core/moderacion/` y `can_edit_*`), en el tenant.
- **Foto a la izquierda, datos editables a la derecha** (convocados, parciales; en formato 3 también sextetos).
  Foto ampliable. Mostrar `confidence` y `notes` y los `validation_errors`.
- Botones **Aprobar** (revalida §5.5 con lo editado → `store_match_lineups(match, data)` → `approved`) y **Rechazar**.
- Textos en **castellano** y traducir al catalán (`makemessages -l ca`). `{% trans %}` dentro de `<script>` con `as x` + `|escapejs`.

### 5.7 Cambio en #455
La tarea que reintenta actas por la vía HTML **debe saltarse** los partidos con `MatchActaPhoto` (cualquier estado) y sin `acta_html`.

---

## 6. Orden de trabajo para el siguiente agente

0. **Verificar la hipótesis del ID** (barato): con el CSV, coger 3-4 filas con `match_id_guess` y comprobar si existe un
   `Match` con ese `federation_id` en la BD local/producción. Si coincide, se usa; si no, se empareja por club+jornada.
1. Scraping + modelo `MatchActaPhoto` (§5.1–5.2) → `makemigrations` → **parar y avisar para que apliquen la migración**.
2. `fetch_acta_image` (§5.3) con **tests** sobre los 4 casos reales de §2.4 (jpeg, jpg 2 páginas, png con alfa, HEIC vacío) y el texto de «caducado».
3. Lectura con visión (§5.4) detrás de un setting `ACTA_VISION_ENABLED` (por defecto `False`).
4. Validación (§5.5) con tests de las reglas de negocio.
5. Pantalla de revisión (§5.6) + cambio de #455 (§5.7).

Cada paso es entregable por separado. **No hace falta terminar todos para que el 1 sea útil.**

### Cómo obtener muestras reales para probar
```bash
mkdir -p /ruta/fuera/del/repo/muestras && cd /ruta/fuera/del/repo/muestras
curl -sL -o a.pdf "https://www.voleibolib.net/pdf.asp?o=81768.jpeg"      # alevín, JPEG limpio, 1 página
curl -sL -o b.pdf "https://www.voleibolib.net/pdf.asp?o=81772.jpg"       # alevín, foto girada, 2 páginas
curl -sL -o c.pdf "https://www.voleibolib.net/pdf.asp?o=81807.png"       # captura de app, PNG recomprimido
curl -sL -o d.pdf "https://www.voleibolib.net/pdf.asp?o=81669.HEIC"      # PDF sin imagen
curl -sL      "https://www.voleibolib.net/pdf.asp?o=1780153395_6042.pdf"  # texto: «El acta no se ha guardado…»
```
⚠️ **No commitear fotos reales de actas**: llevan nombres y firmas de menores y de árbitros. Los tests deben usar imágenes
sintéticas generadas con Pillow/pypdf, no actas reales.

---

## 7. Decisiones pendientes (las toma el usuario, no el agente)

1. **¿Qué modelo con visión?** **Presupuesto del proyecto: prácticamente nulo → priorizar gratis/barato.** Como la
   revisión humana (§5.6) es obligatoria y la validación (§5.5) descarta lo incoherente, **un modelo peor solo cuesta más
   rato de revisión, no datos erróneos**. Por eso un modelo gratuito es aceptable. Opciones, de más a menos recomendable
   (búsqueda del 2026-10-09; los límites y condiciones cambian, **verificar en la consola/ToS antes de depender de ellos**):
   - **A. Modelo local con Ollama en el Mac del usuario** (`qwen3-vl:8b`; alternativas a probar: Gemma 4 pequeño, GLM-OCR).
     Coste 0 €, **privado** (las fotos no salen del Mac), sin límites. Pega: más lento, la letra a mano peor que en modelos
     de pago (hay quien reporta que «tiende a corregir el texto»; usar prompt fijo de «transcribe, no corrijas») y consume
     RAM/CPU del Mac. Encaja si el proceso es **por lotes manual** (`manage.py`), no una tarea Celery en producción.
   - **B. Gemini API, nivel gratuito, modelo Flash-Lite/Flash** (REST con `requests`, **sin dependencia nueva**).
     Gratis con límites por minuto/día (las fuentes discrepan: ~15-30 peticiones/min); sobra para unas pocas actas por
     jornada. ⚠️ **En el nivel gratuito Google puede usar el contenido para mejorar sus productos** (no aplica en UE/UK/CH
     según una fuente → comprobar). Las fotos llevan apellidos de menores y firmas: decidir si es aceptable.
   - **C. Claude (`anthropic`)**: el más fiable, **de pago**, y añade dependencia + clave API. Solo si A y B no rinden.
   - **Descartado: el servidor de producción (`ilovevoley.es`).** HP ProLiant con **Celeron G1610T (2 núcleos, sin AVX/AVX2/FMA,
     solo SSE4.2), 11 GB de RAM con ~2 GB de swap ya en uso y sin GPU**, compartido con la web, Celery, Postgres, Jellyfin y el
     stack *arr. `/opt/ollama-openwebui` tiene Ollama parado con solo modelos de texto (llama3.1/3.2, mistral, phi3,
     tinyllama; sin visión). Un modelo de visión ahí sería inutilizable y pondría en riesgo la web. **No levantarlo.**
   **Ninguna de las tres está probada con nuestras actas.** Hacer una **prueba comparativa con las 4 muestras reales de
   `.local/actas-2025-26/samples/`** (ver §9) antes de elegir. Diseño: una sola función
   `read_acta(image_bytes, context) -> dict` en `acta_vision.py` y el proveedor elegido por setting; **no** montar un
   framework de proveedores.
   Fuentes: [Gemini free tier](https://tinkerllm.com/blog/gemini-api-free-tier-limits-rate-quotas/),
   [cambios abril 2026](https://agentdeals.dev/gemini-api-pricing-changes),
   [handwriting local](https://www.autodidacts.io/usable-local-ai-handwriting-recognition.md),
   [GLM-OCR en Mac](https://www.buildwithmatija.com/blog/run-glm-ocr-macbook-ollama).
2. **¿Se construye ya o se espera?** La issue pedía esperar a ver cuántas actas manuales salían esta temporada
   (la liga infantil empieza la semana del 2026-10-12). Con ~945 solo-foto el año pasado, el usuario decidió **dejarlo preparado**.
3. **Alevín (formato 1):** ¿se aprueba que se guarde solo *convocados + parciales* (sin sets como titular)? Recomendado: sí.

---

## 8. Reglas del proyecto que NO se pueden saltar

- **Git:** no `commit`, `push` ni PR sin que el usuario lo pida. Antes de cada commit hay que preguntar `@time` y número de issue
  (excepción: en este repo la memoria del usuario permite commits por fases sin preguntar; ante la duda, preguntar).
  `git push` en foreground, sin tuberías.
- **Migraciones:** `makemigrations` y avisar; **no** editar las existentes **ni** escribirlas a mano. Backfills = migración
  `RunPython`, no management command. Tests con `--create-db`.
- **Tests:** antes de escribir uno, justificarlo según `docs/ai-guidelines/testing-guidelines.md` (protege una regla de negocio,
  una transformación no trivial, idempotencia/rollback…). No tests que solo comprueben `status_code` o que mockeen todo.
- **Logging:** nada de `logger.info`/`print`/`.debug(` por defecto. Errores reales: `logger.warning/error`.
- **Código en inglés, comunicación/docs en castellano.** Nunca el prefijo `ponytail:` en comentarios.
- **Celery:** toda tarea con `name=` explícito; no quitarlo.
- **Privacidad:** quitar **EXIF y GPS** de la imagen guardada; no guardar el original.
- **Temporadas:** `Season.objects.current()`; **partidos:** `Match.all_objects` si hay que incluir `withdrawn`.
- Docker para todo comando Django; no usar `docker-compose.dev.yml` en producción.

---

## 9. Material ya descargado (no volver a bajarlo)

En el worktree, carpeta **`.local/actas-2025-26/`** (excluida de git vía `.git/info/exclude`; **no commitear**, hay datos de menores):

| Fichero | Qué es |
|---|---|
| `scan.json` | Barrido completo de 1908 partidos (alevín+infantil 2025-26): equipos, parciales, enlaces `acta`/`foto`, HTML crudo del bloque |
| `menu2526.html` | Menú de competiciones `temp=2526` (ids de liga) |
| `desglose.json` | Muestra del JSON unificado (`ID`, `acta_html`; sin foto) |
| `samples/*.pdf` | 4 PDF reales ya descargados: `alevin_jpeg` (papel, limpio), `alevin_jpg` (papel girado, 2 págs), `alevin_png` (captura app, PNG+alfa), `alevin_heic` (sin imagen) |
| `samples/img_*` | Imágenes ya extraídas de esos PDF con `pdfimages` |
| `samples/inf_pdf.bin` | La respuesta de texto «El acta no se ha guardado en el servidor» |

Para descargar más fotos concretas: filas del CSV de esta carpeta (`foto_url`), **con pausa de ≥1 s entre peticiones**
(la federación responde lento; el barrido completo tardó ~35 min).
Prueba comparativa de modelos: pasar `img_alevin_jpeg-000.jpg` y `img_alevin_jpg-000.jpg` (girada) y `img_alevin_png-000.png`
y comparar con la lectura manual: convocados con dorsal, parciales por set, resultado, capitán.

---

## 10. Resultado de la prueba con Gemini gratuito (2026-10-09)

Prueba: `gemini-3.5-flash-lite`, nivel gratuito, clave de un proyecto de AI Studio sin facturación, 3 imágenes de §9, `temperature 0`,
`responseMimeType: application/json`. Script y respuestas en `.local/actas-2025-26/gemini_test.py` y `gemini_out_3.5-flash-lite.json`.
Llamada REST con `requests` (`POST …/v1beta/models/<modelo>:generateContent`, cabecera `x-goog-api-key`), **sin dependencia nueva**.

- **Modelos 2.5 (`flash`, `flash-lite`) devuelven 404 «no disponible para usuarios nuevos»**. Usar 3.x. `gemini-3.8-flash` **no se probó**.
- Coste/tiempo por foto: ~1300 tokens de entrada, ~420 de salida, **2-3 s**.
- **Orientación y formato: acertó en las 3** (detectó `rotation_degrees_needed: 270` en la foto girada; `paper_alevin` / `app_screenshot`).
- **Parciales por set y resultado: 3/3 correctos** (25-10, 25-11, 25-11 · 13-25, 7-25, 7-25 · 24-26, 17-25, 18-25). Es lo que valida §5.5.
- **Sextetos de la captura de app: correctos** en los 3 sets (no leyó las sustituciones; no estaban en el esquema del prompt).
- **Errores observados (todos de lectura a mano, los atraparía la revisión humana):**
  un dorsal mal (42 leído como 47); un apellido mal («Morey» → «Norey», «Geuss» → «Gelabert»);
  en la foto girada mezcló **lugar/cancha con el nombre del equipo** («MARRATXI PORTOL», «P. BLANQUERNA ALGAIDA» en vez de «PORTOL»/«ALGAIDA»)
  y tomó los nombres de la firma como capitanes. → Pedir en el prompt: «el equipo es el de la fila EQUIPO LOCAL/VISITANTE, no el lugar
  ni la cancha», y **casar el equipo con `resolve_acta_team` y los nombres del partido en vez de fiarse del texto leído**;
  pasar los dos equipos del partido como contexto.
- **Conclusión:** viable para el flujo «modelo propone → humano revisa → guardar». Los números que se validan automáticamente salen bien;
  los nombres y dorsales necesitan revisión. **Muestra pequeña (3 imágenes): repetir con ~10 actas variadas antes de dar por buena la precisión.**
- ⚠️ La clave se pegó en la conversación: **rotarla en AI Studio** al terminar. No guardarla en el repo (usar variable de entorno).


---

## 11. Segunda prueba: 9 actas variadas (Gemini gratuito) — el modelo se equivoca mucho en los parciales

Muestra: 9 fotos reales al azar (seed 7) de `scan.json` sin acta HTML: 4 alevín y 5 infantil (`.jpg`/`.jpeg`/`.png`); una décima (`04`) ya estaba
**caducada** («El acta no se ha guardado…»). Verdad de referencia = parciales que publica la federación (`scan.json`). Scripts y salidas en
`.local/actas-2025-26/gemini_batch.py` y `batch2/out_*.json`. Se pasó al modelo el nombre de local/visitante como contexto.

| Modelo | Parciales exactos | Notas |
|---|---|---|
| `gemini-3.5-flash-lite`, imagen a 1600 px | **2 / 9** | 3-5 s por foto |
| `gemini-3.5-flash-lite`, imagen a 2400 px | **3 / 9** | 2-4 s; mejora algo, no lo resuelve |
| `gemini-3.8-flash`, 1600 px | 2 / 4 respondidas | **5 de 9 llamadas dieron 503** («alta demanda») y las respondidas tardaron 36-163 s |

- **El campo `confidence` es inútil:** el modelo contestó `"high"` en las 27 lecturas, también cuando se equivocaba. **No usarlo para decidir nada.**
- Errores graves incluso en papel limpio y legible (acta 02: leyó 25-25 donde ponía 10-25). Los valores inventados a veces ni son marcadores válidos (15-14).
- **Orientación:** detecta que la foto está girada, pero el ángulo no es fiable entre ejecuciones (la misma foto salió 270, 90 y 180).
- **Las hojas de infantil «completas» (FIVB, 5 sets con sextetos, turnos, cambios) son mucho más densas** que la hoja alevín; con este modelo no se pueden leer de forma fiable.
- **Convocados:** solo se pudo comprobar el nº de filas (coincide en las claras); la exactitud de dorsales/apellidos **no está medida** a escala.
- **Resultado oficial ≠ papel:** en la acta 06 el papel dice 3-1 pero la federación publicó 0-3 con 0-25 ×3 por una sanción (observaciones del delegado).
  El papel no manda sobre el resultado oficial. Usar `is_penalty_result` y **no descartar** esos casos: marcarlos «resultado sancionado, revisar».
  Nunca sobrescribir `Match.set_scores` oficial con lo leído.

### Qué cambia en el diseño
1. **La federación ya da los parciales y el resultado → no necesitamos que el modelo los lea.** Sirven como **comprobación fuerte**: cualquier lectura que
   no case set a set con `Match.set_scores` se marca/descarta (habría atrapado las 6-7 lecturas erróneas de arriba). Pasar los parciales conocidos
   en el prompt como contexto (ayuda a orientar y a validar), pero tratarlos como verdad, no como salida.
2. **El valor real que aporta el modelo son los convocados** (dorsal + apellido) y, en capturas de app / hojas completas, los sextetos. Medir **solo eso**.
3. **La revisión humana no es opcional**: con este nivel de precisión, la pantalla de revisión (§5.6) es el control principal, no un extra.
4. Reintentos para 503/429: backoff y «reintentar en la siguiente ejecución»; nunca perder la foto.

### Experimentos pendientes (baratos) antes de decidir modelo
- Pedir **solo la tabla DEPORTISTAS recortada** (recorte fijo de la hoja alevín, que siempre es igual) y a mayor resolución; probable mejora grande.
- Otros modelos gratuitos disponibles en la clave: `gemini-3.7-flash`, `gemini-3.6-flash`, `gemini-flash-latest`.
- **Ollama local en el Mac** (`qwen3-vl:8b`) con la misma muestra.
- Medir exactitud de convocados a mano en ~5 fotos (contar dorsales/apellidos correctos).


---

## 12. Alcance y flujo acordados (prevalece sobre §5/§6)

**Decisión del usuario:** leer y procesar **solo los partidos de los tenants**. Hoy: 3 equipos con familias registradas + 2 alevines que se rellenan por si
a alguien le interesa. Estimación: ~2 partidos alevín seguros a la semana y, con suerte, 0 de infantil/cadete/juvenil. **Volumen mínimo → coste cero y revisión corta.**

### 12.1 Qué cambia respecto a §5
1. **Alcance (sustituye a §5.2):** solo crear `MatchActaPhoto` (y solo llamar al modelo) si el partido es de un equipo de algún tenant:
   `Match.objects.for_tenant(tenant)` (ver `ilovevoley/core/tenancy.py` y `MatchTenantQuerySet` en `competitions/models/competitions.py`) para cada `Organization` activa.
   El resto de las ~945 actas del año pasado **no se procesan**. Beneficios: coste cero con el nivel gratuito y **menos fotos de menores enviadas a Google**.
2. **El modelo propone, la persona corrige y valida.** Es el flujo principal, no un extra. Ejemplo del usuario: la foto dice «1 Pérez, 2 López, 3 García, 4 Sánchez»,
   el modelo lee «2 Lepe», «3 Gracia» → el revisor corrige, valida y se guarda.
3. **Lo que importa para las estadísticas es el DORSAL, no el apellido.** `build_match_lineups` resuelve la persona por `(team, jersey_number)` contra `PlayerRole`
   de la temporada; el apellido solo va a `name_acta`. Por tanto un «Lepe» por «López» no rompe nada si el dorsal está bien. **El revisor debe vigilar dorsales y
   que no falte/sobre ninguno.**
4. **Rellenar los nombres desde la plantilla (equipos propios):** al preparar la pantalla de revisión y al construir el prompt, usar la plantilla del equipo del tenant
   (`PlayerRole` con `jersey_number` de la temporada, ver `_roles_lookup` en `competitions/services/lineups.py`):
   - En el prompt, para el equipo propio, pasar la lista `dorsal → apellido` conocida y pedir que **solo corrija/confirme** (no que invente): reduce los errores «Lepe/López».
   - En la pantalla, mostrar por fila: dorsal leído · apellido leído por el modelo · **apellido de la plantilla para ese dorsal** · indicador si no coinciden
     (acción de un clic «usar el de la plantilla»). Para el rival no hay plantilla: lo leído tal cual, editable.
5. **Pantalla de comprobación (§5.6) con enlace directo:** cada `MatchActaPhoto` en `pending_review` debe tener una URL estable (p. ej. `/competiciones/actas-foto/<id>/revisar/`)
   y, ideal, un aviso al usuario revisor (lista de pendientes en el panel de moderación `/core/moderacion/`, o una notificación existente) para llegar al enlace sin buscarlo.
   Foto a un lado, filas editables al otro, parciales de la federación (`Match.set_scores`) visibles como referencia, botón **Aprobar** (→ `store_match_lineups`) / **Rechazar**.
6. **Parciales:** no se piden al modelo como dato (ver §11). Se muestran los oficiales de la federación y se usan para validar; si el modelo los lee y no coinciden,
   se **ignora su lectura** y se avisa, sin bloquear la revisión del resto.
7. **Reintentos y límites:** con este volumen el nivel gratuito sobra. Aun así, backoff ante 503/429 y dejar la foto en `pending_download`/`pending_read` para la siguiente ejecución.

### 12.2 Orden de trabajo revisado (cada paso entregable)
0. Verificar hipótesis del ID del partido (§6.0) con partidos de un tenant real.
1. Scraping: guardar el enlace «Ver Foto Acta» **solo para partidos de tenants sin acta HTML** + modelo `MatchActaPhoto` (+ `makemigrations`, parar y avisar).
2. Descarga/extracción de imagen (§5.3) — también cubre `.png`, 2 páginas, HEIC vacío y «caducada».
3. Lectura con Gemini gratuito (§10/§11) con plantilla del equipo propio en el prompt; `ACTA_VISION_ENABLED=False` por defecto; clave por variable de entorno.
4. Pantalla de revisión con foto + comparación con plantilla + enlace estable (§12.1.4-5).
5. Cambio de #455 (dejar de reintentar estos partidos por la vía HTML).

### 12.3 Qué NO hace falta construir (por el volumen)
Cola masiva, lotes paralelos, métricas de precisión, reentrenamiento, soporte para las ~945 actas históricas, ni elegir entre varios proveedores de visión: **una función, un modelo gratuito**.
Si el modelo falla en una foto, el revisor puede **teclear los convocados a mano** en la misma pantalla (la foto ya está al lado): esa ruta debe funcionar sin modelo.
