from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models


class Categoria(models.TextChoices):
    """Categorías por edad. Valores de dominio fijos (no hay CRUD sobre ellos)."""

    MINI = "MINI", "Mini"
    MENOR = "MENOR", "Menor"
    MAYOR = "MAYOR", "Mayor"


class Horario(models.TextChoices):
    """Los dos horarios que puede tener cada categoría."""

    LUN_MIE = "LUN_MIE", "Lunes y Miércoles"
    MAR_JUE = "MAR_JUE", "Martes y Jueves"


validar_telefono = RegexValidator(
    regex=r"^\d{2} \d{4} \d{4}$",
    message="Ingresa 10 dígitos con el formato 55 1234 5678.",
)


class Tutor(models.Model):
    """Padre, madre o responsable. Un tutor puede tener varios alumnos (hermanos)."""

    nombre = models.CharField("nombre completo", max_length=120)
    telefono = models.CharField(
        "teléfono de contacto",
        max_length=14,
        validators=[validar_telefono],
        help_text="Formato: 55 1234 5678",
    )
    correo = models.EmailField("correo electrónico", blank=True)

    class Meta:
        verbose_name = "tutor"
        verbose_name_plural = "tutores"
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre


class Alumno(models.Model):
    nombre = models.CharField("nombre completo", max_length=120)
    fecha_nacimiento = models.DateField("fecha de nacimiento")
    categoria = models.CharField("categoría", max_length=5, choices=Categoria.choices)
    horario = models.CharField("horario", max_length=7, choices=Horario.choices)
    tutor = models.ForeignKey(
        Tutor,
        on_delete=models.PROTECT,
        related_name="alumnos",
        verbose_name="tutor",
    )
    activo = models.BooleanField("activo", default=True)
    fecha_alta = models.DateTimeField("fecha de alta", auto_now_add=True)

    class Meta:
        verbose_name = "alumno"
        verbose_name_plural = "alumnos"
        ordering = ["nombre"]

    def __str__(self):
        return f"{self.folio} · {self.nombre}"

    @property
    def folio(self):
        """Identificador visible tipo VS-0142 (deriva del id, no se guarda)."""
        return f"VS-{self.pk:04d}" if self.pk else "VS-----"


class Evaluacion(models.Model):
    alumno = models.ForeignKey(
        Alumno,
        on_delete=models.CASCADE,
        related_name="evaluaciones",
        verbose_name="alumno",
    )
    fecha = models.DateField("fecha")
    pase = models.PositiveSmallIntegerField(
        "pase", validators=[MinValueValidator(1), MaxValueValidator(10)]
    )
    recepcion = models.PositiveSmallIntegerField(
        "recepción", validators=[MinValueValidator(1), MaxValueValidator(10)]
    )
    tiro = models.PositiveSmallIntegerField(
        "tiro", validators=[MinValueValidator(1), MaxValueValidator(10)]
    )
    capturada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="evaluaciones_capturadas",
        verbose_name="capturada por",
    )
    creada = models.DateTimeField("registrada", auto_now_add=True)

    class Meta:
        verbose_name = "evaluación"
        verbose_name_plural = "evaluaciones"
        ordering = ["-fecha", "alumno__nombre"]
        constraints = [
            models.UniqueConstraint(
                fields=["alumno", "fecha"],
                name="evaluacion_unica_por_alumno_y_fecha",
            )
        ]

    def __str__(self):
        return f"{self.alumno.nombre} · {self.fecha:%d/%m/%Y} · {self.promedio}"

    @property
    def promedio(self):
        valores = [self.pase, self.recepcion, self.tiro]
        if any(v is None for v in valores):
            return None
        return round(sum(valores) / 3, 1)
