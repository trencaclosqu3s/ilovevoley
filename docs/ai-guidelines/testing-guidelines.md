# Estándares de tests

**Criterio de entrada:** cada test nombra en una frase el defecto que evita.
Si no se puede nombrar, el test no se escribe, y si ya existe se borra. No
basta con que suba cobertura, pase en CI o sea fácil de escribir.

## Escribir

1. **Ningún test es fiable hasta que lo has visto en rojo.** Rompe el código
   que protege, o revierte el fix si es un bug, y confirma que falla por la
   razón correcta. `scripts/en_rojo.py` aplica la mutación, ejecuta pytest y
   restaura el fichero. Hecho cuando cada test nuevo o reescrito tiene una fila
   en la tabla *mutación → tests que fallan* de la PR; un test sin fila no se
   entrega. La mutación imita una regresión plausible (un filtro de tenant
   quitado, una condición invertida); una mutación inventada para que el test
   falle no cuenta. Si dos mecanismos producen el mismo efecto (una vista y una
   task que limpian el mismo flag, un `unique` y una validación de formulario),
   la mutación de uno sobrevive: el test aísla el que protege.
2. **Lo temporal se valida en la PR, no en la suite.** Una migración de datos
   o un mecanismo de transición se comprueba con un script o una ejecución
   anotada en la PR. Nunca un test de migración: `MigrationExecutor` desaplica y
   reaplica toda la cadena, y 10 de esos tests eran el 45 % del tiempo de la
   suite (#536). La lógica que importa una migración (p. ej.
   `normalize_season_name`) se prueba donde vive. No se prueba `reverse()`: se
   despliega solo hacia adelante.
3. **`transaction=True` (o `TransactionTestCase`) solo si otra conexión tiene
   que ver los commits**, por ejemplo un hilo o un proceso aparte. Su teardown
   vacía todas las tablas. Para `on_commit`, usa
   `self.captureOnCommitCallbacks(execute=True)` o la fixture
   `django_capture_on_commit_callbacks`.
4. **Ajusta la implementación, no el test.** Una aserción solo se debilita si
   cambia el comportamiento esperado, y la PR lo explica.
5. **Más de 3 tests nuevos: propón antes la lista** (test y defecto que evita)
   y espera a que la valide quien pidió el trabajo.
6. **Una PR con tests escritos por IA** indica qué queda sin cubrir y por qué,
   y antes de entregarse la revisa un agente sin el contexto de quien los
   escribió: marca cada test nuevo como esencial, prescindible o borrar, y se
   borran los dos últimos. Lo que queda sin cubrir es información para la PR,
   no una lista de tests por escribir; revisar o podar no autoriza a ampliar la
   cobertura.

## Revisar y podar

7. **Señales de un test que sobra:**
   - comprueba llamadas a mocks en lugar de estado, payload o resultado;
   - monta objetos con `SimpleNamespace` o mockea servicios propios en lugar
     de usar las fronteras: red y scraping federativo (voleibolib, RFEVB,
     circulares), Google Vision, Web Push, email, YouTube, broker de Celery
     (`.delay`) y reloj. El hook `avisar-mocks-propios` avisa de los nuevos;
   - solo valida `status_code` sin un efecto, payload o contexto propio;
   - su única aserción es `is not None`;
   - prueba `__str__`, getters, properties o filtros ORM sin regla de negocio;
   - repite lo que ya garantiza Django, el ORM o un mixin estándar
     (`LoginRequiredMixin`, `required` de un formulario, validadores de campo);
   - comprueba HTML decorativo, clases CSS o copy;
   - pinea configuración que el despliegue puede sobreescribir;
   - reproduce la implementación en vez de comprobar comportamiento;
   - repite el riesgo de otro test;
   - su arrange no crea lo que dice su nombre (un id inexistente donde el
     nombre habla de una ficha de otro club).
