# RGPD self-service: exportar mis datos y borrar mi cuenta (#613)

## Objetivo

Que la persona titular de una cuenta pueda ejercer por sí misma el acceso y la
supresión. Desde el perfil pide un ZIP con sus datos, que se genera en segundo
plano y se descarga con un enlace caducable enviado por email. Desde el mismo
sitio pide el borrado de la cuenta entera, en todos los clubes, con confirmación
por enlace de email.

La baja de #327 no cambia: sigue poniendo `is_active=False` y quitando el push.
Esto es otra operación. Borrar la fila de `User` no sirve, porque `Video.created_by`,
`Image.uploaded_by`, `Comment.user` y `ImageFavorite.user` están en `CASCADE` y se
llevarían el archivo del club.

## Decisiones

- La cuenta se anonimiza. La fila se queda. El contenido que la persona elige
  conservar pasa a no tener autor (`NULL`).
- El borrado y la exportación cubren la cuenta entera, no la membresía del club
  desde el que se pide.
- Fichas, roles, actas e historial deportivo no se tocan. El consentimiento de
  imagen vive en la ficha y se queda: es la autorización del club, no un dato de
  la cuenta.
- Comentarios y favoritos se borran siempre.
- Fotos y vídeos subidos por esa cuenta se borran o se quedan sin autor, según
  elija en el formulario. Borrar un vídeo borra la fila de `Video`. El vídeo de
  YouTube no es nuestro y no se toca. En un álbum compartido solo se tocan las
  fotos de esa cuenta.
- Si es el último admin activo y aprobado de algún club, el borrado se rechaza
  entero y se nombran esos clubes. Un admin inactivo o sin aprobar no cuenta
  como sustituto.
- Staff y superusuario no pueden borrarse desde este flujo.
- La confirmación es un enlace de email firmado, el mismo patrón que la baja de
  #327. El acceso es con Google y no hay contraseña que pedir.
- El ZIP lleva JSON y CSV. No lleva los bytes de las fotos ni secretos (hash de
  contraseña, token de calendario, claves push, sesiones).
- El registro de auditoría no guarda nombre ni email. En un borrado guarda el id
  de la fila ya anonimizada, la fecha, la acción y qué se hizo con el contenido.
  En una exportación el id va vacío: la cuenta sigue identificable y guardarlo
  permitiría reidentificarla.

## Modelo

Dos modelos en `ilovevoley/users/models.py`.

### `DataExport`

Exportación de una cuenta.

- `user`: FK a `User`, `CASCADE`.
- `status`: `pending`, `ready`, `failed`.
- `file`: `FileField` en almacenamiento privado, vacío hasta que el ZIP está listo.
- `created_at`, `expires_at`. El ZIP caduca a los 7 días de quedar `ready`.
- Una cuenta solo tiene una exportación activa: `pending` de menos de una hora,
  o `ready` con `expires_at` en el futuro. Un `pending` más viejo se marca
  `failed` y no bloquea. Un `failed` tampoco bloquea un reintento.

El enlace del email no guarda el token en claro. Es un `TimestampSigner` con sal
propia sobre el id de la exportación, válido 7 días. Quien tiene el enlace
descarga sin sesión: el token es la credencial.

### `PrivacyAuditEvent`

Solicitud, sin datos personales.

- `user_id`: `PositiveIntegerField`, nulo. No es FK. Solo lo rellena un borrado,
  con el id de la fila ya anonimizada. Una exportación lo deja vacío.
- `action`: `export` o `erasure`.
- `content_choice`: vacío en una exportación; `delete` o `retain` en un borrado.
- `club_count`: entero.
- `created_at`.

Retención de un año. Una tarea diaria borra los más viejos, igual que
`cleanup_expired_web_push_audits`.

### Migración de autores

`makemigrations`, sin migración de datos:

- `Video.created_by` e `Image.uploaded_by` pasan a `null=True`, `blank=True`,
  `on_delete=SET_NULL`.
- `ImageRemovalRequest.requested_by` pasa a `null=True`, `blank=True`,
  `on_delete=SET_NULL`.

El resto de FKs de revisión (`moderated_by`, `reviewed_by`, `resolved_by`,
`MatchShareLink.created_by`, `MatchLineupPersonLink.created_by`) ya son
`SET_NULL`. El borrado las vacía a mano para que no sigan apuntando a la fila
anonimizada.

