# Restringir Endpoints Mutables Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restringir la creación de equipos y personas a usuarios con rol `manager`, aislando la asignación de club al tenant actual y reforzando los métodos HTTP con `@require_POST`.

**Architecture:** Modificar `teams/views.py:ajax_register_team` para forzar `manager=True`, validar sintaxis/longitud y caracteres de control vía regex devolviendo HTTP 400 en fallo, y fijar `club = getattr(request.tenant, 'club', None)`. Restringir `rosters/views.py:person_create` a `manager=True` y adaptar la UI en `person_list.html`. Asegurar decorador `@require_POST` en `ajax_register_team` y `ajax_add_match_result`.

**Tech Stack:** Django 6.0.8, pytest, pytest-django, Docker Compose.

**Spec:** Issue #90 (`[Task]: Restringir endpoints mutables de creación de equipos y personas a usuarios con rol manager`).

## Global Constraints

- Django 6.0.8 fijado en dependencias.
- No ejecutar `docker-compose.dev.yml` en producción; en desarrollo usar `docker compose -p videosvoley -f docker-compose.dev.yml run --rm web python -m pytest ... --tb=short`.
- Tests deben proteger decisiones de negocio reales, sin tests superfluos.
- No hacer `git commit` sin pedir confirmación de imputación `@time` e issue `#90`.

---

### Task 1: Restringir y validar `teams/views.py:ajax_register_team`

**Files:**
- Modify: `ilovevoley/teams/views.py:1-85`
- Test: `ilovevoley/teams/tests/test_views.py:20-96`

**Interfaces:**
- Consumes: `request.tenant.club`, `tenant_access_required(manager=True)`, `require_POST`.
- Produces: `ajax_register_team` retornando HTTP 403 para usuarios sin rol manager, HTTP 405 para métodos distintos de POST, HTTP 400 si el nombre es inválido o tiene caracteres de control/longitud fuera de rango, y crea equipos asignados exclusivamente a `request.tenant.club`.

- [ ] **Step 1: Escribir tests que fallen para `ajax_register_team`**

Editar `ilovevoley/teams/tests/test_views.py`:
- Actualizar `setUp` de `TeamViewUrlTests` para incluir un usuario manager (`self.manager`) además del `self.user` (member) y vincular `self.org.club = self.club`.
- Añadir test `test_basic_member_cannot_register_team_returns_403`: verificar que `self.user` (rol `member`) recibe HTTP 403.
- Añadir test `test_get_method_rejected_with_405`: verificar que peticiones GET devuelven HTTP 405.
- Añadir test `test_register_team_validates_name_syntax_and_length`: verificar que nombres con caracteres de control (`\x00`, `\n`), nombres de longitud < 2 o > 100 caracteres son rechazados con HTTP 400.
- Añadir test `test_register_team_forces_tenant_club_ignoring_payload`: verificar que al enviar `club_id` de otro club, el equipo creado queda asociado a `request.tenant.club`.
- Actualizar `test_teams_ajax_register_team_url_resolves_and_creates_team` para autenticarse con `self.manager`.

```python
    def test_basic_member_cannot_register_team_returns_403(self):
        self.client.force_login(self.user)
        url = reverse('teams:ajax_register_team')
        response = self.client.post(
            url,
            {'name': 'Team Member', 'category_id': self.category.id},
            HTTP_HOST='testclub.ilovevoley.es',
        )
        self.assertEqual(response.status_code, 403)

    def test_get_method_rejected_with_405(self):
        self.client.force_login(self.manager)
        url = reverse('teams:ajax_register_team')
        response = self.client.get(url, HTTP_HOST='testclub.ilovevoley.es')
        self.assertEqual(response.status_code, 405)

    def test_register_team_validates_name_syntax_and_length(self):
        self.client.force_login(self.manager)
        url = reverse('teams:ajax_register_team')
        invalid_names = [
            'A',  # Demasiado corto (<2)
            'A' * 101,  # Demasiado largo (>100)
            'Team\nNewline',  # Carácter de control \n
            'Team\x00Null',  # Carácter de control \x00
            'Team\tTab',  # Carácter de control \t
        ]
        for name in invalid_names:
            response = self.client.post(
                url,
                {'name': name, 'category_id': self.category.id},
                HTTP_HOST='testclub.ilovevoley.es',
            )
            self.assertEqual(response.status_code, 400, f"Expected 400 for invalid name: {name!r}")

    def test_register_team_forces_tenant_club_ignoring_payload(self):
        other_club = Club.objects.create(official_name='Other Club', federation_id='OTHER-CLUB')
        self.client.force_login(self.manager)
        url = reverse('teams:ajax_register_team')
        response = self.client.post(
            url,
            {
                'name': 'Tenant Team Protected',
                'category_id': self.category.id,
                'club_id': other_club.id,
            },
            HTTP_HOST='testclub.ilovevoley.es',
        )
        self.assertEqual(response.status_code, 200)
        team = Team.objects.get(name='Tenant Team Protected')
        self.assertEqual(team.club, self.club)
```

