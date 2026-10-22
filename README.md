# VIVA SOCCER

App web para gestionar una escuela de fútbol infantil en Tijuana: padrón de
alumnos, captura de evaluaciones en la cancha y seguimiento de la progresión
por temporada.

## Stack

- Python 3.12, Django 5.2
- SQLite en desarrollo, PostgreSQL administrado (Neon) en la nube
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

# 3. Variables de entorno (ver "Configuración" abajo)
cp .env.example .env    # y pon la contraseña real

# 4. Base de datos
python manage.py migrate

# 5. Datos de ejemplo + usuarios demo (8 alumnos con histórico de evaluaciones)
python manage.py seed_demo

# 6. Servidor de desarrollo
python manage.py runserver
```

Abre http://127.0.0.1:8000/ y entra con uno de los usuarios demo.

## Configuración

`settings.py` lee estas variables de entorno:

| Variable                 | Para qué                                   | Si falta                                   |
|--------------------------|--------------------------------------------|--------------------------------------------|
| `DATABASE_URL`           | Conexión a PostgreSQL (Neon)               | SQLite local; error si `DEBUG` está apagado |
| `DJANGO_SECRET_KEY`      | Llave secreta de Django                    | Llave de desarrollo; error si `DEBUG` está apagado |
| `DJANGO_DEBUG`           | `1` encendido, `0` apagado                 | Encendido                                  |
| `DJANGO_ALLOWED_HOSTS`   | Hosts permitidos, separados por coma       | `127.0.0.1,localhost`                      |
| `DJANGO_CSRF_TRUSTED`    | Orígenes de confianza para CSRF            | Ninguno                                    |
| `TEST_POSTGRES`          | `1` corre las pruebas contra `DATABASE_URL` | Pruebas en SQLite en memoria              |

**En desarrollo** se ponen en un archivo `.env` en la raíz (copia de
`.env.example`), que `settings.py` carga al arrancar con `python-dotenv`. El
`.env` tiene la contraseña real y está en `.gitignore`: nunca se sube.

**En producción el `.env` no se usa.** Las variables las da la plataforma donde
corre la app (su panel de variables de entorno). Si por error hubiera un `.env`,
las variables de la plataforma tienen prioridad: `load_dotenv` no sobrescribe
las que ya existen.

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
python manage.py test                      # SQLite en memoria (lo normal)
TEST_POSTGRES=1 python manage.py test      # contra PostgreSQL (DATABASE_URL)
```

Por omisión las pruebas usan **SQLite en memoria**, aunque el `.env` tenga
`DATABASE_URL`: tardan segundos y nunca tocan Neon. No hay que exportar nada.

Con `TEST_POSTGRES=1` corren contra el servidor de `DATABASE_URL`. Django crea
ahí una base aparte (`test_<nombre>`) y la borra al terminar, así que no toca
los datos reales, pero tarda un par de minutos. Conviene correrlas así antes de
una entrega o al tocar algo que dependa del motor (restricciones, transacciones,
el UPDATE condicionado del canje de códigos). Si falta `DATABASE_URL`, falla
con un mensaje claro.

Cubren el cálculo de promedio y folio, la restricción de una evaluación por
alumno y fecha, la validación del teléfono, la separación de accesos por rol,
el guardado de la pantalla de captura, las funciones de secretaria (tutores,
baja, corrección de evaluaciones y boletas) y la API móvil (login con JWT,
renovación de tokens y activación de tutores).

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
