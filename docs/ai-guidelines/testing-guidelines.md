## Testing Guidelines

Execute tests with:
```bash
docker compose -f docker-compose.dev.yml run --rm web python -m pytest --create-db
```
**Nota:** Usar `--create-db` para forzar la creación de la base de datos de test y aplicar migraciones correctamente. Sin este flag la BD de test puede quedar desactualizada y los tests fallar (p. ej. columnas faltantes).

## Test Value Rules

Un test es necesario cuando protege una decisión propia del producto. No basta con que aumente cobertura, pase en CI o sea fácil de escribir.

### Un test debe existir si cumple al menos una regla

- Protege una regla de negocio
- Protege un caso límite que ya falló, puede fallar de forma realista o sería caro de detectar en producción.
- Verifica una transformación de datos no trivial: normalización, parsing de actas/HTML/JSON federativo, serialización de API o resolución de duplicados.
- Cubre un flujo con efectos persistentes: crea, actualiza, bloquea, revierte o borra datos relevantes.
- Comprueba manejo de errores en un camino crítico: rollback, idempotencia, errores externos, respuestas parciales o recuperación.
- Documenta una decisión ambigua que un futuro cambio podría romper sin darse cuenta.
- Da confianza sobre integración entre componentes propios del proyecto, no sobre el framework.

### Un test no debe existir si su valor principal es la cobertura

- Solo comprueba que Django, DRF, pytest, el ORM o un mixin estándar hacen lo que ya está probado por la librería.
- Solo valida `status_code == 200`, `302`, `403` o `404` sin comprobar un efecto, payload, contexto o regla propia.
- Solo comprueba HTML decorativo, clases CSS, textos cosméticos, spinners o estructura visual frágil sin contrato funcional.
- Duplica otro test más fuerte que ya cubre el mismo riesgo con mejores aserciones.
- Mockea tanto la unidad bajo prueba que el test solo verifica el mock.
- Reproduce literalmente la implementación en el test, en vez de comprobar comportamiento observable.
- Prueba getters, setters, propiedades simples o filtros ORM triviales sin regla de negocio.
- Cubre permisos genéricos de `LoginRequiredMixin` o `PermissionRequiredMixin` salvo que haya lógica de autorización propia.

### Preguntas de revisión antes de añadir o conservar un test

1. Si este test falla, ¿qué comportamiento real se habría roto?
2. ¿El fallo obligaría a cambiar código de producto, o solo actualizar el test?
3. ¿Está probando nuestra lógica o la librería?
4. ¿Hay otro test que ya cubre el mismo riesgo de forma más directa?
5. ¿El test seguirá siendo útil si cambia el HTML, el copy o una clase CSS?
6. ¿El coste de mantenerlo está justificado por el riesgo que reduce?

Si la respuesta no identifica un riesgo concreto, el test debe eliminarse o reescribirse.

### Preferencias de diseño

- Prioriza tests de comportamiento observable sobre detalles internos.
- Prefiere una aserción fuerte sobre persistencia, payload o efecto de dominio antes que varias aserciones de estado superficial.
- Usa el nivel más bajo que conserve el contrato: método puro para lógica pura, vista/API para contratos HTTP, E2E solo para flujos de usuario completos.
- Usa `RequestFactory` cuando el objetivo sea ejercitar una vista concreta sin middleware, sesión ni renderizado innecesario.
- Usa `client` cuando el contrato incluya routing, auth, middleware, mensajes, templates o integración HTTP completa.
- Evita renderizar templates pesados si el test solo necesita probar una rama de `post`; stubbea el retorno visual solo si las aserciones siguen cubriendo efectos reales.
- No mezcles ubicaciones: lógica de modelo en `test_models.py`, filtros de template en `test_templatetags.py`, APIs en `test_api.py`, vistas HTML en `test_views.py`.
- Un test lento debe justificar su lentitud. Si abre archivos reales, llama a importadores o recorre un flujo de integración valioso, puede quedarse. Si solo mira una cabecera, no.

### Automatic Test Generation Rules
When working with business logic, automatically generate tests that cover:
```yaml
business_logic_testing:
  always_test:
    - Custom model methods with business rules
    - Data validation beyond Django's built-in validators  
    - Permission and authorization logic
    - Multi-tenant isolation and tenant scoping
    - State machines and workflow transitions
    - Custom managers and QuerySets with complex logic
  
  test_selectively:
    - Views with complex conditional logic
    - API endpoints that transform data
    - Custom form validation methods
    
  skip_testing:
    - Basic Django CRUD operations
    - Simple property getters/setters
    - Standard Django field validations
    - Basic template rendering without logic

  focus_areas:
    - Edge cases in business rules
    - Error handling in critical paths
    - Integration points between business domains

admin_testing:
  skip:
    - Basic ModelAdmin configuration
    - Standard CRUD operations  
    - Built-in admin functionality
    - Simple list_display/search_fields
  
  test_when_present:
    - Custom admin methods with business logic
    - Complex get_queryset() implementations
    - Custom admin actions
    - save_model() with validation logic
    - Custom admin views or forms
    - Permission-based admin behavior
```

## Test Organization Structure

### Mandatory Test Directory Structure
```yaml
test_structure:
  location: "app_name/tests/"
  organization:
    models: "test_models.py"
    views: "test_views.py" 
    forms: "test_forms.py"
    utils: "test_utils.py"
    api: "test_api.py"
    admin: "test_admin.py"  # only if custom logic exists
  
  required_files:
    - "tests/__init__.py"  # always required
```