- [ ] **Step 2: Ejecutar los tests para confirmar que fallan**

Ejecutar:
```bash
docker compose -p videosvoley -f docker-compose.dev.yml run --rm web python -m pytest ilovevoley/teams/tests/test_views.py -k "register_team or 403 or 405" --tb=short
```
Expected: FAIL (403 no devuelto para member, 400 no devuelto para nombres inválidos, payload arbitrario no bloqueado).

- [ ] **Step 3: Implementar la protección y validaciones en `teams/views.py`**

Modificar `ilovevoley/teams/views.py`:
- Importar `re` y `from django.views.decorators.http import require_POST`.
- Definir regex `TEAM_NAME_REGEX = re.compile(r"^[\w \.\-'\(\)/&]{2,100}$", re.UNICODE)`.
- Decorar `ajax_register_team` con `@require_POST` y `@tenant_access_required(manager=True)`.
- Validar `raw_name` y `team_name`: si está vacío, longitud < 2 o > 100, no coincide con el regex o contiene caracteres de control (`ord(c) < 32 or ord(c) == 127`), retornar `JsonResponse({'success': False, 'error': 'Nombre de equipo no válido'}, status=400)`.
- Asignar `club = getattr(request.tenant, 'club', None)`, descartando cualquier `club_id` provisto en el payload.

- [ ] **Step 4: Ejecutar los tests de `teams` para verificar que pasan**

Ejecutar:
```bash
docker compose -p videosvoley -f docker-compose.dev.yml run --rm web python -m pytest ilovevoley/teams/tests/test_views.py --tb=short
```
Expected: PASS (todos los tests de `teams` pasan).

---

### Task 2: Restringir `rosters/views.py:person_create` a rol manager y actualizar UI

**Files:**
- Modify: `ilovevoley/rosters/views.py:180-221`
- Modify: `ilovevoley/rosters/templates/rosters/person_list.html:167,339`
- Test: `ilovevoley/rosters/tests/test_views.py:275-315,398-410`

**Interfaces:**
- Consumes: `tenant_access_required(manager=True)`.
- Produces: `person_create` restringido a managers (HTTP 403 a miembros normales). Botones "Agregar Persona" en `person_list.html` condicionados a `is_tenant_manager`.

- [ ] **Step 1: Escribir tests que fallen para `person_create`**

En `ilovevoley/rosters/tests/test_views.py`:
- En `RostersTenantIsolationTests`:
  - Añadir test `test_basic_member_cannot_access_person_create`: verificar que `self.member` recibe HTTP 403 tanto por GET como por POST en `rosters:person_create`.
  - Actualizar `test_person_create_ignora_organizacion_enviada_por_cliente` para usar `self.manager` (rol `manager`) y comprobar que crea la ficha asignando la organización del tenant.
- En `PersonCreatePhotoUploadTests.setUp`:
  - Configurar `self.user` con rol `manager` en su membresía para que continúe probando la subida y procesamiento de imágenes con credenciales válidas.

- [ ] **Step 2: Ejecutar los tests para confirmar que fallan**

Ejecutar:
```bash
docker compose -p videosvoley -f docker-compose.dev.yml run --rm web python -m pytest ilovevoley/rosters/tests/test_views.py -k "person_create" --tb=short
```
Expected: FAIL (member no recibe 403).