## Qué le ocurre a la cuenta

Marca de cuenta ya borrada: `username == f"deleted-{pk}"`. Un segundo borrado
sobre esa marca no cambia datos y muestra la misma pantalla de confirmación.

En la transacción de borrado, por este orden:

1. Comentarios, favoritos, `StoryComposition`, `SharedUpload` (fila y fichero) y
   `PersonLinkRequest` de las que esta cuenta es solicitante.
2. Fotos y vídeos. Con `delete`, filas y ficheros. Con `retain`,
   `uploaded_by` y `created_by` a `NULL`.
3. Autores de revisión a `NULL`. En `ImageRemovalRequest`, además, `reason` a
   cadena vacía.
4. `Person.user` a `NULL` si apunta a esta cuenta. `User.children` vacío. El
   vínculo de otro progenitor no se toca. La ficha, sus roles y
   `image_consent` siguen.
5. Membresías de todos los clubes, preferencias de categorías y de avisos,
   suscripciones push, sesiones, `SocialAccount` y `EmailAddress`.
6. Exportaciones de esa cuenta, fichero incluido.
7. La fila de `User`: `username` a `deleted-<pk>`, email, nombre, `parent_info`,
   idioma y token de calendario vacíos, avatar borrado, contraseña inutilizable,
   `is_active` e `is_approved` en falso, avisos de inactividad y marcas de
   onboarding y reactivación a su valor vacío. Se escribe un
   `PrivacyAuditEvent` con `action=erasure`.

`parent_info` es texto libre de la cuenta y se vacía. Las notas de la ficha son
del club y se quedan.

## Exportación

Bloque «Tus datos» al final de la pestaña Perfil, con dos acciones.

`POST` autenticado y limitado (`10/m` por IP, como la baja):

- Si ya hay una exportación activa, no se crea otra y se dice que el enlace ya
  está en camino o en el correo.
- Si no, se crea `DataExport` en `pending` y, al hacer commit, se encola
  `build_data_export` (`name=` explícito) con el id de la exportación y el id
  del tenant de la petición. Sin tenant, se usa la primera membresía aprobada.
  La URL del email sale de `build_absolute_url`.

La tarea vuelve a leer la exportación antes de escribir el fichero. Si la fila
ya no está o la cuenta ya está anonimizada, para y no envía email: el borrado
puede haber ganado la carrera. Si sigue vigente, monta el ZIP, guarda el
fichero, pone `ready` y `expires_at`, y manda el enlace en el idioma de la
cuenta (`language_for`). Si falla, `failed`, sin fichero, `logger.error`, y un
email para que pueda reintentar. El evento de auditoría `export` se escribe al
quedar `ready`, con `user_id` vacío.

Contenido del ZIP, de todos los clubes:

- `account.json` y `account.csv`: perfil (username, email, nombre,
  `parent_info`, idioma, `date_joined`, `last_login`, `is_approved`), membresías
  (club, rol, aprobación, alta), preferencias de categorías, equipos y avisos,
  ficha propia e hijos vinculados (id, nombre, apellidos, año, tipo de vínculo)
  y consentimiento de imagen de esas fichas.
- `content.json` y `content.csv`: fotos y vídeos subidos por la cuenta (id,
  título, URL de la foto o URL de YouTube, fecha, club, estado de moderación).

La descarga es una vista sin login. Token inválido o caducado no entrega el
fichero. Tampoco un ZIP ya borrado. Límite `10/m` por IP.

`cleanup_expired_data_exports` entra en `config/celery_schedule.py` con cadencia
diaria, `name=` explícito. Marca `failed` los `pending` de más de una hora,
borra el fichero y la fila de las exportaciones `ready` con `expires_at`
vencido, y borra las `failed` más viejas de 7 días.

`cleanup_expired_privacy_audit_events`, misma cadencia, borra eventos de más de
un año.

## Borrado

Página propia, con la sesión abierta. Explica el efecto y obliga a elegir
`delete` o `retain` para fotos y vídeos.

`POST`:

- Último admin de algún club: no se envía email. La página lista esos clubes.
- Staff o superusuario: no se envía email.
- Cuenta ya anonimizada: pantalla de confirmación, sin cambios.
- En cualquier otro caso, email con enlace firmado de 48 horas. El token lleva
  `user_id` y la elección (`delete` o `retain`), sal propia. El texto va en el
  idioma de la cuenta.

