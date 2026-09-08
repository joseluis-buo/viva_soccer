# VIVA SOCCER

App web para gestionar una escuela de fútbol infantil en Tijuana.

## Stack
- Python 3.12, Django 5.x
- SQLite en desarrollo, PostgreSQL en producción
- HTMX para interactividad, sin React ni build de JS
- Tailwind CSS
- Chart.js para las gráficas

## Dominio
- Alumnos menores de edad, con tutor y teléfono de contacto
- Tres categorías por edad: MINI, MENOR, MAYOR
- Cada categoría tiene dos horarios: "Lunes y Miércoles" o "Martes y Jueves"
- Cada alumno se evalúa en PASE, RECEPCIÓN y TIRO, escala 1-10
- Las evaluaciones se registran por fecha, hay histórico y progresión
- Dos roles: administrador (padrón completo) y entrenador (captura)

## Reglas
- Todo en español: modelos, campos, vistas, comentarios, UI
- La referencia visual está en design/design.html
- Los colores salen de tailwind.config.js, nunca hex sueltos en templates
- La pantalla de captura de evaluaciones es mobile-first, es la que
  más se usa y se usa en la cancha
- No metas dependencias sin avisar