- [ ] **Step 3: Implementar la restricción en `rosters/views.py` y actualizar la plantilla**

Modificar `ilovevoley/rosters/views.py`:
- Cambiar el decorador de `person_create`:
```python
@tenant_access_required(manager=True)
def person_create(request):
```
Modificar `ilovevoley/rosters/templates/rosters/person_list.html`:
- Envolver el botón "Agregar Persona" (línea ~167) con `{% if is_tenant_manager %} ... {% endif %}`.
- Envolver el botón en el estado vacío (línea ~339) con `{% if is_tenant_manager %} ... {% endif %}`.

- [ ] **Step 4: Ejecutar los tests de `rosters` para verificar que pasan**

Ejecutar:
```bash
docker compose -p videosvoley -f docker-compose.dev.yml run --rm web python -m pytest ilovevoley/rosters/tests/test_views.py --tb=short
```
Expected: PASS (todos los 26+ tests de rosters pasan).

---

### Task 3: Forzar decorador `@require_POST` en `competitions/views.py:ajax_add_match_result`

**Files:**
- Modify: `ilovevoley/competitions/views.py:420-430`
- Test: `ilovevoley/competitions/tests/test_views.py:470-510`

**Interfaces:**
- Consumes: `django.views.decorators.http.require_POST`.
- Produces: `ajax_add_match_result` decorado con `@require_POST`, respondiendo HTTP 405 a cualquier petición no-POST.

- [ ] **Step 1: Escribir test que falle para método GET en `ajax_add_match_result`**

En `ilovevoley/competitions/tests/test_views.py`:
- Añadir en `AddMatchResultTests`:
```python
    def test_add_match_result_rejects_get_with_405(self):
        self.client.force_login(self.manager)
        response = self.client.get(
            reverse('competitions:ajax_add_match_result', args=[self.match.id]),
            HTTP_HOST='testclub.ilovevoley.es',
        )
        self.assertEqual(response.status_code, 405)
```

- [ ] **Step 2: Ejecutar test para verificar el comportamiento actual**

Ejecutar:
```bash
docker compose -p videosvoley -f docker-compose.dev.yml run --rm web python -m pytest ilovevoley/competitions/tests/test_views.py -k "test_add_match_result_rejects_get_with_405" --tb=short
```

- [ ] **Step 3: Aplicar `@require_POST` en `competitions/views.py`**

Modificar `ilovevoley/competitions/views.py`:
- Importar `from django.views.decorators.http import require_POST`.
- Añadir decorador `@require_POST` a `ajax_add_match_result`.
- Eliminar la comprobación manual redundante `if request.method != 'POST':`.

- [ ] **Step 4: Ejecutar los tests de `competitions` para verificar que pasan**

Ejecutar:
```bash
docker compose -p videosvoley -f docker-compose.dev.yml run --rm web python -m pytest ilovevoley/competitions/tests/test_views.py --tb=short
```
Expected: PASS (todos los tests de `competitions` pasan).

---

### Task 4: Verificación Integral de Regresión

**Files:**
- Test: `ilovevoley/teams/tests/test_views.py`
- Test: `ilovevoley/rosters/tests/test_views.py`
- Test: `ilovevoley/competitions/tests/test_views.py`

- [ ] **Step 1: Ejecutar la suite conjunta de tests de las apps afectadas**

Ejecutar:
```bash
docker compose -p videosvoley -f docker-compose.dev.yml run --rm web python -m pytest ilovevoley/teams/tests/test_views.py ilovevoley/rosters/tests/test_views.py ilovevoley/competitions/tests/test_views.py --tb=short
```
Expected: 100% PASS.

- [ ] **Step 2: Verificar cumplimiento de criterios de éxito del issue #90**
- Usuario con rol de miembro básico recibe HTTP 403 al invocar `ajax_register_team` (comprobado).
- No es posible crear un equipo asignado a un club distinto del asociado a la organización del subdominio (comprobado).
- Nombres de equipo con caracteres de control o longitudes fuera de rango son rechazados con HTTP 400 (comprobado).
- Creación de fichas restringida a managers con HTTP 403 a miembros normales (comprobado).
- Endpoints mutables de API/AJAX protegidos con `@require_POST` (comprobado).
