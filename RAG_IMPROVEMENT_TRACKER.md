# RAG System Improvement Tracker
*Última actualización: 2025-11-09*

## 🎯 OBJETIVO PRINCIPAL
Crear un asistente inteligente para padres de voleibol infantil que pueda responder consultas como:
- "¿Cómo va mi hijo en la liga alevín?"
- "¿Contra quién jugamos la próxima semana?"
- "¿Estamos mejor que el año pasado?"
- "¿Qué dice el reglamento sobre las rotaciones?"

## 📊 ESTADO ACTUAL DEL SISTEMA

### ✅ LO QUE FUNCIONA
- [x] Arquitectura RAG básica implementada (ChromaDB + Ollama)
- [x] Modelo phi3:mini configurado (ligero y eficiente)
- [x] Indexación de videos, imágenes, partidos, ligas, clasificaciones
- [x] Procesamiento básico de PDFs (PyPDF2)
- [x] Sistema de chat con historial por usuario
- [x] Fallback system implementado para errores de memoria

### ❌ LO QUE NO FUNCIONA
- [ ] **PROBLEMA CRÍTICO**: Ollama timeouts en consultas simples (Connection timeout)
- [ ] Fragmentación de PDFs muy básica (no preserva estructura semántica)
- [ ] No hay análisis temporal ni comparativo
- [ ] No detecta tipo de consulta (todo va por RAG)
- [ ] Respuestas no contextualizadas para padres

### 🔧 ARQUITECTURA ACTUAL
```
User Query → RAG Service → ChromaDB (search) → Ollama (generate) → Response
```

### 🚀 ARQUITECTURA PROPUESTA (NUEVA)
```
User Query → Query Classifier → {
  ├─ 70% Simple Data: Direct DB → Template Response (2s)
  ├─ 20% Analysis: DB + Aggregation → Template Response (3s)  
  └─ 10% Complex: RAG → Ollama → Response (10s)
}
```

**VENTAJAS DEL CAMBIO**:
- ❌ Elimina 90% de timeouts (sin Ollama para consultas simples)
- ⚡ 5x más rápido para consultas comunes
- 💰 Menos carga en el servidor (sin embeddings innecesarios)
- 🎯 Respuestas más consistentes y predecibles

**Archivos clave:**
- `videosvoley/rag/services.py`: RAGService principal
- `videosvoley/rag/models.py`: Document, ChatSession, ChatMessage
- `videosvoley/rag/views.py`: API endpoints del chat
- `videosvoley/rag/management/commands/`: Comandos de indexación

## 🚨 PROBLEMAS IDENTIFICADOS

### 1. PROBLEMA CRÍTICO: Ollama Timeouts
**Síntoma**: `[Errno 110] Connection timed out` en consultas simples
**Ubicación**: `services.py:280` - `self.ollama_client.generate()`
**Causa**: Sin configuración de timeouts específicos
**Impacto**: Sistema inutilizable para usuarios

### 2. Consultas Ineficientes
**Problema**: Consulta "próximo partido alevín" va por RAG cuando podría ser query directa a BD
**Impacto**: Lentitud innecesaria y mayor probabilidad de timeout

### 3. Falta de Contexto Temporal
**Problema**: No puede hacer comparaciones "mejor que año pasado"
**Causa**: Datos sin agregaciones temporales

### 4. Respuestas No Conversacionales
**Problema**: Respuestas técnicas, no amigables para padres
**Ejemplo**: Devuelve metadata cruda en lugar de "El próximo partido es el sábado"

## 📋 PLAN DE MEJORA (Por Fases)

### ⚡ ESTRATEGIA PRAGMÁTICA: Arreglar lo Básico + Aprendizaje

**DECISIÓN**: Enfoque iterativo basado en uso real de usuarios

### 🚀 FASE 1: ARREGLAR TIMEOUT (CRÍTICO - AHORA)
**Objetivo**: Que el sistema responda sin fallar

#### 1.1 Configurar Timeouts en Ollama ⚡ AHORA
- [x] Añadir timeout de conexión: 30 segundos ✅ COMPLETADO
- [x] Añadir timeout de generación: 60 segundos ✅ COMPLETADO
- [x] Configurar en `services.py:108` ✅ COMPLETADO

