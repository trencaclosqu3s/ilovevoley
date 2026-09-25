# Custom Manager para Partidos Withdrawn

## 🎯 Problema Resuelto

**Antes**: Teníamos que recordar añadir `.exclude(status='withdrawn')` en cada query de partidos, lo cual es propenso a errores y olvidos.

**Ahora**: El modelo `Match` tiene un **Custom Manager** que excluye automáticamente los partidos withdrawn por defecto.

---

## 📊 Implementación

### 1. Custom Managers en el Modelo

```python
class MatchManager(models.Manager):
    """Manager personalizado que excluye partidos withdrawn por defecto"""
    def get_queryset(self):
        return super().get_queryset().exclude(status='withdrawn')


class MatchAllManager(models.Manager):
    """Manager que incluye TODOS los partidos, incluyendo withdrawn"""
    pass


class Match(models.Model):
    # ... campos ...
    
    # Managers
    objects = MatchManager()  # Manager por defecto: excluye withdrawn
    all_objects = MatchAllManager()  # Manager completo: incluye withdrawn
```

### 2. Uso en el Código

#### ✅ Uso Normal (Excluye Withdrawn Automáticamente)
```python
# En vistas, formularios, templates, etc.
matches = Match.objects.filter(league__category=category)
# Esto automáticamente excluye withdrawn ✨
```

#### ✅ Admin (Incluye Withdrawn)
```python
@admin.register(Match)
class MatchAdmin(admin.ModelAdmin):
    def get_queryset(self, request):
        """Usar all_objects para ver TODOS los partidos, incluyendo withdrawn"""
        return Match.all_objects.get_queryset()
```

#### ✅ Scraping (Incluye Withdrawn)
```python
# En scraping.py, cuando necesitamos marcar partidos como withdrawn
withdrawn_matches = Match.all_objects.filter(
    league=self.league,
    status__in=['scheduled', 'postponed']
).filter(
    models.Q(home_team__is_active=False) | models.Q(away_team__is_active=False)
)
```

---

## 🔧 Archivos Modificados

### 1. `ilovevoley/videos/models.py` ✅
- Añadido `MatchManager` (excluye withdrawn)
- Añadido `MatchAllManager` (incluye withdrawn)
- Configurado `objects` y `all_objects` en el modelo `Match`

### 2. `ilovevoley/videos/admin.py` ✅
- Sobreescrito `get_queryset()` para usar `all_objects`
- Ahora el admin muestra TODOS los partidos para gestión

### 3. `ilovevoley/videos/views.py` ✅
- **REMOVIDOS** todos los `.exclude(status='withdrawn')`
- El manager los excluye automáticamente

### 4. `ilovevoley/videos/forms.py` ✅
- **REMOVIDOS** todos los `.exclude(status='withdrawn')`
- El manager los excluye automáticamente

### 5. `ilovevoley/videos/calendar_feed.py` ✅
- **REMOVIDO** el `.exclude(status='withdrawn')`
- El manager lo excluye automáticamente

---

## 🎯 Ventajas

### ✅ Seguridad
- **No más olvidos**: No hay que recordar excluir withdrawn manualmente
- **Código limpio**: Queries más cortas y legibles
- **Consistencia**: Comportamiento uniforme en toda la aplicación

### ✅ Flexibilidad
- **`Match.objects`**: Uso normal (sin withdrawn)
- **`Match.all_objects`**: Cuando necesitas ver TODO (admin, scraping)
- **Fácil de extender**: Si añades nuevas queries, automáticamente excluyen withdrawn

### ✅ Mantenibilidad
- **Menos código**: No repetir `.exclude()` en cada lugar
- **Más fácil de leer**: Queries más concisas
- **Centralizado**: La lógica está en un solo lugar (el manager)

---

## 📝 Casos de Uso

### Caso 1: Vista del Calendario
```python
# ANTES (manual)
matches = Match.objects.filter(...).exclude(status='withdrawn')

# AHORA (automático)
matches = Match.objects.filter(...)  # ✨ withdrawn excluidos automáticamente
```

### Caso 2: Formulario de Video
```python
# ANTES (manual)
past_matches = Match.objects.filter(...).exclude(status='withdrawn')

# AHORA (automático)
past_matches = Match.objects.filter(...)  # ✨ withdrawn excluidos automáticamente
```

### Caso 3: Admin (Ver TODO)
```python
# Admin necesita ver withdrawn para gestión
def get_queryset(self, request):
    return Match.all_objects.get_queryset()  # ✨ Incluye withdrawn
```

### Caso 4: Scraping (Marcar como Withdrawn)
```python
# Scraping necesita acceder a withdrawn para marcarlos
withdrawn_matches = Match.all_objects.filter(
    status__in=['scheduled', 'postponed']
)  # ✨ Usa all_objects
```

---

## 🧪 Testing

### Verificación
```python
from ilovevoley.competitions.models import Match

# objects (excluye withdrawn)
normal_count = Match.objects.count()

# all_objects (incluye withdrawn)
total_count = Match.all_objects.count()

# withdrawn count
withdrawn_count = Match.all_objects.filter(status='withdrawn').count()

# Verificación
assert normal_count + withdrawn_count == total_count
```

### Resultado del Test
```
✅ Match.objects.count() (excluye withdrawn): 55
✅ Match.all_objects.count() (incluye withdrawn): 55
✅ Partidos withdrawn: 0

🎉 ¡Perfecto! 55 + 0 = 55
```

---

## 💡 Buenas Prácticas

### ✅ DO (Hacer)
```python
# Uso normal - automáticamente excluye withdrawn
matches = Match.objects.filter(league=league)

# Admin o scraping - cuando necesitas TODO
all_matches = Match.all_objects.filter(league=league)
```

### ❌ DON'T (No Hacer)
```python
# ❌ Ya no es necesario (y es redundante)
matches = Match.objects.filter(league=league).exclude(status='withdrawn')

# ❌ No usar all_objects en vistas normales
matches = Match.all_objects.filter(league=league)  # Mostraría withdrawn
```

---

## 🚀 Futuras Extensiones

Si en el futuro necesitas añadir más filtros automáticos al manager:

```python
class MatchManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().exclude(
            status='withdrawn'
        ).select_related(
            'home_team', 'away_team', 'league'  # Optimización
        )
```

O métodos custom:

```python
class MatchManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().exclude(status='withdrawn')
    
    def upcoming(self):
        """Partidos futuros"""
        from django.utils import timezone
        return self.get_queryset().filter(match_date__gte=timezone.now())
    
    def finished(self):
        """Partidos finalizados"""
        return self.get_queryset().filter(status='finished')

# Uso:
upcoming_matches = Match.objects.upcoming()
finished_matches = Match.objects.finished()
```

---

## ✅ Conclusión

El Custom Manager es una solución **elegante, segura y mantenible** para excluir automáticamente partidos withdrawn de todas las queries normales, mientras permite acceso completo cuando es necesario (admin, scraping).

**Beneficios principales**:
1. ✅ Automático: No hay que recordar excluir withdrawn
2. ✅ Seguro: Imposible olvidarlo
3. ✅ Limpio: Código más conciso
4. ✅ Flexible: `all_objects` cuando necesites TODO
5. ✅ Mantenible: Lógica centralizada

¡Excelente sugerencia! 👏
