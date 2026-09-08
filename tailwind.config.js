/** @type {import('tailwindcss').Config} */
// Tokens extraídos de design/design.html (sección "08 / DESIGN TOKENS").
// Los hex son exactos, no aproximados. Nunca usar hex sueltos en templates:
// siempre a través de estas clases (bg-*, text-*, border-*).
module.exports = {
  content: [
    './templates/**/*.html',
    './escuela/**/*.{html,py}',
  ],
  theme: {
    // Paleta cerrada: solo los colores del diseño, sin la paleta default de Tailwind.
    colors: {
      transparent: 'transparent',
      current: 'currentColor',

      // --- Tokens nombrados del diseño ---
      'bg-base': '#12081F',          // Fondo de aplicación e inputs sobre superficie
      'bg-surface': '#1E1033',       // Tarjetas, tablas, modales, barra de navegación
      'border': '#2D1B4E',           // Bordes, encabezado de tabla, divisores, elevación
      'accent': '#C6FF00',           // Botón primario, cifra clave, fila activa, serie principal
      'accent-secondary': '#7B2FF7', // Filtro activo, avatares, barras y segunda serie
      'text-primary': '#F5F3FA',     // Títulos, nombres, calificaciones
      'text-muted': '#A79FB8',       // Etiquetas, metadatos, columnas secundarias
      'success': '#3DDC91',          // Deltas positivos, confirmación de guardado
      'danger': '#FF4D6D',           // Error de validación, acción destructiva
    },
    extend: {
      fontFamily: {
        // Datos, tablas y cuerpo
        sans: ['Barlow', 'system-ui', '-apple-system', 'sans-serif'],
        // Display: títulos, marca, números y calificaciones
        display: ['"Barlow Condensed"', '"Barlow"', 'system-ui', 'sans-serif'],
        // IDs, fechas, teléfonos, specs
        mono: ['"IBM Plex Mono"', 'ui-monospace', 'SFMono-Regular', 'monospace'],
      },
      maxWidth: {
        app: '1440px', // Contenedor máximo (breakpoint 2xl del diseño)
      },
      borderRadius: {
        lg: '8px',  // Controles
        xl: '12px', // Tarjetas
      },
    },
  },
  plugins: [],
}