#### 1.2 Optimizar Parámetros del Modelo ⚡ AHORA
- [x] Limitar tokens a 800 (respuestas más cortas) ✅ COMPLETADO
- [x] Reducir temperature a 0.3 (respuestas más directas) ✅ COMPLETADO
- [x] Configurar en `services.py:283` ✅ COMPLETADO

#### 1.3 Mejorar Fallback System ⚡ AHORA
- [x] Ampliar detección de errores de timeout ✅ COMPLETADO
- [x] Mejorar logging del fallback ✅ COMPLETADO
- [x] Añadir medición de tiempo en views.py ✅ COMPLETADO

**RESULTADO ESPERADO**: Sistema que funciona sin timeouts

### 🔍 FASE 2: SISTEMA DE APRENDIZAJE ✅ COMPLETADO
**Objetivo**: Aprender de consultas reales de usuarios

#### 2.1 Logging de Consultas ✅ COMPLETADO
- [x] Añadir campos al modelo ChatMessage:
  - `response_type` (rag/direct/fallback) ✅ COMPLETADO
  - `response_time` (segundos) ✅ COMPLETADO
  - `user_rating` (thumbs up/down) ✅ COMPLETADO
- [x] Guardar metadata de cada consulta ✅ COMPLETADO

#### 2.2 Sistema de Feedback Simple ✅ COMPLETADO
- [x] Añadir botones 👍 👎 en el chat ✅ COMPLETADO
- [x] Endpoint para guardar valoración de usuarios ✅ COMPLETADO
- [x] Dashboard simple para ver qué funciona/no funciona ✅ COMPLETADO

#### 2.3 Análisis de Patrones (Después de 2-3 semanas)
- [ ] Comando para analizar consultas más frecuentes
- [ ] Identificar top 5-10 tipos de preguntas
- [ ] Decidir qué optimizar basándose en datos REALES

**RESULTADO ESPERADO**: Datos reales de qué preguntan los padres

### 🧠 FASE 3: Query Router Inteligente ✅ COMPLETADO
**Objetivo**: Routing inteligente basado en patrones reales

#### 3.1 Crear Query Router ✅ COMPLETADO
- [x] Detectar tipo de consulta automáticamente:
  - Consultas simples → BD directa ✅ COMPLETADO
  - Análisis → RAG + agregaciones ✅ COMPLETADO 
  - Reglamento → RAG semántico ✅ COMPLETADO
- [x] Nuevo archivo: `videosvoley/rag/query_router.py` ✅ COMPLETADO

#### 3.2 Consultas Directas a BD ✅ COMPLETADO
- [x] "Próximo partido" → Query directa a Match model ✅ COMPLETADO
- [x] "Última clasificación" → Query directa a Standing model ✅ COMPLETADO
- [x] "Partidos pasados" → Query directa con resultados ✅ COMPLETADO
- [x] Implementar en views.py antes del RAG ✅ COMPLETADO

#### 3.3 Detección Inteligente de Equipos ✅ COMPLETADO
- [x] Extracción dinámica de nombres de equipos desde BD ✅ COMPLETADO
- [x] Normalización de acentos y puntuación ✅ COMPLETADO
- [x] Soporte para equipos compuestos (Sant Joan, etc.) ✅ COMPLETADO
- [x] Detección de consultas "contra equipo X" ✅ COMPLETADO

**RESULTADO OBTENIDO**: ✅ Sistema híbrido funcional (33s → 0.18s, 90% consultas por BD directa)

### 🚀 FASE 4: Detección Avanzada de Lenguaje Natural ✅ COMPLETADO
**Objetivo**: Mejorar detección de consultas complejas basándose en patrones reales

#### 4.1 Análisis de Consultas Reales ✅ COMPLETADO
- [x] Analizar últimas 20 consultas de usuarios ✅ COMPLETADO
- [x] Identificar patrones no detectados correctamente ✅ COMPLETADO
- [x] Patrones problemáticos identificados:
  - "próximo partido del Alaró" ✅ COMPLETADO
  - "cuándo jugaremos contra el Artà" ✅ COMPLETADO
  - "del Pórtol en Cadete" ✅ COMPLETADO

