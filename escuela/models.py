import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models, transaction
from django.utils import timezone


class Categoria(models.TextChoices):
    """Categorías por edad. Valores de dominio fijos (no hay CRUD sobre ellos)."""

    MINI = "MINI", "Mini"
    MENOR = "MENOR", "Menor"
    MAYOR = "MAYOR", "Mayor"


class Horario(models.TextChoices):
    """Los dos horarios que puede tener cada categoría."""

    LUN_MIE = "LUN_MIE", "Lunes y Miércoles"
    MAR_JUE = "MAR_JUE", "Martes y Jueves"


# Los seis grupos (categoría + horario). La clave "MINI-LUN_MIE" es la misma en
# los filtros de la web y en el parámetro ?grupo= de la API.
GRUPOS = [
    (f"{c.value}-{h.value}", f"{c.label} · {h.label}")
    for c in Categoria
    for h in Horario
]


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
    # Cuenta con la que el tutor entra a la app móvil. Se crea al canjear su
    # código de activación; sus hijos son los alumnos que ya lo tienen asignado.
    usuario = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tutor",
        verbose_name="cuenta de la app",
    )

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
    # `fecha` es el día en que se evaluó en la cancha; `creada` es cuándo llegó
    # al servidor. Con la captura sin conexión pueden ser días distintos.
    creada = models.DateTimeField("registrada", auto_now_add=True)
    # Lo genera el teléfono. Si la app reenvía la misma evaluación al
    # sincronizar, se reconoce por este valor y no se duplica. La web lo deja vacío.
    client_uuid = models.UUIDField(
        "identificador del teléfono", unique=True, null=True, blank=True, editable=False
    )

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


class AsignacionEntrenador(models.Model):
    """Grupo (categoría + horario) que le toca a un entrenador.

    El administrador no necesita asignaciones: ve todos los grupos.
    """

    entrenador = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="asignaciones",
        limit_choices_to={"groups__name": "entrenador"},
        verbose_name="entrenador",
    )
    categoria = models.CharField("categoría", max_length=5, choices=Categoria.choices)
    horario = models.CharField("horario", max_length=7, choices=Horario.choices)

    class Meta:
        verbose_name = "asignación de entrenador"
        verbose_name_plural = "asignaciones de entrenadores"
        ordering = ["entrenador__username", "categoria", "horario"]
        constraints = [
            models.UniqueConstraint(
                fields=["entrenador", "categoria", "horario"],
                name="asignacion_unica_por_entrenador_y_grupo",
            )
        ]

    def __str__(self):
        return f"{self.entrenador} · {self.get_categoria_display()} · {self.get_horario_display()}"

    @property
    def grupo(self):
        """Clave del grupo, igual que en GRUPOS: "MINI-LUN_MIE"."""
        return f"{self.categoria}-{self.horario}"


# ---------------------------------------------------------------------------
# Modelos de la app móvil
# ---------------------------------------------------------------------------


# Sin 0/O ni 1/I/L para que el padre no se confunda al teclearlo.
ALFABETO_CODIGO = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
DIAS_VIGENCIA_CODIGO = 7


def generar_codigo():
    return "".join(secrets.choice(ALFABETO_CODIGO) for _ in range(8))


def vencimiento_codigo():
    return timezone.now() + timedelta(days=DIAS_VIGENCIA_CODIGO)


class CodigoYaUsado(Exception):
    """El código ya se canjeó o ya venció."""


class CodigoActivacion(models.Model):
    """Código de un solo uso que la escuela entrega al padre para crear su contraseña.

    Los padres no se registran solos: se trata de información de menores, así
    que la escuela genera el código desde el admin y el padre solo lo canjea.
    """

    tutor = models.ForeignKey(
        Tutor,
        on_delete=models.CASCADE,
        related_name="codigos",
        verbose_name="tutor",
    )
    codigo = models.CharField(
        "código", max_length=8, unique=True, default=generar_codigo, editable=False
    )
    creado = models.DateTimeField("creado", auto_now_add=True)
    vence = models.DateTimeField("vence", default=vencimiento_codigo)
    usado = models.DateTimeField("usado", null=True, blank=True)

    class Meta:
        verbose_name = "código de activación"
        verbose_name_plural = "códigos de activación"
        ordering = ["-creado"]

    def __str__(self):
        return f"{self.codigo} · {self.tutor}"

    @property
    def vigente(self):
        return self.usado is None and timezone.now() < self.vence

    def canjear(self, contrasena):
        """Crea (o reactiva) la cuenta del tutor con esta contraseña y gasta el código.

        El UPDATE condicionado a `usado IS NULL` es lo que garantiza el solo
        uso: si dos peticiones llegan a la vez, solo una actualiza la fila.
        Todo va en una transacción: si algo falla, el código sigue sin usarse.
        """
        with transaction.atomic():
            marcados = CodigoActivacion.objects.filter(
                pk=self.pk, usado__isnull=True, vence__gt=timezone.now()
            ).update(usado=timezone.now())
            if marcados == 0:
                raise CodigoYaUsado("El código ya se usó o ya venció.")

            usuario = self.tutor.usuario or self._crear_usuario()
            usuario.set_password(contrasena)
            usuario.is_active = True
            usuario.save(update_fields=["password", "is_active"])
            usuario.groups.add(Group.objects.get_or_create(name="tutor")[0])
        self.refresh_from_db(fields=["usado"])
        return usuario

    def _crear_usuario(self):
        """El padre inicia sesión con su teléfono, sin espacios: 5512345678."""
        tutor = self.tutor
        tutor.usuario = get_user_model().objects.create_user(
            username=tutor.telefono.replace(" ", ""),
            email=tutor.correo,
            first_name=tutor.nombre[:150],
        )
        tutor.save(update_fields=["usuario"])
        return tutor.usuario


class Dispositivo(models.Model):
    """Token de notificaciones push de Expo (ExponentPushToken[...])."""

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="dispositivos",
        verbose_name="usuario",
    )
    # Único: si otro usuario inicia sesión en el mismo celular, el token se le reasigna.
    token = models.CharField("token de Expo", max_length=255, unique=True)
    registrado = models.DateTimeField("registrado", auto_now_add=True)
    actualizado = models.DateTimeField("actualizado", auto_now=True)

    class Meta:
        verbose_name = "dispositivo"
        verbose_name_plural = "dispositivos"

    def __str__(self):
        return f"{self.usuario} · {self.token}"


class Comunicado(models.Model):
    """Aviso de la escuela. Sin categoría va para todos."""

    titulo = models.CharField("título", max_length=120)
    cuerpo = models.TextField("mensaje")
    categoria = models.CharField(
        "categoría",
        max_length=5,
        choices=Categoria.choices,
        blank=True,
        help_text="Déjala vacía para enviarlo a todas las categorías.",
    )
    publicado = models.DateTimeField("publicado", default=timezone.now)
    autor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="comunicados",
        verbose_name="autor",
    )

    class Meta:
        verbose_name = "comunicado"
        verbose_name_plural = "comunicados"
        ordering = ["-publicado"]

    def __str__(self):
        return self.titulo
