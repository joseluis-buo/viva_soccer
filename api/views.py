from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as ErrorDeDjango
from django.db import IntegrityError, transaction
from django.db.models import Count, Q
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView

from escuela.models import (
    GRUPOS,
    CodigoActivacion,
    CodigoYaUsado,
    Comunicado,
    Dispositivo,
    Evaluacion,
)
from escuela.roles import alumnos_del_entrenador, alumnos_del_tutor, grupos_de

from .errores import Conflicto, Vencido
from .permisos import SoloEntrenador, SoloTutor
from .serializers import (
    ActivacionSerializer,
    AlumnoSerializer,
    CapturaSerializer,
    ComunicadoSerializer,
    CorreccionSerializer,
    DispositivoSerializer,
    EvaluacionHistorialSerializer,
    EvaluacionSerializer,
    FichaAlumnoSerializer,
    HijoSerializer,
    LoginSerializer,
    datos_de_sesion,
    nombre_de,
)


class LoginView(TokenObtainPairView):
    """POST usuario y contraseña → access, refresh, rol, roles y nombre."""

    serializer_class = LoginSerializer
    throttle_scope = "login"


class ActivarView(APIView):
    """POST código y contraseña nueva → crea la cuenta del tutor y la deja con sesión."""

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_scope = "activacion"

    def post(self, request):
        datos = ActivacionSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        codigo = self._buscar_vigente(datos.validated_data["codigo"])
        contrasena = datos.validated_data["contrasena"]
        self._validar_contrasena(codigo.tutor, contrasena)

        try:
            usuario = codigo.canjear(contrasena)
        except CodigoYaUsado:
            # Otra petición lo canjeó entre la búsqueda y el canje.
            raise Conflicto("Este código ya se usó.")
        except IntegrityError:
            raise Conflicto(
                "Ya existe una cuenta con el teléfono de este tutor. "
                "Pide ayuda en la escuela."
            )
        return Response(datos_de_sesion(usuario), status=status.HTTP_201_CREATED)

    def _buscar_vigente(self, texto):
        """Distingue los tres casos para que la app muestre el mensaje correcto."""
        codigo = (
            CodigoActivacion.objects.select_related("tutor__usuario")
            .filter(codigo=texto)
            .first()
        )
        if codigo is None:
            raise NotFound("El código no existe. Revisa que esté bien escrito.")
        if codigo.usado is not None:
            raise Conflicto("Este código ya se usó. Pide uno nuevo en la escuela.")
        if codigo.vence <= timezone.now():
            raise Vencido("Este código ya venció. Pide uno nuevo en la escuela.")
        return codigo

    def _validar_contrasena(self, tutor, contrasena):
        """Aplica AUTH_PASSWORD_VALIDATORS, comparando contra el teléfono y el nombre."""
        usuario = tutor.usuario or get_user_model()(
            username=tutor.telefono.replace(" ", ""), first_name=tutor.nombre
        )
        try:
            validate_password(contrasena, usuario)
        except ErrorDeDjango as error:
            raise ValidationError({"contrasena": error.messages})


# ---------------------------------------------------------------------------
# Entrenador. Todo parte de alumnos_del_entrenador(): un alumno de un grupo
# ajeno responde 404, como si no existiera.
# ---------------------------------------------------------------------------


class MisGruposView(APIView):
    """GET → los grupos del entrenador, con cuántos alumnos activos tiene cada uno."""

    permission_classes = [IsAuthenticated, SoloEntrenador]

    def get(self, request):
        conteo = {
            f"{fila['categoria']}-{fila['horario']}": fila["total"]
            for fila in alumnos_del_entrenador(request.user)
            .values("categoria", "horario")
            .annotate(total=Count("id"))
        }
        nombres = dict(GRUPOS)
        grupos = []
        for clave in grupos_de(request.user):
            categoria, horario = clave.split("-")
            grupos.append(
                {
                    "grupo": clave,
                    "nombre": nombres[clave],
                    "categoria": categoria,
                    "horario": horario,
                    "alumnos": conteo.get(clave, 0),
                }
            )
        return Response(grupos)