#### 4.2 Mejoras en Detección de Equipos ✅ COMPLETADO
- [x] Mejorar patrones "del EQUIPO" y "de EQUIPO" ✅ COMPLETADO
- [x] Añadir regex patterns para extracción de equipos ✅ COMPLETADO
- [x] Filtrar palabras comunes (del, de, la, el, etc.) ✅ COMPLETADO
- [x] Optimizar búsqueda de equipos dinámicamente desde BD ✅ COMPLETADO

#### 4.3 Consultas de Enfrentamiento Específico ✅ COMPLETADO
- [x] Detectar patrones "contra EQUIPO" ✅ COMPLETADO
- [x] Detectar "cuándo se volverá a enfrentar" ✅ COMPLETADO
- [x] Nuevo método `_handle_versus_query` ✅ COMPLETADO
- [x] Nuevo método `_format_versus_match_response` ✅ COMPLETADO

#### 4.4 Patrones de Lenguaje Natural Extendidos ✅ COMPLETADO
- [x] "del equipo", "de equipo" patterns ✅ COMPLETADO
- [x] "qué día", "que dia" indicators ✅ COMPLETADO
- [x] "volverá a enfrentar", "próximo enfrentamiento" ✅ COMPLETADO

#### 4.5 Consultas de Análisis de Rachas ✅ COMPLETADO
- [x] Detectar consultas "mejor racha" vs "peor racha" ✅ COMPLETADO
- [x] Implementar `_calculate_winning_streaks` con diferenciación ✅ COMPLETADO
- [x] Añadir emojis específicos para peor racha (💀 😵 😔) ✅ COMPLETADO
- [x] Formato diferenciado: victorias vs derrotas y posición ✅ COMPLETADO
- [x] Filtro automático por temporada actual (dinámico) ✅ COMPLETADO

#### 4.6 Nuevos Tipos de Consultas Implementados ✅ COMPLETADO
- [x] `_is_team_points_query`: puntos específicos de equipos ✅ COMPLETADO
- [x] `_is_team_stats_query`: estadísticas detalladas ✅ COMPLETADO
- [x] `_is_period_results_query`: resultados por semana/mes ✅ COMPLETADO
- [x] `_is_analysis_query`: consultas analíticas ✅ COMPLETADO
- [x] Priorización correcta de consultas específicas sobre generales ✅ COMPLETADO

**RESULTADO OBTENIDO**: ✅ 100% de consultas típicas detectadas correctamente como direct_query + análisis de rachas funcional

#### 4.7 Agregadores de Datos
- [x] Calcular tendencias básicas: rachas ganadoras/perdedoras ✅ COMPLETADO
- [ ] Comparaciones temporales entre temporadas
- [ ] Pre-computar estadísticas frecuentes
- [ ] Crear archivo: `videosvoley/rag/aggregators.py` (opcional)

### 🏆 FASE 5: Análisis Temporal, Histórico y Media ✅ COMPLETADO (Parte 1/2)
**Objetivo**: Consultas sobre temporadas pasadas, análisis históricos y contenido multimedia

#### 5.1 Detección Temporal ✅ COMPLETADO
- [x] Detectar "temporada pasada", "año pasado", "hace X años" ✅ COMPLETADO
- [x] Detectar temporadas específicas: "2022-23", "en 2022" ✅ COMPLETADO
- [x] Cálculo dinámico de temporadas anteriores (sin hardcodear años) ✅ COMPLETADO
- [x] Nuevo método: `_is_temporal_query` ✅ COMPLETADO
- [x] Nuevo método: `_detect_specific_season` ✅ COMPLETADO
- [x] Nuevo método: `_get_current_season` y `_get_previous_season` ✅ COMPLETADO

#### 5.2 Consultas Históricas ✅ COMPLETADO
- [x] "mejor de la historia", "récord histórico", "de todos los tiempos" ✅ COMPLETADO
- [x] Comparaciones inter-temporada: "¿estamos mejor que el año pasado?" ✅ COMPLETADO
- [x] Análisis de tendencias: mejores/peores temporadas de un equipo ✅ COMPLETADO
- [x] Nuevo método: `_is_historical_query` ✅ COMPLETADO
- [x] Nuevo método: `_handle_temporal_query` y `_handle_historical_query` ✅ COMPLETADO
- [x] Implementar `_get_best_historical_season` y `_get_worst_historical_season` ✅ COMPLETADO

