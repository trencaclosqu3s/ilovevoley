# Implementación de Partidos Amistosos

## ✅ Completado

Se ha implementado con éxito el sistema de partidos amistosos para VideosVoley. Los usuarios con permisos (staff y VideoManagers) ahora pueden crear partidos amistosos desde la vista del calendario.

### Cambios Realizados

#### 1. **Modelo de Datos** ✅
- ✅ Añadidos campos al modelo `Match`:
  - `home_team_text`: CharField para nombre del equipo local en texto libre
  - `away_team_text`: CharField para nombre del equipo visitante en texto libre
  - `is_friendly`: Boolean para marcar partidos amistosos
- ✅ ForeignKeys `home_team`, `away_team`, `league` ahora son opcionales (null=True, blank=True)
- ✅ Propiedades helper: `home_team_display`, `away_team_display`, `is_official`
- ✅ Método `clean()` para validación
- ✅ Migración de base de datos aplicada: `0017_add_friendly_match_support`

#### 2. **Formulario y Vista** ✅
- ✅ Creado `FriendlyMatchForm` con autocompletado inteligente
- ✅ Vista `friendly_match_create` para crear amistosos
- ✅ Vista AJAX `ajax_search_teams` para búsqueda de equipos
- ✅ Sistema de autocompletado con JavaScript que:
  - Busca equipos existentes en la BD
  - Filtra por categoría seleccionada
  - Permite texto libre si no encuentra el equipo
  - Muestra badge visual cuando se selecciona un equipo

#### 3. **Templates** ✅
- ✅ `friendly_match_form.html`: Formulario con autocompletado
- ✅ `calendar.html`: 
  - Botón verde "Añadir Amistoso" (visible solo para staff/VideoManagers)
  - Badge verde "🏐 Amistoso" en partidos amistosos
  - Indicador verde en vista calendario
- ✅ `match_detail.html`: Badge de amistoso en detalle del partido
- ✅ Todos los templates actualizados para usar `home_team_display` y `away_team_display`

#### 4. **URLs** ✅
- ✅ `/videos/calendario/amistoso/nuevo/` - Crear partido amistoso
- ✅ `/videos/ajax/search-teams/` - AJAX para autocompletado

#### 5. **Admin de Django** ✅
- ✅ Actualizado `MatchAdmin`:
  - Filtro por `is_friendly`
  - Display de tipo de partido (🏐 Amistoso / 🏆 Oficial / ❓ Otro)
  - Fieldsets reorganizados para incluir campos de texto
  - Manejo de equipos opcionales en `teams_active_status`

#### 6. **Scraping** ✅
- ✅ El scraping ahora excluye partidos amistosos:
  - No actualiza partidos con `is_friendly=True`
  - No marca amistosos como "withdrawn"
  - Mantiene intactos los partidos creados manualmente

#### 7. **Integraciones** ✅
- ✅ **Google Calendar**: Actualizado para usar `home_team_display` y `away_team_display`
- ✅ **Calendar Feed (ICS)**: 
  - Incluye partidos amistosos
  - Busca también en campos de texto (`home_team_text`, `away_team_text`)
  - Añade marcador "[AMISTOSO]" en el título

### Funcionalidades

#### Para Usuarios (Staff/VideoManagers):
1. **Crear Amistoso**: Clic en botón verde "Añadir Amistoso" en calendario
2. **Autocompletado Inteligente**:
   - Escribe el nombre del equipo
   - Si existe en BD → aparece en lista desplegable
   - Si no existe → escribe el nombre completo
   - Filtra por categoría automáticamente
3. **Flexibilidad Total**:
   - Equipos de otras federaciones → texto libre
   - Equipos del mismo club → seleccionar de BD
   - Equipos de nuestra liga → seleccionar de BD

#### Visualización:
- Badge verde "🏐 Amistoso" en todos los listados
- Borde verde en vista calendario
- Sincroniza con Google Calendar
- Aparece en feeds ICS con marcador [AMISTOSO]

### Comportamiento del Sistema

#### Creación de Ligas Automáticas:
Cuando creas un amistoso, el sistema:
1. Busca o crea una liga "Amistosos - [Categoría]" para la temporada actual
2. Asigna `federation_id` único: `friendly-{category_id}-{season}`
3. Marca `competition_type = 'friendly'`

