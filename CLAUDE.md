# VIVA SOCCER

App web para gestionar una escuela de fútbol infantil en Tijuana.

Ahora se le agrega una **API REST** para que una app móvil (proyecto hermano
`vsoccer-movil`, en React Native + Expo) comparta la misma base de datos en la
nube. La web la siguen usando el administrador, la secretaria y los
entrenadores; la app móvil la usan los entrenadores, para capturar desde la
cancha, y los padres de familia, para consultar el desempeño de sus hijos.

## Stack
- Python 3.12, Django 5.x
- SQLite en desarrollo, PostgreSQL administrado en producción (Neon)
- HTMX para interactividad, sin React ni build de JS
- Tailwind CSS
- Chart.js para las gráficas
- Django REST Framework + djangorestframework-simplejwt (para la API móvil)

## Dominio
- Alumnos menores de edad. Cada alumno apunta a un `Tutor` con llave
  foránea (nombre, teléfono y correo del padre); un tutor puede tener varios
  hijos en la escuela
- Tres categorías por edad: MINI, MENOR, MAYOR
- Cada categoría tiene dos horarios: "Lunes y Miércoles" o "Martes y Jueves"
- Cada alumno se evalúa en PASE, RECEPCIÓN y TIRO, escala 1-10
- Las evaluaciones se registran por fecha, hay histórico y progresión
- Cuatro roles, cada uno un grupo de Django, definidos en `escuela/roles.py`
  con su función `es_<rol>` y su decorador `solo_<rol>`:
  - **administrador**: todo. También cuenta como secretaria y entrenador.
  - **secretaria**: padrón (alta, edición, baja y reactivación de alumnos,
    conservando su histórico), tutores (alta y edición; no se elimina un
    tutor con alumnos), corrección y borrado de evaluaciones (respetando la
    de una por fecha), boletas individuales y de grupo, y en el admin de
    Django los códigos de activación de los tutores. No entra al panel ni a
    la captura.
  - **entrenador**: captura de evaluaciones.
  - **tutor**: consulta, solo desde la app móvil. El administrador no lo
    hereda: ser tutor es ser el padre de alumnos concretos, no un permiso.

## Reglas
- Todo en español: modelos, campos, vistas, comentarios, UI
- La referencia visual está en design/design.html
- Los colores salen de tailwind.config.js, nunca hex sueltos en templates
- La pantalla de captura de evaluaciones es mobile-first, es la que
  más se usa y se usa en la cancha
- No metas dependencias sin avisar

## Reglas de la parte nueva
- **La web existente sigue funcionando igual.** Las vistas HTMX, las
  plantillas y el flujo del administrador no se tocan salvo que se pida.
  La API se agrega al lado, no en lugar de ellas.
- **Los modelos son la única fuente de verdad.** El promedio y el folio los
  calcula el modelo, nunca el cliente. La app móvil manda pase, recepción y
  tiro; el servidor calcula el resto.
- **Una sola evaluación por alumno y fecha.** Es restricción de base de datos
  y la API debe respetarla: responder 409, no duplicar.
- **Los permisos se resuelven en el servidor.** Un entrenador solo ve los
  alumnos de sus grupos; un tutor solo a sus hijos. Nunca se filtra en el
  cliente.
- **Nada de credenciales en el código.** DATABASE_URL, SECRET_KEY y DEBUG
  salen de variables de entorno. Si falta una, que falle con mensaje claro.
- **Cada cambio de comportamiento lleva su prueba.** `python manage.py test`
  debe pasar antes de dar por terminado cualquier trabajo.

## Modelos nuevos
Ya existen `Tutor`, `Alumno`, `Evaluacion`, `Categoria`, `Horario` y los roles
en `escuela/roles.py`.

Se agregan para la versión móvil (migraciones 0005 y 0006):

- `Tutor.usuario` — `OneToOneField` opcional a `User`: la cuenta con la que
  ese tutor entra a la app. No hay un modelo aparte para la cuenta: el padre
  del padrón es el mismo que inicia sesión, y sus hijos son los alumnos que
  ya lo tienen asignado (`request.user.tutor.alumnos`). Como `Alumno.tutor`
  es una sola llave foránea, **cada alumno tiene un solo tutor con acceso a
  la app**. Si se borra el usuario, el tutor y sus hijos se conservan.
- `CodigoActivacion` — código de un solo uso, ligado a un `Tutor`, que la
  escuela entrega al padre para que cree su contraseña. **Los padres no se
  registran solos**: se trata de información de menores.
- `Dispositivo` — token de notificaciones push de Expo, ligado a un `User`.
  El token es único: si otro usuario inicia sesión en el mismo celular, se
  le reasigna.
- `Comunicado` — aviso de la escuela, opcionalmente dirigido a una categoría.

La migración 0006 crea el grupo `tutor` (sin permisos de modelo; solo usa la
API) y da a la secretaria los permisos de `CodigoActivacion`.

### Canje de códigos
1. La secretaria o el administrador genera el código desde la ficha del tutor
   en el admin de Django. Son 8 caracteres sin los que se confunden
   (0/O, 1/I/L) y vencen a los 7 días (`DIAS_VIGENCIA_CODIGO`).