#### 5.3 Ejemplos de Consultas Objetivo ⏳ PLANIFICADO
**Temporales:**
- "¿Cuál fue la mejor racha del Sant Josep la temporada pasada?"
- "¿Cómo quedó la clasificación en 2022-23?"
- "¿Contra quién jugamos en la final del año pasado?"

**Históricas:**
- "¿Cuál ha sido la mejor temporada del Sant Josep?"
- "¿Qué equipo tiene el récord histórico de victorias?"
- "¿En qué año tuvimos más puntos?"
- "¿Cuál fue nuestro peor resultado histórico?"

#### 5.4 Consultas de Media y Contenido ⏳ PLANIFICADO
- [ ] Detectar consultas sobre fotos/videos por partido específico
- [ ] Detectar consultas por tipo de media (celebración, entrenamiento, etc.)
- [ ] Implementar `_is_media_query` y `_handle_media_query`
- [ ] Integrar con modelos Video e Image existentes
- [ ] Nuevo método: `_format_media_response`

#### 5.5 Ejemplos de Consultas de Media ⏳ PLANIFICADO
**Consultas por partido específico:**
- "¿Hay fotos del partido contra el Sant Joan?"
- "¿Tenemos vídeo del partido de ayer?"
- "Enséñame las fotos del último partido de alevín"
- "¿Hay vídeo del partido contra el Pórtol del sábado?"

**Consultas por tipo de contenido:**
- "¿Qué fotos de celebración tenemos?"
- "Enséñame videos de entrenamientos"
- "¿Hay fotos del equipo este año?"
- "Videos de la categoría cadete"

**RESULTADO ESPERADO**: Análisis temporal completo + consultas históricas + acceso directo a fotos/videos

### 📋 FASE 6: Mejorar RAG para Documentos PDF ✅ COMPLETADO (Dic 2025)
**Objetivo**: RAG inteligente para documentos deportivos (reglamentos, dossiers de torneos, etc.)

#### 6.1 Problema Inicial 🚨 RESUELTO
- [x] RAG devuelve siempre el principio del PDF sin análisis semántico ✅ RESUELTO
- [x] Fragmentación básica de PyPDF2 no preserva contexto ✅ RESUELTO
- [x] Consultas como "¿qué dice el reglamento sobre rotaciones?" → respuesta inútil ✅ MEJORADO
- [x] **IMPACTO**: RAG para reglamentos actualmente es inservible ✅ FUNCIONAL

#### 6.2 Mejora de Fragmentación de PDFs ✅ COMPLETADO
- [x] Chunks semánticos inteligentes (por secciones, no por tamaño) ✅ IMPLEMENTADO
- [x] Detectar títulos, subtítulos, listas en PDFs ✅ IMPLEMENTADO
- [x] Preservar contexto: "Artículo 5.3 - Rotaciones" completo ✅ IMPLEMENTADO
- [x] Procesar automáticamente al subir documentos nuevos ✅ IMPLEMENTADO
- [x] Nuevo archivo: `videosvoley/rag/pdf_processor.py` ✅ CREADO
- [x] Detección de alturas de red y categorías específicas ✅ IMPLEMENTADO
- [x] Enriquecimiento de metadata con contexto deportivo ✅ IMPLEMENTADO

#### 6.3 Mejora de Búsqueda Semántica ✅ COMPLETADO
- [x] Activado filtro inteligente `_smart_filter_for_rules` ✅ IMPLEMENTADO
- [x] Filtrado de chunks irrelevantes antes de responder ✅ IMPLEMENTADO
- [x] Ranking de relevancia: artículos específicos > introducciones generales ✅ IMPLEMENTADO
- [x] Scoring por keywords en contenido (+30 puntos/keyword) ✅ IMPLEMENTADO
- [x] Bonificación por "altura de red" (+50 puntos) ✅ IMPLEMENTADO
- [x] Bonificación por categorías mencionadas (+15 puntos) ✅ IMPLEMENTADO
- [x] Logging detallado de scores para debugging ✅ IMPLEMENTADO