class AlumnosView(APIView):
    """GET ?grupo=MINI-LUN_MIE → alumnos del grupo, marcando quién ya se evaluó hoy."""

    permission_classes = [IsAuthenticated, SoloEntrenador]

    def get(self, request):
        clave = request.query_params.get("grupo", "")
        if clave not in dict(GRUPOS):
            raise ValidationError({"grupo": "Indica un grupo válido, p. ej. MINI-LUN_MIE."})
        if clave not in grupos_de(request.user):
            raise PermissionDenied("Ese grupo no te toca.")

        categoria, horario = clave.split("-")
        alumnos = alumnos_del_entrenador(request.user).filter(
            categoria=categoria, horario=horario
        ).order_by("nombre")
        evaluadas_hoy = dict(
            Evaluacion.objects.filter(
                alumno__in=alumnos, fecha=timezone.localdate()
            ).values_list("alumno_id", "id")
        )
        datos = AlumnoSerializer(
            alumnos, many=True, context={"evaluadas_hoy": evaluadas_hoy}
        ).data
        return Response(datos)


class HistorialView(APIView):
    """GET → todas las evaluaciones del alumno, de la más antigua a la más reciente.

    Lo usan los dos modos: el entrenador con los alumnos de sus grupos y el
    tutor con sus hijos. Con eso la app dibuja la gráfica de progresión.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        alumno = (
            alumnos_del_entrenador(request.user).filter(pk=pk).first()
            or alumnos_del_tutor(request.user).filter(pk=pk).first()
        )
        if alumno is None:
            raise NotFound("El alumno no existe.")
        evaluaciones = alumno.evaluaciones.select_related("capturada_por").order_by("fecha")
        return Response(
            {
                "alumno": FichaAlumnoSerializer(alumno).data,
                "evaluaciones": EvaluacionHistorialSerializer(evaluaciones, many=True).data,
            }
        )


class EvaluacionesView(APIView):
    """POST → captura. Reenviar el mismo client_uuid devuelve la que ya existe (200)."""

    permission_classes = [IsAuthenticated, SoloEntrenador]

    def post(self, request):
        datos = CapturaSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        datos = datos.validated_data
        alumno = alumno_visible(request.user, datos["alumno"])

        ya_recibida = Evaluacion.objects.filter(client_uuid=datos["client_uuid"]).first()
        if ya_recibida:
            return self._reenvio(ya_recibida, alumno)

        fecha = datos.get("fecha") or timezone.localdate()
        exigir_sin_evaluacion(alumno, fecha)
        try:
            # atomic propio: si el INSERT choca, la conexión sigue usable para revisar.
            with transaction.atomic():
                evaluacion = Evaluacion.objects.create(
                    alumno=alumno,
                    fecha=fecha,
                    pase=datos["pase"],
                    recepcion=datos["recepcion"],
                    tiro=datos["tiro"],
                    observaciones=datos["observaciones"],
                    capturada_por=request.user,
                    client_uuid=datos["client_uuid"],
                )
        except IntegrityError:
            # Otra petición ganó entre la revisión y el INSERT (p. ej. un reintento
            # del teléfono que llegó a la vez). Se responde como si hubiera llegado después.
            ya_recibida = Evaluacion.objects.filter(client_uuid=datos["client_uuid"]).first()
            if ya_recibida:
                return self._reenvio(ya_recibida, alumno)
            exigir_sin_evaluacion(alumno, fecha)
            raise
        return Response(EvaluacionSerializer(evaluacion).data, status=status.HTTP_201_CREATED)

    def _reenvio(self, evaluacion, alumno):
        if evaluacion.alumno_id != alumno.id:
            raise Conflicto("Ese client_uuid ya se usó para la evaluación de otro alumno.")
        return Response(EvaluacionSerializer(evaluacion).data, status=status.HTTP_200_OK)


class EvaluacionDetalleView(APIView):
    """PATCH → corrección de calificaciones u observaciones.

    Solo quien la capturó y solo el mismo día.
    """

    permission_classes = [IsAuthenticated, SoloEntrenador]

    def patch(self, request, pk):
        evaluacion = (
            Evaluacion.objects.select_related("alumno", "capturada_por")
            .filter(alumno__in=alumnos_del_entrenador(request.user), pk=pk)
            .first()
        )
        if evaluacion is None:
            raise NotFound("La evaluación no existe.")
        if evaluacion.capturada_por_id != request.user.id:
            raise PermissionDenied("Solo quien capturó la evaluación puede corregirla.")
        if evaluacion.fecha != timezone.localdate():
            raise PermissionDenied("Solo se puede corregir el mismo día de la evaluación.")

        datos = CorreccionSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        for campo, valor in datos.validated_data.items():
            setattr(evaluacion, campo, valor)
        evaluacion.save(update_fields=list(datos.validated_data))
        return Response(EvaluacionSerializer(evaluacion).data)


# ---------------------------------------------------------------------------
# Familia. Todo parte de alumnos_del_tutor(): el hijo de otro responde 404 en
# el histórico y no aparece en mis-hijos ni en los comunicados.
# ---------------------------------------------------------------------------


class MisHijosView(APIView):
    """GET → los hijos del tutor, primero los activos, con su última evaluación."""

    permission_classes = [IsAuthenticated, SoloTutor]

    def get(self, request):
        hijos = (
            alumnos_del_tutor(request.user)
            .prefetch_related("evaluaciones__capturada_por")
            .order_by("-activo", "nombre")
        )
        return Response(HijoSerializer(hijos, many=True).data)


class ComunicadosView(APIView):
    """GET → los avisos generales más los de las categorías de sus hijos activos."""

    permission_classes = [IsAuthenticated, SoloTutor]

    def get(self, request):
        categorias = alumnos_del_tutor(request.user).filter(activo=True).values("categoria")
        comunicados = Comunicado.objects.filter(
            Q(categoria="") | Q(categoria__in=categorias),
            # Uno con fecha futura está programado: todavía no se muestra.
            publicado__lte=timezone.now(),
        ).order_by("-publicado")
        return Response(ComunicadoSerializer(comunicados, many=True).data)


class DispositivosView(APIView):
    """POST token → registra el push token de Expo del teléfono.

    Si el token ya era de otro usuario, pasa al actual: es el mismo aparato y
    ahora inició sesión alguien más. 201 si es nuevo, 200 si ya existía.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        datos = DispositivoSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        dispositivo, nuevo = Dispositivo.objects.update_or_create(
            token=datos.validated_data["token"],
            defaults={"usuario": request.user},
        )
        return Response(
            {"token": dispositivo.token},
            status=status.HTTP_201_CREATED if nuevo else status.HTTP_200_OK,
        )


def alumno_visible(usuario, pk):
    """Alumno de los grupos del entrenador, o 404. Los hijos propios no cuentan aquí:
    un entrenador que también es papá no captura a su hijo fuera de sus grupos."""
    alumno = alumnos_del_entrenador(usuario).filter(pk=pk).first()
    if alumno is None:
        raise NotFound("El alumno no existe.")
    return alumno


def exigir_sin_evaluacion(alumno, fecha):
    """409 si el alumno ya tiene evaluación ese día: una sola por alumno y fecha."""
    existente = (
        Evaluacion.objects.select_related("capturada_por")
        .filter(alumno=alumno, fecha=fecha)
        .first()
    )
    if existente:
        quien = nombre_de(existente.capturada_por) or "un usuario dado de baja"
        raise Conflicto(
            f"{alumno.nombre} ya tiene evaluación del {fecha:%d/%m/%Y}, "
            f"capturada por {quien}."
        )