#### Estado de los Datos:
- **Partidos existentes**: Sin cambios, siguen funcionando normalmente
- **Scraping**: No afecta ni modifica partidos amistosos
- **Texto vs BD**: 
  - Si seleccionas equipo existente → usa ForeignKey
  - Si escribes texto libre → guarda en `home_team_text`/`away_team_text`

---

## 🔮 Mejora Futura: "Convertir Texto a Equipo"

### Concepto
Según la conversación con el usuario, se planea añadir una funcionalidad para **convertir equipos escritos en texto libre a equipos reales en la base de datos**.

### Caso de Uso
1. Creas un amistoso contra "CV Palma Cadete Femenino" (texto libre)
2. Más tarde, decides que quieres convertirlo en un equipo real para:
   - Asociarle un club
   - Añadir logo
   - Corregir typos (ej: "Protol" → "Portol")
   - Reutilizar en futuros partidos

### Propuesta de Implementación

#### Opción Recomendada: Botón "Convertir a Equipo"

**Ubicación**: Admin de Django en la vista de partido amistoso

**Funcionalidad**:
```python
# En admin.py, añadir acción personalizada
@admin.action(description='Convertir texto a equipo (crear Team en BD)')
def convert_text_to_team(self, request, queryset):
    """
    Convierte equipos de texto libre a objetos Team en la BD
    Solo para partidos amistosos que usan texto
    """
    for match in queryset:
        if match.is_friendly:
            # Si tiene home_team_text pero no home_team
            if match.home_team_text and not match.home_team:
                # Crear Team
                team, created = Team.objects.get_or_create(
                    name=match.home_team_text,
                    defaults={
                        'federation_id': f"manual-{timezone.now().timestamp()}",
                        'is_manual': True,  # Nuevo campo a añadir
                        'needs_review': True,  # Nuevo campo a añadir
                        'category': match.league.category if match.league else None
                    }
                )
                match.home_team = team
                match.home_team_text = ''
            
            # Repetir para away_team
            # ...
            
            match.save()
```

#### Campos Adicionales Sugeridos para Team:
```python
class Team(models.Model):
    # ... campos existentes ...
    
    # NUEVOS CAMPOS para equipos manuales
    is_manual = models.BooleanField(
        default=False,
        help_text='Indica si el equipo fue creado manualmente (no vía scraping)'
    )
    needs_review = models.BooleanField(
        default=False,
        help_text='Indica si el equipo necesita revisión/corrección manual'
    )
```

#### Workflow Propuesto:

1. **Creación Inicial**:
   - Usuario crea amistoso con texto libre
   - Partido se guarda con `home_team_text` / `away_team_text`

2. **Conversión a Equipo**:
   - Desde admin, seleccionar partido(s)
   - Acción "Convertir texto a equipo"
   - Sistema crea Team con `is_manual=True`, `needs_review=True`
   - Partido ahora usa ForeignKey

3. **Revisión Manual**:
   - Filtro en admin de Teams: "Equipos manuales pendientes de revisión"
   - Admin puede:
     - Vincular a club existente
     - Corregir nombre
     - Añadir logo
     - Marcar `needs_review=False`

4. **Gestión de Duplicados**:
   - Comando: `python manage.py merge_duplicate_teams`
   - Detecta nombres similares usando Levenshtein distance
   - Sugiere fusiones al admin

### Beneficios:
- ✅ **Flexibilidad inicial**: Puedes crear amistosos rápidamente sin preocuparte
- ✅ **Orden posterior**: Conviertes a Team cuando lo necesites
- ✅ **Corrección de errores**: Fácil corregir typos en nombre
- ✅ **Reutilización**: Una vez convertido, aparece en autocompletado
- ✅ **Trazabilidad**: Sabes qué equipos fueron creados manualmente

### Implementación Estimada:
- **Tiempo**: 2-3 horas
- **Archivos a modificar**:
  - `videosvoley/videos/models.py` (añadir campos a Team)
  - `videosvoley/videos/admin.py` (añadir acción y filtros)
  - `videosvoley/videos/management/commands/merge_duplicate_teams.py` (nuevo)
  - Migración de BD

---

