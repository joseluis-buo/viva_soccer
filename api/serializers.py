from datetime import timedelta

from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.tokens import RefreshToken

from escuela.models import Alumno, Evaluacion
from escuela.roles import es_administrador, es_entrenador, es_secretaria, es_tutor

# En orden de prioridad: el primero que aplica es el rol principal. Con él la
# app decide si abre el modo Entrenador o el modo Familia.
ROLES = [
    ("administrador", es_administrador),
    ("secretaria", es_secretaria),
    ("entrenador", es_entrenador),
    ("tutor", es_tutor),
]


def roles_de(usuario):
    return [nombre for nombre, tiene_rol in ROLES if tiene_rol(usuario)]


def datos_de_sesion(usuario):
    """Tokens más lo que la app necesita para elegir su modo.

    `roles` lleva todos (un entrenador puede ser también papá de un alumno);
    `rol` es el principal.
    """
    roles = roles_de(usuario)
    if not roles:
        raise PermissionDenied("Tu cuenta no tiene un rol asignado en la escuela.")
    refresh = RefreshToken.for_user(usuario)
    return {
        "access": str(refresh.access_token),
        "refresh": str(refresh),
        "rol": roles[0],
        "roles": roles,
        "nombre": nombre_de(usuario),
    }


class LoginSerializer(TokenObtainPairSerializer):
    """Login de simplejwt (usuario y contraseña) con rol y nombre en la respuesta."""

    def validate(self, attrs):
        super().validate(attrs)  # valida las credenciales y deja self.user
        return datos_de_sesion(self.user)


class ActivacionSerializer(serializers.Serializer):
    codigo = serializers.CharField(max_length=20)
    contrasena = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate_codigo(self, valor):
        # El padre lo puede teclear en minúsculas o con espacios.
        return valor.replace(" ", "").upper()


# ---------------------------------------------------------------------------
# Entrenador: alumnos y evaluaciones
# ---------------------------------------------------------------------------

DIAS_ATRAS_PERMITIDOS = 7


class FichaAlumnoSerializer(serializers.ModelSerializer):
    folio = serializers.CharField(read_only=True)

    class Meta:
        model = Alumno
        fields = ["id", "folio", "nombre", "categoria", "horario"]


class AlumnoSerializer(FichaAlumnoSerializer):
    """Alumno de la lista de captura. `evaluacion_hoy` es el id para corregirla, o null."""

    evaluado_hoy = serializers.SerializerMethodField()
    evaluacion_hoy = serializers.SerializerMethodField()

    class Meta(FichaAlumnoSerializer.Meta):
        fields = FichaAlumnoSerializer.Meta.fields + ["evaluado_hoy", "evaluacion_hoy"]

    def get_evaluacion_hoy(self, alumno):
        # La vista deja en el contexto {alumno_id: evaluacion_id} con una sola consulta.
        return self.context["evaluadas_hoy"].get(alumno.id)

    def get_evaluado_hoy(self, alumno):
        return alumno.id in self.context["evaluadas_hoy"]


class EvaluacionSerializer(serializers.ModelSerializer):
    """Lo que la API devuelve de una evaluación. Promedio y folio los calcula el modelo."""

    folio = serializers.CharField(source="alumno.folio", read_only=True)
    alumno_nombre = serializers.CharField(source="alumno.nombre", read_only=True)
    promedio = serializers.FloatField(read_only=True)
    capturada_por = serializers.SerializerMethodField()

    class Meta:
        model = Evaluacion
        fields = [
            "id",
            "alumno",
            "folio",
            "alumno_nombre",
            "fecha",
            "pase",
            "recepcion",
            "tiro",
            "promedio",
            "capturada_por",
            "creada",
            "client_uuid",
        ]
        read_only_fields = fields

    def get_capturada_por(self, evaluacion):
        return nombre_de(evaluacion.capturada_por)


class CapturaSerializer(serializers.Serializer):
    """Lo que manda el teléfono. Cualquier otro campo (promedio, folio…) se ignora."""

    client_uuid = serializers.UUIDField()
    alumno = serializers.IntegerField()
    fecha = serializers.DateField(required=False)
    pase = serializers.IntegerField(min_value=1, max_value=10)
    recepcion = serializers.IntegerField(min_value=1, max_value=10)
    tiro = serializers.IntegerField(min_value=1, max_value=10)

    def validate_fecha(self, fecha):
        """La fecha es la del día en la cancha: puede llegar días después, pero no del futuro."""
        hoy = timezone.localdate()
        if fecha > hoy:
            raise serializers.ValidationError("No puede ser una fecha futura.")
        if fecha < hoy - timedelta(days=DIAS_ATRAS_PERMITIDOS):
            raise serializers.ValidationError(
                f"No puede tener más de {DIAS_ATRAS_PERMITIDOS} días de antigüedad."
            )
        return fecha


class CorreccionSerializer(serializers.Serializer):
    """En una corrección solo cambian las calificaciones; alumno y fecha se quedan."""

    pase = serializers.IntegerField(min_value=1, max_value=10, required=False)
    recepcion = serializers.IntegerField(min_value=1, max_value=10, required=False)
    tiro = serializers.IntegerField(min_value=1, max_value=10, required=False)


def nombre_de(usuario):
    if usuario is None:
        return None
    return usuario.get_full_name() or usuario.username
