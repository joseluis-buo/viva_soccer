# VIVA SOCCER

App web para gestionar una escuela de fútbol infantil en Tijuana.

Ahora se le agrega una **API REST** para que una app móvil (proyecto hermano
`vsoccer-movil`, en React Native + Expo) comparta la misma base de datos en la
nube. La web la sigue usando el administrador; la app móvil la usan los
entrenadores, para capturar desde la cancha, y los padres de familia, para
consultar el desempeño de sus hijos.

## Stack
- Python 3.12, Django 5.x
- SQLite en desarrollo, PostgreSQL administrado en producción (Neon)
- HTMX para interactividad, sin React ni build de JS
- Tailwind CSS
- Chart.js para las gráficas
- Django REST Framework + djangorestframework-simplejwt (para la API móvil)

## Dominio
- Alumnos menores de edad, con tutor y teléfono de contacto
- Tres categorías por edad: MINI, MENOR, MAYOR
- Cada categoría tiene dos horarios: "Lunes y Miércoles" o "Martes y Jueves"
- Cada alumno se evalúa en PASE, RECEPCIÓN y TIRO, escala 1-10
- Las evaluaciones se registran por fecha, hay histórico y progresión
- Tres roles: administrador (padrón completo), entrenador (captura) y
  tutor (consulta, solo desde la app móvil)

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
Ya existen `Alumno`, `Evaluacion`, `Categoria`, `Horario` y los roles en
`escuela/roles.py`.

Se agregan para la versión móvil:

- `CuentaTutor` — la cuenta con la que el padre inicia sesión, vinculada a un
  `User`, con relación N:M a `Alumno`. **Ojo:** no confundir con los datos de
  tutor y teléfono que ya guarda `Alumno` como texto. Aquellos son el contacto
  de la escuela; este es el acceso a la app. Un padre puede tener varios
  hijos y un alumno puede tener más de un tutor con cuenta.
- `CodigoActivacion` — código de un solo uso que la escuela entrega al padre
  para que cree su contraseña. **Los padres no se registran solos**: se trata
  de información de menores.
- `Dispositivo` — token de notificaciones push de Expo, ligado a un `User`.
- `Comunicado` — aviso de la escuela, opcionalmente dirigido a una categoría.

El rol `tutor` se suma a `roles.py` con su decorador, igual que los existentes.

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