2. El padre lo canjea con `codigo.canjear(contrasena)`, que en una sola
   transacción:
   - gasta el código con un UPDATE condicionado a que no se haya usado ni
     vencido; si dos peticiones llegan a la vez, solo una gana y la otra
     recibe `CodigoYaUsado`;
   - si el tutor no tiene cuenta, la crea con su teléfono sin espacios como
     usuario (`5512345678`), que es con lo que inicia sesión;
   - fija la contraseña, activa la cuenta y la agrega al grupo `tutor`.
3. Si el padre olvida su contraseña, se le genera otro código; canjearlo solo
   cambia la contraseña de la cuenta que ya tiene.

Si algo falla (por ejemplo, el teléfono ya está ocupado como usuario), se
revierte todo y el código sigue vigente.

### Grupos del entrenador (migraciones 0007 y 0008)
- Un grupo es categoría + horario; no hay modelo `Grupo`. Las seis claves
  (`"MINI-LUN_MIE"`…) están en `GRUPOS`, en `escuela/models.py`, y las usan la
  web y la API.
- `AsignacionEntrenador` liga un entrenador con un grupo. La asignan el
  administrador o la secretaria desde el admin. El administrador no necesita
  asignaciones: ve los seis.
- `grupos_de(user)` y `alumnos_del_entrenador(user)` en `escuela/roles.py`
  son la única regla de qué ve un entrenador en la API: alumnos activos que
  **hoy** están en uno de sus grupos. Lo de fuera responde 404.
- La captura web todavía **no** se restringe por asignación.
- `Evaluacion.client_uuid` lo genera el teléfono. `fecha` es el día en la
  cancha (hasta 7 días atrás) y `creada` es cuándo llegó al servidor: son
  datos distintos.

### Modo Familia
- `alumnos_del_tutor(user)` en `escuela/roles.py` es la única regla de qué ve
  un tutor: sus hijos, **incluidos los dados de baja** (su histórico sigue
  siendo del papá). Lo de fuera responde 404.
- El histórico lo comparten entrenador y tutor: el alumno es visible si sale
  en `alumnos_del_entrenador` o en `alumnos_del_tutor`. La captura y la
  corrección solo usan la del entrenador.
- Los comunicados que le tocan son los generales más los de las categorías de
  sus hijos **activos**; uno con `publicado` en el futuro todavía no sale.
- No hay modelo de temporada: la temporada es el año de la fecha de la
  evaluación (`Evaluacion.temporada`), como en el panel web.

### Observaciones y comunicados (migraciones 0009 y 0010)
- `Evaluacion.observaciones`: nota opcional del entrenador, hasta 500
  caracteres (`MAX_OBSERVACIONES`). Se captura igual desde la API y desde la
  captura web (y se corrige en la ficha), para que las dos capturas no se
  separen. El tutor la ve en el histórico junto con `capturada_por`.
- `Comunicado` se publica desde el admin; el autor es quien lo guarda. La
  migración 0010 da a la secretaria sus permisos.
- `seed_demo` deja tres comunicados y algunas observaciones para la demo,
  una mamá con cuenta activa (`5512345678` / `tutor`) y el código `CANCHA26`
  sin canjear para mostrar la activación (ver README).

## API
Prefijo `/api/v1/`. JSON. Autenticación JWT para el móvil; la web sigue con
sesiones de Django.

- `POST /api/v1/token/` y `/token/refresh/` — login y renovación
- `POST /api/v1/activar/` — alta de contraseña con código de activación
- `GET  /api/v1/mis-grupos/` — categorías y horarios del entrenador
- `GET  /api/v1/alumnos/?grupo=` — alumnos del grupo, con marca de si ya
  fueron evaluados hoy
- `POST /api/v1/evaluaciones/` — captura. Acepta un `client_uuid` para que la
  sincronización sea idempotente: reenviar la misma evaluación no duplica
- `PATCH /api/v1/evaluaciones/<id>/` — corrección, solo el mismo día
- `GET  /api/v1/mis-hijos/` — alumnos del tutor autenticado
- `GET  /api/v1/alumnos/<id>/evaluaciones/` — histórico y progresión
- `GET  /api/v1/comunicados/`
- `POST /api/v1/dispositivos/` — registro del push token de Expo

Los errores van como `{"detail": "..."}` con el código HTTP correcto. La app
móvil depende de ese formato.

## Comandos
```bash
source .venv/bin/activate
pip install -r requirements.txt
./bin/tailwindcss -i static/src/input.css -o static/css/tailwind.css --minify
python manage.py migrate
python manage.py seed_demo          # datos de ejemplo; --reset para limpiar
python manage.py runserver
python manage.py test               # antes de cerrar cualquier cambio
```

Para probar la API desde un celular en la misma red:
`python manage.py runserver 0.0.0.0:8000`, usando la IP local de la máquina.

## Contexto
Es el proyecto de la materia *Desarrollo de Aplicaciones Móviles Basadas en
Cómputo en la Nube* (ITT), de un equipo de cuatro, y el código se expone en
clase. Que se pueda explicar: nombres claros, funciones cortas y un comentario
donde la razón no sea obvia. Nada de abstracciones que el equipo no pueda
sostener frente al profesor.