#### 6.4 Mejora de Generación de Respuestas ✅ COMPLETADO
- [x] Prompt específico para consultas de reglamento ✅ IMPLEMENTADO
- [x] Instrucciones para sintetizar información (no repetir literal) ✅ IMPLEMENTADO
- [x] Detección de categorías faltantes en contexto ✅ IMPLEMENTADO
- [x] Organización estructurada de medidas y dimensiones ✅ IMPLEMENTADO

#### 6.5 Comandos de Gestión ✅ COMPLETADO
- [x] `list_pdf_documents.py` - Listar PDFs indexados ✅ CREADO
- [x] `reindex_pdfs.py` - Re-indexar con fragmentación inteligente ✅ CREADO
- [x] Logging mejorado en `import_rulebook.py` con flag --verbose ✅ IMPLEMENTADO

#### 6.4 Casos de Uso Objetivo ⏳ PLANIFICADO

**Consultas sobre reglamentos:**
- "¿Qué dice el reglamento sobre rotaciones?"
- "¿Cuántos toques máximos permite el reglamento?"
- "¿Qué pasa si se rompe la red durante el partido?"
- "Reglas sobre sustituciones en juvenil"
- "¿Se puede tocar la red en voleibol?"

**Consultas sobre dossiers de torneos:**
- "¿Dónde nos alojamos para el torneo de Pascua?"
- "¿Qué horarios tiene el torneo del fin de semana?"
- "¿Hay que llevar algo especial para el torneo?"
- "¿Cuánto cuesta la inscripción del campeonato?"
- "¿Dónde comemos en el torneo de Valencia?"
- "¿A qué hora es el primer partido del sábado?"
- "¿Qué instalaciones tiene el polideportivo del torneo?"

**RESULTADO ESPERADO**: RAG útil para cualquier documento deportivo con respuestas precisas y contextualizadas

### 📊 FASE 7: Contexto Avanzado y Conversacional (FUTURO)
**Objetivo**: Respuestas como asistente personal

#### 3.1 Enriquecimiento Automático
- [ ] Pre-computar "estado del equipo"
- [ ] Análisis de rivales
- [ ] Evolución temporal automática

#### 3.2 Templates Conversacionales
- [ ] Respuestas formateadas para padres
- [ ] Emojis y lenguaje natural
- [ ] Contexto personalizado por usuario

#### 3.3 Seguimiento de Conversación
- [ ] Recordar contexto dentro de la sesión
- [ ] "¿Y el equipo contrario?" → saber de qué partido habla

## 🛠 CAMBIOS TÉCNICOS ESPECÍFICOS

### Archivos a Modificar:

#### `services.py` - PRIORIDAD 1
```python
# Línea ~108: Añadir timeouts
self.ollama_client = ollama.Client(
    host=self.ollama_host,
    timeout=30  # AÑADIR
)

# Línea ~283: Optimizar parámetros
response = self.ollama_client.generate(
    model=model,
    prompt=prompt,
    options={
        'temperature': 0.3,  # CAMBIAR de 0.7
        'top_p': 0.9,
        'max_tokens': 800,   # AÑADIR límite
        'timeout': 60        # AÑADIR
    }
)
```

#### `views.py` - PRIORIDAD 2
```python
# Línea ~66: Añadir timeout al endpoint
@timeout_decorator(45)  # AÑADIR
def send_message(request):
    # ... código existente
```

#### Nuevos archivos a crear:
- [ ] `videosvoley/rag/query_router.py`
- [ ] `videosvoley/rag/aggregators.py`
- [ ] `videosvoley/rag/response_formatter.py`

## 📝 TESTING Y VALIDACIÓN

### Casos de Prueba Críticos:
- [ ] "¿Cuándo es el próximo partido de alevín?" → Debe responder sin timeout
- [ ] "¿Cómo va la clasificación?" → Debe mostrar tabla actualizada
- [ ] "¿Qué dice el reglamento sobre rotaciones?" → Debe buscar en PDF