8. **Señales de un test que se queda**, aunque se parezca a otro:
   - aísla por tenant/club una vía con su propio filtro
     (`Person.objects.for_tenant`, `PersonRoleTenantQuerySet`, otro queryset u
     otra acción);
   - reproduce la condición de un incidente (#NNN) que ningún otro test
     reproduce;
   - fija marcadores, clasificaciones, dorsales, temporadas (corte del 1 de
     septiembre, temporada activa única) o fechas (zona horaria, borde de mes)
     que se publican o se notifican;
   - fija una transformación no trivial: parsing de actas, HTML o JSON
     federativo, normalización o resolución de duplicados;
   - fija qué se hace cuando falla un sistema externo: no borrar partidos, no
     notificar, no marcar como finalizado.
9. **Borrar un test de poco valor es una mejora.** Si un refactor que no
   cambia el comportamiento lo rompe, reescríbelo contra la vía pública.
10. **«Ya lo cubre X» se demuestra en rojo.** Quien borra un test por repetir
   el riesgo de otro escribe la mutación que el borrado detectaba y la pasa por
   `en_rojo.py` contra los tests que quedan. Si sale verde, el test vuelve.
   La mutación va en la vía que el test fija (la acción, el queryset propio),
   no en el código que comparten varias: un test de la regla 8 sobrevive a la
   mutación compartida y cae solo con la propia. Todos los borrados de la PR se
   prueban a la vez (cierre: cada mutación con todos deseleccionados), y se
   repite el cierre tras el último merge de main, que puede borrar detectores.
   Hecho cuando cada borrado por repetición tiene su fila *mutación → test que
   la detecta* en la PR, y ese test existe en el árbol final y cae por el mismo
   comportamiento (no por un 500 ni por otro efecto). Los borrados por otra
   señal de la regla 7 no la necesitan.
11. **El tamaño de una poda es un resultado, nunca un objetivo.** Cada borrado
   sale de la regla 7 o de la 10. Un encargo de poda a subagentes apunta a
   esta sección sin añadir criterios: en otro proyecto, una cuota del 40 %
   borró cientos de tests con defecto nombrado. Quien revisa la poda parte de
   `scripts/tests_borrados.py listar <ruta>`, sin los motivos de quien podó, y
   devuelve los que hagan falta con `scripts/tests_borrados.py restaurar`.

## Diseño

- Comportamiento observable antes que detalles internos; una aserción fuerte
  sobre persistencia, payload o efecto de dominio antes que varias de estado
  superficial.
- El nivel más bajo que conserve el contrato: función pura para lógica pura,
  `RequestFactory` para una rama de una vista, `client` cuando el contrato
  incluye routing, middleware de tenant, sesión o mensajes.
- Un test lento justifica su lentitud: abrir ficheros reales o recorrer un
  flujo de integración valioso, sí; renderizar una plantilla pesada para mirar
  una cabecera, no.
- **Admin:** solo métodos con lógica, `get_queryset()` complejos, acciones
  custom y `save_model()` con validación; nunca configuración de `ModelAdmin`.
- **Ubicación:** `app/tests/` con `__init__.py`; `test_models.py`,
  `test_views.py`, `test_forms.py`, `test_api.py`, `test_utils.py`,
  `test_templatetags.py` y `test_admin.py` solo si hay lógica propia.

## Ejecución

```bash
docker compose -f docker-compose.dev.yml run --rm web python -m pytest --create-db -n auto
```

`--create-db` siempre que cambien modelos o migraciones; en iteración local,
`--reuse-db`.

- **Mutaciones:** para «¿lo detecta este test?» (regla 1), pasa a `en_rojo.py`
  solo los tests que tocan el código mutado (fichero o nodeid); para «¿lo
  detecta la suite?» (regla 10), la carpeta `tests/` de la app: con un nodeid,
  otro test que sí la detecta no cuenta y sale un verde falso. Para más de dos,
  `en_rojo.py --lote FICHERO.jsonl` arranca Django una vez. Ver
  `scripts/en_rojo.py --help` para el formato.
- **Helpers compartidos** van en `tests/helpers.py` o `conftest.py`; el hook
  `no-importar-de-test` rechaza importar de otro `test_*.py` (al podar uno se
  rompe la colección del otro).
- **Casos en un `TestCase`:** `self.subTest(...)`; `pytest.mark.parametrize`
  solo funciona en tests de función o clases sin `TestCase`.
