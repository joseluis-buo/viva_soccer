# VIVA SOCCER

App web para gestionar una escuela de fútbol infantil en Tijuana: padrón de
alumnos, captura de evaluaciones en la cancha y seguimiento de la progresión
por temporada.

## Stack

- Python 3.12, Django 5.2
- SQLite en desarrollo (PostgreSQL en producción)
- HTMX para la interactividad, sin build de JS
- Tailwind CSS 3.4 (binario standalone, sin Node)
- Chart.js para las gráficas

## Requisitos

- Python 3.12+
- El binario `bin/tailwindcss` (v3.4, standalone) ya viene incluido. Si falta,
  descárgalo de https://github.com/tailwindlabs/tailwindcss/releases y colócalo
  en `bin/tailwindcss` con permiso de ejecución.

## Puesta en marcha

```bash
# 1. Entorno virtual e dependencias
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 2. Compilar el CSS de Tailwind (genera static/css/tailwind.css)
./bin/tailwindcss -i static/src/input.css -o static/css/tailwind.css --minify

# 3. Base de datos
python manage.py migrate

# 4. Datos de ejemplo + usuarios demo (8 alumnos con histórico de evaluaciones)
python manage.py seed_demo

# 5. Servidor de desarrollo
python manage.py runserver
```

Abre http://127.0.0.1:8000/ y entra con uno de los usuarios demo.

## Usuarios demo

| Usuario       | Contraseña    | Rol           | Pantalla de inicio |
|---------------|---------------|---------------|--------------------|
| `admin`       | `admin`       | administrador | Panel              |
| `secretaria`  | `secretaria`  | secretaria    | Padrón             |
| `entrenador`  | `entrenador`  | entrenador    | Captura            |

- **administrador**: todo lo de los otros dos roles, más el panel con indicadores.
- **secretaria**: padrón (alta, edición, baja y reactivación de alumnos),
  tutores, corrección de evaluaciones desde la ficha y boletas imprimibles
  (por alumno o por grupo). No ve el panel ni la captura.
- **entrenador**: solo la pantalla de captura de evaluaciones (mobile-first).

Un usuario con sesión que entra a una pantalla de otro rol se manda a su propia
pantalla de inicio.

`seed_demo` es idempotente. Con `--reset` borra el padrón y las evaluaciones
antes de recargar.

## Desarrollo del CSS

Tailwind no corre en el request. Al tocar plantillas o `static/src/input.css`,
recompila el CSS (deja `--watch` corriendo en otra terminal):

```bash
./bin/tailwindcss -i static/src/input.css -o static/css/tailwind.css --watch
```

Los colores y tipografías salen de `tailwind.config.js` (tokens tomados de
`design/design.html`). Nunca se usan hex sueltos en las plantillas.

## Pruebas

```bash
python manage.py test
```

Cubren el cálculo de promedio y folio, la restricción de una evaluación por
alumno y fecha, la validación del teléfono, la separación de accesos por rol,
el guardado de la pantalla de captura y las funciones de secretaria (tutores,
baja, corrección de evaluaciones y boletas).

## Estructura

```
escuela/            App principal
  models.py         Tutor, Alumno, Evaluacion, Categoria, Horario
  views.py          dashboard, padrón, ficha, captura, tutores, evaluaciones, boletas
  roles.py          es_administrador / es_secretaria / es_entrenador y sus decoradores
  forms.py          AlumnoForm, TutorForm, EvaluacionForm
  admin.py          Django admin de Tutor, Alumno y Evaluacion
  management/commands/seed_demo.py
templates/          Plantillas (base + escuela/*)
static/             input.css de Tailwind, CSS compilado, HTMX y Chart.js locales
design/design.html  Referencia visual y tokens de diseño
```