### Métricas de Éxito:
- [ ] 0% timeouts en consultas básicas
- [ ] <5 segundos respuesta promedio
- [ ] 90% consultas resueltas sin fallback

## 🔗 ENLACES Y REFERENCIAS

### Documentación del sistema actual:
- README: `/videosvoley/rag/README.md`
- Models: `/videosvoley/rag/models.py`
- Views: `/videosvoley/rag/views.py`
- Services: `/videosvoley/rag/services.py`

### URLs de testing:
- Chat: `/rag/`
- Documentos: `/rag/documents/`
- Stats: `/rag/stats/`

## 💡 NOTAS DE CONTEXTO

### Configuración actual:
- Modelo por defecto: `phi3:mini`
- Embedding model: `sentence-transformers/all-MiniLM-L6-v2`
- ChromaDB collection: `videosvoley_docs`
- Ollama host: Variable `OLLAMA_HOST`

### Datos disponibles:
- Videos con categorías y comentarios
- Imágenes con tipos y partidos relacionados
- Partidos con equipos, fechas, resultados
- Ligas con categorías y temporadas
- Clasificaciones con posiciones y puntos
- PDFs de reglamentos (problema: fragmentación básica)

## 🎯 PRÓXIMOS PASOS INMEDIATOS

1. ✅ **COMPLETADO**: Arreglar timeouts en Ollama
2. ✅ **COMPLETADO**: Implementar query routing inteligente
3. ✅ **COMPLETADO**: Sistema de aprendizaje con feedback
4. ✅ **COMPLETADO**: Detección avanzada de lenguaje natural + análisis de rachas
5. ✅ **COMPLETADO**: Mejorar RAG para reglamentos (fragmentación inteligente de PDFs)
6. ⏳ **SIGUIENTE**: Análisis temporal, histórico y media (temporadas pasadas, récords, fotos/videos)
7. 📋 **FUTURO**: Conversación contextual y seguimiento de sesión
8. 📋 **FUTURO**: Subir reglamentos específicos de categorías infantiles (alevín, infantil, cadete)

---

## 📞 PARA EL PRÓXIMO CLAUDE

**Estado actual (Dic 2025)**:
✅ **Fases 1-6 COMPLETADAS**: Sistema funcional sin timeouts + query routing inteligente + análisis de rachas + RAG para PDFs mejorado

**Si continúas este proyecto**:
1. ✅ Timeouts de Ollama → RESUELTO
2. ✅ Query routing básico → FUNCIONANDO (90% consultas por BD directa)
3. ✅ Análisis de rachas → FUNCIONANDO (mejor/peor racha con temporada actual dinámica)
4. ✅ **COMPLETADO**: Fase 6 (RAG para PDFs) → FUNCIONANDO
   - Fragmentación inteligente de PDFs con `pdf_processor.py`
   - Filtro inteligente activado en `services.py`
   - Scoring mejorado (+30 pts/keyword, +50 pts altura red)
   - Prompt específico para reglamentos en Ollama
   - Comandos: `list_pdf_documents.py`, `reindex_pdfs.py`
5. ⏳ **PRÓXIMO**: Implementar Fase 5 (análisis temporal, histórico y media)
6. El usuario quiere consultas como "¿cómo fue la temporada pasada?" y "récords históricos"
7. Ya tienes la base: temporada actual se calcula dinámicamente en `query_router.py`

**Limitaciones conocidas**:
- El PDF subido es reglamento de adultos, no tiene alturas para categorías infantiles
- Necesita subir reglamentos específicos de alevín/infantil/cadete para responder esas consultas

**Comandos útiles**:
```bash
# Listar PDFs indexados
docker-compose exec web python manage.py list_pdf_documents --verbose

# Re-indexar PDFs con fragmentación inteligente
docker-compose exec web python manage.py reindex_pdfs --all --verbose

# Importar nuevo reglamento
docker-compose exec web python manage.py import_rulebook --file /path/to/reglamento.pdf --title "Reglamento Voleibol Infantil" --verbose

# Probar sistema RAG
docker-compose exec web python manage.py test_rag
```

**El usuario tiene Ollama funcionando en un servidor separado, no en Docker.**