# VIVA SOCCER — Primera entrega de avance

Fecha: 2026-09-08

## Resumen

El flujo completo del producto funciona de punta a punta: los dos roles
(administrador y entrenador) tienen su pantalla, la captura de evaluaciones
guarda y actualiza, y el histórico alimenta las gráficas de progresión. La app
sigue la referencia visual de `design/design.html` y sus tokens.

Para probarlo: seguir el README y entrar con `admin/admin` o
`entrenador/entrenador`.

## Lo que ya está

### Dominio y datos
- Modelos `Alumno` y `Evaluacion` con las reglas del negocio:
  - categorías MINI / MENOR / MAYOR y los dos horarios por categoría,
  - alumno con tutor y teléfono validado (formato `55 1234 5678`),
  - evaluación de PASE, RECEPCIÓN y TIRO en escala 1–10,
  - una sola evaluación por alumno y fecha (restricción en base de datos),
  - folio visible tipo `VS-0142` derivado del id.
- Migraciones al día. La migración `0002` crea los grupos `administrador` y
  `entrenador`.
- Comando `seed_demo`: 8 alumnos con seis fechas de evaluación cada uno
  (progresión ascendente, determinista) y los dos usuarios demo.

### Roles y acceso
- `es_administrador` / `es_entrenador` y decoradores de vista.
- El administrador puede todo; el entrenador solo entra a Captura.
- `/` redirige a cada rol a su pantalla de inicio.

### Pantallas
| Pantalla            | Ruta               | Rol           | Estado |
|---------------------|--------------------|---------------|--------|
| Acceso              | `/acceso/`         | —             | Listo  |
| Panel / Dashboard   | `/panel/`          | administrador | Listo  |
| Padrón + panel lateral | `/padron/`      | administrador | Listo  |
| Alta / edición de alumno | modal HTMX    | administrador | Listo  |
| Ficha de alumno     | `/padron/<id>/`    | administrador | Listo  |
| Captura (mobile-first) | `/captura/`     | entrenador    | Listo  |
| Django admin        | `/admin/`          | administrador | Listo  |

- **Panel**: alumnos activos, conteo por categoría, evaluaciones del mes,
  promedio general y por habilidad, gráfica de barras por categoría y ranking
  de mayor progreso reciente.
- **Padrón**: búsqueda por nombre, filtro por grupo (categoría + horario),
  paginación y panel lateral con la última evaluación y su miniprogresión SVG.
- **Ficha**: encabezado con promedio del alumno vs. su categoría y la
  diferencia, gráfica de líneas de progresión y tabla del histórico.
- **Captura**: selector de grupo y fecha, barra de avance, una tarjeta por
  alumno con tres campos numéricos y guardado en bloque. Reenviar actualiza en
  lugar de duplicar.

### Calidad
- Suite de pruebas (`python manage.py test`): 17 pruebas sobre reglas de
  dominio, permisos por rol y guardado de captura.
- `python manage.py check` sin observaciones.
- HTMX y Chart.js servidos localmente (la captura se usa en la cancha, sin red
  fiable).

## Pendiente / siguiente iteración

- Endurecer para producción: `SECRET_KEY` fuera del código, `DEBUG=False`,
  `ALLOWED_HOSTS`, configuración de PostgreSQL y de archivos estáticos.
- Gestión de usuarios y contraseñas desde la UI (hoy solo por `seed_demo` o el
  Django admin).
- Exportar el padrón y las evaluaciones (CSV) para la coordinación.
- Edición y borrado de una evaluación puntual desde la ficha.
- Confirmación visual al guardar en captura sin recargar toda la página.
- Reporte por alumno para entregar a los tutores.

## Notas de decisiones

- Tailwind se compila con el binario standalone (`bin/tailwindcss`), sin Node ni
  build de JS, para mantener el entorno simple.
- El binario de Tailwind, el CSS compilado y `db.sqlite3` están en `.gitignore`:
  el CSS se regenera y la base se recrea con `migrate` + `seed_demo`.
- Los colores viven solo en `tailwind.config.js` y su espejo `static/js/paleta.js`
  (para Chart.js); las plantillas no llevan hex.
