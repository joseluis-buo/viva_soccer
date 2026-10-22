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
- El binario standalone de Tailwind (v3.4.17). No se versiona (pesa ~40 MB):
  `python bin/compilar_css.py` lo descarga a `bin/tailwindcss` la primera vez.

## Puesta en marcha

```bash
# 1. Entorno virtual e dependencias
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 2. Compilar el CSS de Tailwind (genera static/css/tailwind.css; descarga
#    el binario si no está)
python bin/compilar_css.py

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
| `DJANGO_DEBUG`           | `1` encendido, `0` apagado. En Railway siempre apagado | Encendido (fuera de Railway)   |
| `DJANGO_ALLOWED_HOSTS`   | Hosts permitidos, separados por coma       | `127.0.0.1,localhost`; error si `DEBUG` está apagado |
| `DJANGO_CSRF_TRUSTED`    | Orígenes de confianza para CSRF, con `https://` | Ninguno                               |
| `TEST_POSTGRES`          | `1` corre las pruebas contra `DATABASE_URL` | Pruebas en SQLite en memoria              |

**En desarrollo** se ponen en un archivo `.env` en la raíz (copia de
`.env.example`), que `settings.py` carga al arrancar con `python-dotenv`. El
`.env` tiene la contraseña real y está en `.gitignore`: nunca se sube.

**En producción el `.env` no se usa.** Las variables las da la plataforma donde
corre la app (su panel de variables de entorno). Si por error hubiera un `.env`,
las variables de la plataforma tienen prioridad: `load_dotenv` no sobrescribe
las que ya existen.

## Despliegue en Railway

La web y la API corren en un servicio de Railway conectado al repositorio de
GitHub. **La base sigue siendo la de Neon**: Railway no tiene base propia, y
la web y la app móvil comparten la misma.

### Qué hay en el repositorio

| Archivo                | Para qué |
|------------------------|----------|
| `railway.json`         | Build, migraciones y comando de inicio (Railway lo lee solo) |
| `.python-version`      | Python 3.12 (sin él, Railway usaría 3.13) |
| `bin/compilar_css.py`  | Descarga Tailwind v3.4.17 si falta y compila el CSS |

En cada push a `main`, Railway hace esto:

1. **Build**: instala `requirements.txt`, compila el CSS de Tailwind y corre
   `collectstatic`. WhiteNoise sirve los estáticos desde gunicorn, comprimidos
   y con hash en el nombre.
2. **Pre-deploy**: `python manage.py migrate` contra Neon. Si una migración
   falla, el despliegue se detiene y la versión anterior sigue en línea.
3. **Inicio**: `gunicorn vivasoccer.wsgi --workers 2`. Gunicorn escucha en el
   puerto que da Railway en `$PORT`.

> [!IMPORTANT]
> Como el pre-deploy migra la base compartida, **una migración que llega a
> `main` se aplica en Neon para los cuatro**. Revisen las migraciones antes de
> hacer merge.

### Por qué el CSS se compila en el build

`static/css/tailwind.css` es un archivo generado y sigue en `.gitignore`. Se
compila en Railway en lugar de versionarlo porque:

- Si se versionara, alguien que agrega una clase en una plantilla y olvida
  recompilar subiría un CSS viejo, y en producción esa clase no existiría.
  Compilando en el build, el CSS siempre corresponde a las plantillas de ese
  commit.
- El CSS minificado es una sola línea: con cuatro personas recompilando, cada
  merge tendría conflictos en ese archivo.

El costo es que el build descarga el binario de Tailwind de GitHub (~40 MB).
La versión está fijada en `bin/compilar_css.py`, así que el resultado es el
mismo que en local.

### Variables de entorno en Railway

En el servicio → **Variables**:

| Variable               | Valor |
|------------------------|-------|
| `DATABASE_URL`         | La cadena de conexión de Neon, la misma del `.env` |
| `DJANGO_SECRET_KEY`    | Una llave nueva y larga, distinta de la de desarrollo (ver abajo) |
| `DJANGO_ALLOWED_HOSTS` | El dominio de Railway, sin `https://`: `vivasoccer.up.railway.app` |
| `DJANGO_CSRF_TRUSTED`  | El mismo dominio, con `https://`: `https://vivasoccer.up.railway.app` |
| `DJANGO_DEBUG`         | `0` (opcional: en Railway `DEBUG` se apaga siempre) |

Para generar la llave:

```bash
python -c "from django.core.management.utils import get_random_secret_key as k; print(k())"
```

Si falta `DATABASE_URL`, `DJANGO_SECRET_KEY` o `DJANGO_ALLOWED_HOSTS`, el build
falla con un mensaje que dice cuál. `settings.py` reconoce que está en Railway
por la variable `RAILWAY_ENVIRONMENT_NAME`, que Railway pone sola.

### Pasos en el panel de Railway

1. **New Project → Deploy from GitHub repo** y elegir este repositorio. Si
   Railway sugiere agregar PostgreSQL, **no aceptar**: la base es Neon.
2. En el servicio → **Settings → Networking → Generate Domain**. Anotar el
   dominio (`algo.up.railway.app`).
3. En **Variables**, capturar las cinco de la tabla con ese dominio. No usar
   variables de referencia a un Postgres de Railway (`${{Postgres...}}`).
4. Hacer **Deploy** (o un push a `main`). En **Deployments** se ven los logs del
   build, del pre-deploy (migraciones) y de gunicorn.
5. Entrar a `https://<dominio>/` con un usuario existente en Neon.
6. En la app móvil, cambiar la URL de la API a `https://<dominio>/api/v1/`.

Para verificar que no hay base de Railway: en el lienzo del proyecto solo debe
aparecer el servicio de la web, sin un cuadro de PostgreSQL.

`seed_demo --reset` se niega en producción. Los usuarios demo de Neon (con
contraseñas conocidas) quedan accesibles en el dominio público: sirven para la
exposición, pero no se deben cargar alumnos reales en esa base mientras existan.

## Usuarios demo

| Usuario       | Contraseña    | Rol           | Pantalla de inicio |
|---------------|---------------|---------------|--------------------|
| `admin`       | `admin`       | administrador | Panel              |
| `secretaria`  | `secretaria`  | secretaria    | Padrón             |
| `entrenador`  | `entrenador`  | entrenador    | Captura            |
| `5512345678`  | `tutor`       | tutor         | App móvil, modo Familia |

El tutor demo es Marisol Ruiz, mamá de Diego Salinas (Menor · Martes y Jueves).
Como todos los padres, entra con su teléfono sin espacios y **solo desde la app
móvil**; la web no tiene pantallas para tutores.

**Código de activación demo: `CANCHA26`**, de Hugo Ocampo, papá de Renata
(Mini). Hugo no tiene cuenta todavía: sirve para mostrar el flujo de activación
en la app (código + contraseña nueva → entra al modo Familia como `5588712210`).
Vence a los 7 días; volver a correr `seed_demo` lo renueva si ya venció o ya se
canjeó. Para repetir la activación desde cero (sin cuenta previa de Hugo), usa
`seed_demo --reset`.

- **administrador**: todo lo de los otros dos roles, más el panel con indicadores.
- **secretaria**: padrón (alta, edición, baja y reactivación de alumnos),
  tutores, corrección de evaluaciones desde la ficha y boletas imprimibles
  (por alumno o por grupo). No ve el panel ni la captura.
- **entrenador**: solo la pantalla de captura de evaluaciones (mobile-first).

Un usuario con sesión que entra a una pantalla de otro rol se manda a su propia
pantalla de inicio.

`seed_demo` es idempotente: sin `--reset` solo agrega lo que falta y no borra nada.

> [!WARNING]
> **`seed_demo --reset` borra datos de todo el equipo.** Borra el padrón, las
> evaluaciones y **todas las cuentas de los padres** de la base a la que apunte
> tu `DATABASE_URL`. Si es la de Neon, se borra para los cuatro.
>
> - Pide escribir el nombre de la base para confirmar (`neondb` en Neon,
>   `db.sqlite3` en local). Si no coincide, no borra nada.
> - Con `DJANGO_DEBUG=0` (producción) se niega siempre.
> - Avisa al equipo antes de usarlo contra Neon.
>
> Para scripts: `python manage.py seed_demo --reset --confirmar <nombre de la base>`.

Estos usuarios y el código tienen contraseñas conocidas: son solo para la base
de desarrollo y la demostración, nunca para una base con alumnos reales.

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
bin/compilar_css.py Descarga Tailwind si falta y compila el CSS
railway.json        Configuración del despliegue en Railway
static/             input.css de Tailwind, CSS compilado, HTMX y Chart.js locales
design/design.html  Referencia visual y tokens de diseño
```