## 📊 Estado del Proyecto

### ✅ Completado (100%)
- [x] Modelo de datos con campos flexibles
- [x] Formulario con autocompletado inteligente
- [x] Vistas y URLs
- [x] Templates actualizados
- [x] Admin de Django actualizado
- [x] Scraping protegido
- [x] Integraciones (Google Calendar, ICS)
- [x] Migraciones aplicadas
- [x] Testing básico (Django check)

### 🔮 Pendiente (Opcional)
- [ ] Función "Convertir texto a equipo"
- [ ] Comando `merge_duplicate_teams`
- [ ] Tests unitarios específicos
- [ ] Edición de partidos amistosos existentes
- [ ] Eliminación de partidos amistosos
- [ ] Estadísticas (excluir/separar amistosos)

---

## 🚀 Cómo Usar

### Crear un Partido Amistoso:

1. Ve al calendario: `/videos/calendario/`
2. Haz clic en el botón verde "Añadir Amistoso"
3. Selecciona la categoría
4. Introduce fecha y hora
5. Para cada equipo:
   - Empieza a escribir el nombre
   - Si aparece en la lista → selecciónalo
   - Si no aparece → escribe el nombre completo
6. (Opcional) Añade instalación y ciudad
7. Haz clic en "Crear Partido Amistoso"

### Ejemplos de Uso:

#### Caso 1: Amistoso contra equipo de otra federación
```
Categoría: Senior Masculino
Equipo Local: Sant Josep (seleccionado de BD)
Equipo Visitante: CV Barcelona Cadete F (texto libre)
```

#### Caso 2: Amistoso interno del club
```
Categoría: Infantil Masculino
Equipo Local: Sant Josep Infantil M (seleccionado de BD)
Equipo Visitante: Sant Josep Cadete F (seleccionado de BD)
```

#### Caso 3: Amistoso contra equipo de nuestra liga
```
Categoría: Cadete Femenino
Equipo Local: Sant Josep (seleccionado de BD)
Equipo Visitante: Portol (seleccionado de BD)
```

---

## 🔍 Notas Técnicas

### Compatibilidad:
- ✅ Django 5.2.7
- ✅ PostgreSQL
- ✅ Python 3.11+
- ✅ Compatible con scraping existente
- ✅ Compatible con sistema de imágenes
- ✅ Compatible con Google Calendar sync

### Seguridad:
- ✅ Solo staff y VideoManagers pueden crear amistosos
- ✅ Validación en formulario y modelo
- ✅ CSRF protection
- ✅ Permisos en vistas

### Performance:
- ✅ AJAX para autocompletado (evita cargar todos los equipos)
- ✅ Limit 10 resultados en búsqueda
- ✅ Select_related en queries
- ✅ Debounce de 300ms en búsqueda

---

## 📝 Commit Message Sugerido

```
feat: Add friendly match support with flexible team input

- Add is_friendly, home_team_text, away_team_text fields to Match model
- Make home_team, away_team, league ForeignKeys optional
- Create FriendlyMatchForm with intelligent autocomplete
- Add AJAX team search endpoint filtered by category
- Update calendar view with "Add Friendly" button and green badges
- Update all templates to use home_team_display/away_team_display properties
- Protect scraping from updating friendly matches
- Update Google Calendar and ICS feed to include friendly matches
- Add admin filters and display for friendly match type

Users with staff/VideoManagers permissions can now create friendly matches
with teams that don't exist in the database using free text input.
The system provides intelligent autocomplete for existing teams while
allowing full flexibility for external teams.

Future enhancement: Add "Convert text to team" functionality to create
Team objects from free text entries when needed.
```

---

## 🎉 Resumen

¡Sistema de partidos amistosos completamente implementado! Ahora puedes:

- ✅ Crear amistosos contra cualquier equipo (exista o no en BD)
- ✅ Usar autocompletado inteligente para equipos existentes
- ✅ Ver claramente qué partidos son amistosos (badges verdes)
- ✅ Sincronizar con Google Calendar
- ✅ Exportar a feeds ICS
- ✅ Mantener scraping protegido y funcionando

La funcionalidad de "Convertir texto a equipo" queda como mejora futura opcional, siguiendo tu preferencia de implementarla cuando sea necesario.