`GET` del enlace enseña el resumen y que es irreversible. `POST` ejecuta el
borrado en `transaction.atomic()` y vuelve a comprobar lo del último admin: si
mientras el enlace estaba en el buzón se quedó sola como admin, no se borra
nada. La elección sale del token, no de un campo del formulario. Al terminar se
cierra la sesión y la pantalla confirma el borrado. No hay un segundo email: la
dirección ya no existe.

Token inválido o caducado: la misma respuesta que un enlace de baja inservible,
sin decir si la cuenta existe.

## Errores

- El borrado es todo o nada. Un fallo a medias deja la cuenta como estaba.
- La exportación fallida no deja un ZIP a medias descargable: `failed` y sin
  fichero.
- Pedir la exportación dos veces no encola dos tareas.
- Pedir el borrado dos veces no reanonimiza ni borra contenido de otras cuentas
  que hubiera quedado sin autor.

## Tests

En `ilovevoley/users/tests/test_privacy.py`. Cada uno protege una decisión
propia. Si falla, se habría roto el efecto sobre los datos, no un detalle de
Django ni el HTML.

| Test | Regla de `testing-guidelines.md` | Qué se rompe si falla |
| --- | --- | --- |
| Último admin activo y aprobado bloquea toda la cuenta, también si en otros clubes hay más admins. Con otro admin en ese club, el borrado sigue. El mismo bloqueo se repite al ejecutar el enlace si el sustituto desapareció después de enviarlo. | Regla de negocio y caso límite caro en producción | Un club se queda sin admin |
| Staff y superusuario no disparan el email de borrado | Autorización propia, no la de un mixin | Una cuenta de operación desaparece desde el perfil |
| Se sueltan ficha propia e hijos. Ficha, roles y `image_consent` siguen. El otro progenitor conserva su vínculo | Regla de negocio y efecto persistente | Se borra historial del club o se desvincula a quien no lo pidió |
| Comentarios y favoritos desaparecen | Efecto persistente de una decisión explícita | Siguen atribuidos a la cuenta anonimizada. El `CASCADE` no actúa porque la fila no se borra |
| `delete` quita fotos, vídeos y ficheros de esa cuenta. `retain` deja el autor vacío y el fichero en su sitio. Las fotos de otra persona en el mismo álbum siguen | Efecto persistente y decisión ambigua | Se borra archivo del club, o se conserva con el nombre de quien ya no está |
| La cuenta queda anonimizada en todos los clubes: sin nombre, email, avatar, `parent_info` ni token de calendario, sin membresías, sin cuenta de Google, inactiva, username `deleted-<id>`, y un `PrivacyAuditEvent` sin nombre ni email | Efecto persistente | Quedan datos personales o una membresía en otro club |
| Un segundo borrado no modifica filas | Idempotencia | Se vuelve a tocar contenido ya desatribuido |
| El ZIP trae perfil, clubes, preferencias, vínculos, consentimientos y metadatos, y no trae token de calendario, hash ni claves push | Transformación de datos no trivial | El export se deja un secreto o se olvida un bloque pedido en la issue |
| Un enlace de descarga caducado o mal firmado no entrega el ZIP. Con una exportación activa no se crea una segunda fila. Un `pending` de más de una hora no bloquea. Si al ejecutar la tarea la cuenta ya está anonimizada, no queda fichero ni se manda el email | Camino crítico y regla de negocio | El ZIP queda público, se generan dos ficheros, o la persona se queda sin poder exportar |
| Una solicitud de retirada pierde solicitante y motivo | Efecto persistente | El texto libre sigue ligado a la cuenta |
| Si el borrado lanza a medias, email, comentarios y membresías siguen como antes | Rollback de un camino crítico | La cuenta queda a medias y ya no puede entrar ni completar el borrado |

No se testea el HTML del perfil, el `status_code` suelto, que el ORM haga
`CASCADE`, la firma de `TimestampSigner` por sí sola, ni el idioma del email:
eso ya lo cubre `language_for`.

## Fuera de alcance

- Cambiar la baja por inactividad (#327) o la política de privacidad (#469).
- Borrar ficheros en YouTube o en álbumes de otras personas.
- Exportar los bytes de las fotos.
- Un borrado por club, dejando la cuenta viva en los demás.
