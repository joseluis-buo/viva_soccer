"""Pruebas de la API: login con JWT, renovación, activación de tutores, los
endpoints del entrenador (grupos, alumnos, captura, corrección e histórico) y
los del modo Familia (hijos, histórico, comunicados y dispositivos)."""

import uuid
from datetime import date, timedelta
from unittest import mock

from django.contrib.auth.models import Group, User
from django.core.cache import cache
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from escuela.models import (
    Alumno,
    AsignacionEntrenador,
    Categoria,
    CodigoActivacion,
    Comunicado,
    Dispositivo,
    Evaluacion,
    Horario,
    Tutor,
)

from . import views

CLAVE = "cancha-2026"


def usuario_con_grupo(username, grupo, **extra):
    user = User.objects.create_user(username, password=CLAVE, **extra)
    user.groups.add(Group.objects.get_or_create(name=grupo)[0])
    return user


class ApiTestCase(APITestCase):
    def setUp(self):
        # El límite de peticiones vive en el caché; sin limpiarlo, una prueba
        # podría quedarse sin cupo por las anteriores.
        cache.clear()


class LoginTests(ApiTestCase):
    def login(self, username, password=CLAVE):
        return self.client.post(
            reverse("api_token"), {"username": username, "password": password}
        )

    def test_login_de_cada_rol_devuelve_tokens_rol_y_nombre(self):
        for grupo in ["administrador", "secretaria", "entrenador", "tutor"]:
            with self.subTest(grupo=grupo):
                usuario_con_grupo(grupo, grupo, first_name="Ana", last_name="López")
                respuesta = self.login(grupo)
                self.assertEqual(respuesta.status_code, 200)
                self.assertIn("access", respuesta.data)
                self.assertIn("refresh", respuesta.data)
                self.assertEqual(respuesta.data["rol"], grupo)
                self.assertEqual(respuesta.data["nombre"], "Ana López")

    def test_superusuario_entra_como_administrador(self):
        User.objects.create_superuser("jefe", password=CLAVE)
        respuesta = self.login("jefe")
        self.assertEqual(respuesta.data["rol"], "administrador")
        # Hereda secretaria y entrenador, pero no tutor.
        self.assertEqual(
            respuesta.data["roles"], ["administrador", "secretaria", "entrenador"]
        )

    def test_entrenador_que_tambien_es_papa_trae_ambos_roles(self):
        user = usuario_con_grupo("profe", "entrenador")
        user.groups.add(Group.objects.get_or_create(name="tutor")[0])
        respuesta = self.login("profe")
        self.assertEqual(respuesta.data["rol"], "entrenador")
        self.assertEqual(respuesta.data["roles"], ["entrenador", "tutor"])

    def test_contrasena_mala_responde_401_con_detail(self):
        usuario_con_grupo("profe", "entrenador")
        respuesta = self.login("profe", "otra-clave")
        self.assertEqual(respuesta.status_code, 401)
        self.assertIn("detail", respuesta.data)
        self.assertNotIn("access", respuesta.data)

    def test_usuario_sin_rol_no_recibe_tokens(self):
        User.objects.create_user("nadie", password=CLAVE)
        respuesta = self.login("nadie")
        self.assertEqual(respuesta.status_code, 403)
        self.assertNotIn("access", respuesta.data)

    def test_campos_faltantes_salen_como_detail(self):
        respuesta = self.client.post(reverse("api_token"), {"username": "profe"})
        self.assertEqual(respuesta.status_code, 400)
        self.assertEqual(list(respuesta.data), ["detail"])
        self.assertIn("password", respuesta.data["detail"])


class RenovacionTests(ApiTestCase):
    def test_renovar_rota_el_refresh_y_el_anterior_ya_no_sirve(self):
        usuario_con_grupo("profe", "entrenador")
        login = self.client.post(
            reverse("api_token"), {"username": "profe", "password": CLAVE}
        )
        viejo = login.data["refresh"]

        respuesta = self.client.post(reverse("api_token_refresh"), {"refresh": viejo})
        self.assertEqual(respuesta.status_code, 200)
        self.assertIn("access", respuesta.data)
        self.assertNotEqual(respuesta.data["refresh"], viejo)

        repetida = self.client.post(reverse("api_token_refresh"), {"refresh": viejo})
        self.assertEqual(repetida.status_code, 401)
        self.assertIn("detail", repetida.data)


class ActivacionTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        Group.objects.get_or_create(name="tutor")
        self.tutor = Tutor.objects.create(nombre="Marisol Ruiz", telefono="55 1234 5678")
        self.codigo = CodigoActivacion.objects.create(tutor=self.tutor)

    def activar(self, codigo, contrasena=CLAVE):
        return self.client.post(
            reverse("api_activar"), {"codigo": codigo, "contrasena": contrasena}
        )

    def test_activacion_crea_la_cuenta_y_devuelve_sesion_de_tutor(self):
        respuesta = self.activar(self.codigo.codigo)
        self.assertEqual(respuesta.status_code, 201)
        self.assertEqual(respuesta.data["rol"], "tutor")
        self.assertEqual(respuesta.data["nombre"], "Marisol Ruiz")
        self.assertIn("access", respuesta.data)

        self.tutor.refresh_from_db()
        self.assertEqual(self.tutor.usuario.username, "5512345678")
        self.assertTrue(self.tutor.usuario.check_password(CLAVE))
        # Ya puede iniciar sesión con su teléfono.
        login = self.client.post(
            reverse("api_token"), {"username": "5512345678", "password": CLAVE}
        )
        self.assertEqual(login.status_code, 200)

    def test_acepta_el_codigo_en_minusculas_y_con_espacios(self):
        texto = self.codigo.codigo
        respuesta = self.activar(f" {texto[:4].lower()} {texto[4:].lower()} ")
        self.assertEqual(respuesta.status_code, 201)

    def test_codigo_inexistente_responde_404(self):
        respuesta = self.activar("ZZZZZZZZ")
        self.assertEqual(respuesta.status_code, 404)
        self.assertIn("no existe", respuesta.data["detail"])

    def test_codigo_usado_responde_409(self):
        self.codigo.canjear(CLAVE)
        respuesta = self.activar(self.codigo.codigo, "otra-clave-2026")
        self.assertEqual(respuesta.status_code, 409)
        self.assertIn("ya se usó", respuesta.data["detail"])

    def test_codigo_vencido_responde_410(self):
        self.codigo.vence = timezone.now() - timedelta(minutes=1)
        self.codigo.save()
        respuesta = self.activar(self.codigo.codigo)
        self.assertEqual(respuesta.status_code, 410)
        self.assertIn("venció", respuesta.data["detail"])
        self.assertIsNone(Tutor.objects.get(pk=self.tutor.pk).usuario)

    def test_contrasena_debil_responde_400_y_no_gasta_el_codigo(self):
        respuesta = self.activar(self.codigo.codigo, "5512345678")
        self.assertEqual(respuesta.status_code, 400)
        self.assertTrue(respuesta.data["detail"].startswith("contrasena:"))
        self.codigo.refresh_from_db()
        self.assertTrue(self.codigo.vigente)

    def test_telefono_ocupado_responde_409_y_no_gasta_el_codigo(self):
        User.objects.create_user("5512345678")
        respuesta = self.activar(self.codigo.codigo)
        self.assertEqual(respuesta.status_code, 409)
        self.assertIn("teléfono", respuesta.data["detail"])
        self.codigo.refresh_from_db()
        self.assertTrue(self.codigo.vigente)


# ---------------------------------------------------------------------------
# Entrenador
# ---------------------------------------------------------------------------


def crear_alumno(nombre, categoria, horario, **extra):
    tutor = Tutor.objects.create(nombre=f"Tutor de {nombre}", telefono="55 1234 5678")
    return Alumno.objects.create(
        nombre=nombre,
        fecha_nacimiento=date(2016, 1, 1),
        categoria=categoria,
        horario=horario,
        tutor=tutor,
        **extra,
    )


def asignar(entrenador, categoria, horario):
    AsignacionEntrenador.objects.create(
        entrenador=entrenador, categoria=categoria, horario=horario
    )


class EntrenadorTestCase(ApiTestCase):
    """Dos entrenadores con grupos distintos y un alumno en cada grupo.

    profe → MENOR · Martes y Jueves (Diego)
    otro  → MAYOR · Lunes y Miércoles (Emiliano)
    """

    def setUp(self):
        super().setUp()
        self.hoy = timezone.localdate()
        self.profe = usuario_con_grupo("profe", "entrenador", first_name="Luis", last_name="Ramos")
        self.otro = usuario_con_grupo("otro", "entrenador", first_name="Karla", last_name="Soto")
        asignar(self.profe, Categoria.MENOR, Horario.MAR_JUE)
        asignar(self.otro, Categoria.MAYOR, Horario.LUN_MIE)
        self.diego = crear_alumno("Diego Salinas", Categoria.MENOR, Horario.MAR_JUE)
        self.emiliano = crear_alumno("Emiliano Cortés", Categoria.MAYOR, Horario.LUN_MIE)
        self.client.force_authenticate(self.profe)

    def evaluar(self, alumno, fecha=None, capturada_por=None, pase=7, recepcion=8, tiro=9):
        return Evaluacion.objects.create(
            alumno=alumno,
            fecha=fecha or self.hoy,
            pase=pase,
            recepcion=recepcion,
            tiro=tiro,
            capturada_por=capturada_por or self.profe,
        )

    def capturar(self, alumno, **extra):
        datos = {
            "client_uuid": str(uuid.uuid4()),
            "alumno": alumno.id,
            "pase": 7,
            "recepcion": 8,
            "tiro": 9,
        }
        datos.update(extra)
        return self.client.post(reverse("api_evaluaciones"), datos, format="json")

    def corregir(self, evaluacion, datos):
        return self.client.patch(
            reverse("api_evaluacion", args=[evaluacion.id]), datos, format="json"
        )

    def historial(self, alumno_id):
        return self.client.get(reverse("api_historial", args=[alumno_id]))


class MisGruposTests(EntrenadorTestCase):
    def test_entrenador_ve_solo_sus_grupos_con_alumnos_activos(self):
        crear_alumno("Dado de baja", Categoria.MENOR, Horario.MAR_JUE, activo=False)
        respuesta = self.client.get(reverse("api_mis_grupos"))
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(
            respuesta.data,
            [
                {
                    "grupo": "MENOR-MAR_JUE",
                    "nombre": "Menor · Martes y Jueves",
                    "categoria": "MENOR",
                    "horario": "MAR_JUE",
                    "alumnos": 1,
                }
            ],
        )

    def test_entrenador_sin_asignaciones_recibe_lista_vacia(self):
        self.client.force_authenticate(usuario_con_grupo("nuevo", "entrenador"))
        respuesta = self.client.get(reverse("api_mis_grupos"))
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.data, [])

    def test_administrador_ve_los_seis_grupos_sin_asignaciones(self):
        self.client.force_authenticate(usuario_con_grupo("jefa", "administrador"))
        respuesta = self.client.get(reverse("api_mis_grupos"))
        self.assertEqual(len(respuesta.data), 6)

    def test_tutor_y_secretaria_reciben_403(self):
        for grupo in ["tutor", "secretaria"]:
            with self.subTest(grupo=grupo):
                self.client.force_authenticate(usuario_con_grupo(grupo, grupo))
                respuesta = self.client.get(reverse("api_mis_grupos"))
                self.assertEqual(respuesta.status_code, 403)
                self.assertIn("detail", respuesta.data)

    def test_sin_sesion_responde_401(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(reverse("api_mis_grupos")).status_code, 401)


class AlumnosDelGrupoTests(EntrenadorTestCase):
    def listar(self, grupo):
        return self.client.get(reverse("api_alumnos"), {"grupo": grupo})

    def test_marca_quien_ya_tiene_evaluacion_de_hoy(self):
        mateo = crear_alumno("Mateo Fuentes", Categoria.MENOR, Horario.MAR_JUE)
        evaluacion = self.evaluar(self.diego)
        self.evaluar(mateo, fecha=self.hoy - timedelta(days=1))  # la de ayer no cuenta

        respuesta = self.listar("MENOR-MAR_JUE")

        self.assertEqual(respuesta.status_code, 200)
        por_nombre = {a["nombre"]: a for a in respuesta.data}
        self.assertTrue(por_nombre["Diego Salinas"]["evaluado_hoy"])
        self.assertEqual(por_nombre["Diego Salinas"]["evaluacion_hoy"], evaluacion.id)
        self.assertFalse(por_nombre["Mateo Fuentes"]["evaluado_hoy"])
        self.assertIsNone(por_nombre["Mateo Fuentes"]["evaluacion_hoy"])
        self.assertEqual(por_nombre["Diego Salinas"]["folio"], self.diego.folio)

    def test_no_incluye_alumnos_dados_de_baja(self):
        crear_alumno("Dado de baja", Categoria.MENOR, Horario.MAR_JUE, activo=False)
        nombres = [a["nombre"] for a in self.listar("MENOR-MAR_JUE").data]
        self.assertEqual(nombres, ["Diego Salinas"])

    def test_grupo_inexistente_o_faltante_responde_400(self):
        for grupo in ["MENOR", "OTRO-LUN_MIE", ""]:
            with self.subTest(grupo=grupo):
                respuesta = self.listar(grupo)
                self.assertEqual(respuesta.status_code, 400)
                self.assertIn("grupo", respuesta.data["detail"])


class CapturaApiTests(EntrenadorTestCase):
    def test_crea_la_evaluacion_y_el_servidor_calcula_promedio_y_folio(self):
        respuesta = self.capturar(self.diego, pase=6, recepcion=7, tiro=9, promedio=10, folio="VS-9999")
        self.assertEqual(respuesta.status_code, 201)
        evaluacion = Evaluacion.objects.get()
        self.assertEqual(respuesta.data["id"], evaluacion.id)
        self.assertEqual(respuesta.data["promedio"], 7.3)
        self.assertEqual(respuesta.data["folio"], self.diego.folio)
        self.assertEqual(respuesta.data["capturada_por"], "Luis Ramos")
        self.assertEqual(evaluacion.capturada_por, self.profe)

    def test_sin_fecha_usa_la_de_hoy(self):
        self.capturar(self.diego)
        self.assertEqual(Evaluacion.objects.get().fecha, self.hoy)

    def test_fecha_de_la_cancha_y_momento_de_recepcion_se_guardan_por_separado(self):
        hace_tres_dias = self.hoy - timedelta(days=3)
        respuesta = self.capturar(self.diego, fecha=hace_tres_dias.isoformat())
        self.assertEqual(respuesta.status_code, 201)
        evaluacion = Evaluacion.objects.get()
        self.assertEqual(evaluacion.fecha, hace_tres_dias)
        self.assertEqual(timezone.localtime(evaluacion.creada).date(), self.hoy)

    def test_acepta_hasta_siete_dias_atras(self):
        respuesta = self.capturar(self.diego, fecha=(self.hoy - timedelta(days=7)).isoformat())
        self.assertEqual(respuesta.status_code, 201)

    def test_rechaza_fecha_futura_o_de_mas_de_siete_dias(self):
        for fecha in [self.hoy + timedelta(days=1), self.hoy - timedelta(days=8)]:
            with self.subTest(fecha=fecha):
                respuesta = self.capturar(self.diego, fecha=fecha.isoformat())
                self.assertEqual(respuesta.status_code, 400)
                self.assertIn("fecha", respuesta.data["detail"])
        self.assertFalse(Evaluacion.objects.exists())

    def test_rechaza_calificaciones_fuera_de_rango_o_sin_client_uuid(self):
        casos = [{"pase": 0}, {"tiro": 11}, {"recepcion": "x"}, {"client_uuid": ""}]
        for extra in casos:
            with self.subTest(extra=extra):
                self.assertEqual(self.capturar(self.diego, **extra).status_code, 400)
        self.assertFalse(Evaluacion.objects.exists())

    def test_reenviar_el_mismo_client_uuid_devuelve_la_existente_con_200(self):
        client_uuid = str(uuid.uuid4())
        primera = self.capturar(self.diego, client_uuid=client_uuid)
        # El teléfono no recibió la respuesta y reintenta al recuperar señal.
        segunda = self.capturar(self.diego, client_uuid=client_uuid, pase=1)
        self.assertEqual(primera.status_code, 201)
        self.assertEqual(segunda.status_code, 200)
        self.assertEqual(segunda.data["id"], primera.data["id"])
        self.assertEqual(segunda.data["pase"], 7)  # no se sobrescribe
        self.assertEqual(Evaluacion.objects.count(), 1)

    def test_otro_client_uuid_para_el_mismo_dia_responde_409_con_quien_y_cuando(self):
        asignar(self.otro, Categoria.MENOR, Horario.MAR_JUE)
        self.evaluar(self.diego, capturada_por=self.otro)
        respuesta = self.capturar(self.diego)
        self.assertEqual(respuesta.status_code, 409)
        detalle = respuesta.data["detail"]
        self.assertIn("Diego Salinas", detalle)
        self.assertIn(f"{self.hoy:%d/%m/%Y}", detalle)
        self.assertIn("Karla Soto", detalle)
        self.assertEqual(Evaluacion.objects.count(), 1)

    def test_evaluacion_capturada_en_la_web_tambien_cuenta_para_el_409(self):
        Evaluacion.objects.create(alumno=self.diego, fecha=self.hoy, pase=5, recepcion=5, tiro=5)
        respuesta = self.capturar(self.diego)
        self.assertEqual(respuesta.status_code, 409)

    def test_si_otra_peticion_gana_la_carrera_responde_409(self):
        # Simula que la otra evaluación se guardó entre la revisión y el INSERT:
        # la primera revisión no la ve, el INSERT choca y la segunda sí la ve.
        self.evaluar(self.diego, capturada_por=self.otro)
        revision_real = views.exigir_sin_evaluacion
        llamadas = []

        def primera_no_ve_nada(alumno, fecha):
            llamadas.append(fecha)
            if len(llamadas) > 1:
                revision_real(alumno, fecha)

        with mock.patch.object(views, "exigir_sin_evaluacion", primera_no_ve_nada):
            respuesta = self.capturar(self.diego)
        self.assertEqual(respuesta.status_code, 409)
        self.assertEqual(len(llamadas), 2)
        self.assertEqual(Evaluacion.objects.count(), 1)

    def test_client_uuid_de_otro_alumno_responde_409(self):
        mateo = crear_alumno("Mateo Fuentes", Categoria.MENOR, Horario.MAR_JUE)
        client_uuid = str(uuid.uuid4())
        self.capturar(self.diego, client_uuid=client_uuid)
        respuesta = self.capturar(mateo, client_uuid=client_uuid)
        self.assertEqual(respuesta.status_code, 409)
        self.assertFalse(mateo.evaluaciones.exists())

    def test_alumno_dado_de_baja_responde_404(self):
        baja = crear_alumno("Dado de baja", Categoria.MENOR, Horario.MAR_JUE, activo=False)
        self.assertEqual(self.capturar(baja).status_code, 404)

    def test_administrador_captura_en_cualquier_grupo(self):
        self.client.force_authenticate(usuario_con_grupo("jefa", "administrador"))
        self.assertEqual(self.capturar(self.emiliano).status_code, 201)

    def test_tutor_no_puede_capturar(self):
        self.client.force_authenticate(usuario_con_grupo("papa", "tutor"))
        self.assertEqual(self.capturar(self.diego).status_code, 403)
        self.assertFalse(Evaluacion.objects.exists())


class CorreccionApiTests(EntrenadorTestCase):
    def test_corrige_y_el_modelo_recalcula_el_promedio(self):
        evaluacion = self.evaluar(self.diego, pase=4, recepcion=5, tiro=6)
        respuesta = self.corregir(evaluacion, {"pase": 10, "promedio": 1})
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.data["pase"], 10)
        self.assertEqual(respuesta.data["promedio"], 7.0)
        evaluacion.refresh_from_db()
        self.assertEqual((evaluacion.pase, evaluacion.recepcion, evaluacion.tiro), (10, 5, 6))

    def test_no_cambia_alumno_fecha_ni_momento_de_recepcion(self):
        evaluacion = self.evaluar(self.diego)
        creada = evaluacion.creada
        mateo = crear_alumno("Mateo Fuentes", Categoria.MENOR, Horario.MAR_JUE)
        ayer = self.hoy - timedelta(days=1)
        self.corregir(evaluacion, {"tiro": 3, "fecha": ayer.isoformat(), "alumno": mateo.id})
        evaluacion.refresh_from_db()
        self.assertEqual(evaluacion.tiro, 3)
        self.assertEqual(evaluacion.fecha, self.hoy)
        self.assertEqual(evaluacion.alumno, self.diego)
        self.assertEqual(evaluacion.creada, creada)

    def test_otro_entrenador_del_mismo_grupo_no_puede_corregir(self):
        asignar(self.otro, Categoria.MENOR, Horario.MAR_JUE)
        evaluacion = self.evaluar(self.diego, capturada_por=self.otro)
        respuesta = self.corregir(evaluacion, {"pase": 1})
        self.assertEqual(respuesta.status_code, 403)
        self.assertIn("capturó", respuesta.data["detail"])
        evaluacion.refresh_from_db()
        self.assertEqual(evaluacion.pase, 7)

    def test_evaluacion_de_otro_dia_no_se_puede_corregir(self):
        evaluacion = self.evaluar(self.diego, fecha=self.hoy - timedelta(days=1))
        respuesta = self.corregir(evaluacion, {"pase": 1})
        self.assertEqual(respuesta.status_code, 403)
        self.assertIn("mismo día", respuesta.data["detail"])
        evaluacion.refresh_from_db()
        self.assertEqual(evaluacion.pase, 7)

    def test_rechaza_calificacion_fuera_de_rango(self):
        evaluacion = self.evaluar(self.diego)
        self.assertEqual(self.corregir(evaluacion, {"pase": 11}).status_code, 400)

    def test_evaluacion_inexistente_responde_404(self):
        respuesta = self.client.patch(reverse("api_evaluacion", args=[999]), {"pase": 5})
        self.assertEqual(respuesta.status_code, 404)


class HistorialApiTests(EntrenadorTestCase):
    def test_devuelve_el_historico_completo_en_orden_cronologico(self):
        self.evaluar(self.diego, fecha=date(2026, 9, 8), pase=8, recepcion=8, tiro=8)
        self.evaluar(self.diego, fecha=date(2026, 4, 10), pase=5, recepcion=6, tiro=7)
        respuesta = self.historial(self.diego.id)
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.data["alumno"]["folio"], self.diego.folio)
        fechas = [e["fecha"] for e in respuesta.data["evaluaciones"]]
        self.assertEqual(fechas, ["2026-04-10", "2026-09-08"])
        self.assertEqual([e["promedio"] for e in respuesta.data["evaluaciones"]], [6.0, 8.0])

    def test_incluye_evaluaciones_de_cuando_estaba_en_otro_grupo(self):
        self.evaluar(self.emiliano, fecha=date(2026, 4, 10), capturada_por=self.otro)
        self.emiliano.categoria, self.emiliano.horario = Categoria.MENOR, Horario.MAR_JUE
        self.emiliano.save()
        respuesta = self.historial(self.emiliano.id)
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(len(respuesta.data["evaluaciones"]), 1)

    def test_alumno_inexistente_responde_404(self):
        self.assertEqual(self.historial(999).status_code, 404)


class AislamientoEntreGruposTests(EntrenadorTestCase):
    """Un entrenador no puede leer ni escribir nada de un grupo que no le toca.

    profe (MENOR · Martes y Jueves) intenta todo contra Emiliano, que está en
    MAYOR · Lunes y Miércoles, el grupo de otro.
    """

    def setUp(self):
        super().setUp()
        self.ajena = self.evaluar(self.emiliano, capturada_por=self.otro)

    def test_no_ve_el_grupo_ajeno_en_mis_grupos(self):
        grupos = [g["grupo"] for g in self.client.get(reverse("api_mis_grupos")).data]
        self.assertNotIn("MAYOR-LUN_MIE", grupos)

    def test_no_lista_los_alumnos_del_grupo_ajeno(self):
        respuesta = self.client.get(reverse("api_alumnos"), {"grupo": "MAYOR-LUN_MIE"})
        self.assertEqual(respuesta.status_code, 403)
        self.assertNotIn("Emiliano", str(respuesta.data))

    def test_no_lee_el_historico_de_un_alumno_ajeno(self):
        respuesta = self.historial(self.emiliano.id)
        self.assertEqual(respuesta.status_code, 404)
        self.assertNotIn("Emiliano", str(respuesta.data))

    def test_no_captura_a_un_alumno_ajeno(self):
        respuesta = self.capturar(self.emiliano, fecha=(self.hoy - timedelta(days=1)).isoformat())
        self.assertEqual(respuesta.status_code, 404)
        self.assertEqual(self.emiliano.evaluaciones.count(), 1)

    def test_el_409_no_revela_datos_de_un_alumno_ajeno(self):
        # Emiliano ya tiene evaluación hoy; aun así el ajeno recibe 404, no 409.
        respuesta = self.capturar(self.emiliano)
        self.assertEqual(respuesta.status_code, 404)
        self.assertNotIn("Karla", str(respuesta.data))

    def test_reenviar_el_client_uuid_de_una_evaluacion_ajena_no_la_devuelve(self):
        self.ajena.client_uuid = uuid.uuid4()
        self.ajena.save()
        respuesta = self.capturar(self.emiliano, client_uuid=str(self.ajena.client_uuid))
        self.assertEqual(respuesta.status_code, 404)
        respuesta = self.capturar(self.diego, client_uuid=str(self.ajena.client_uuid))
        self.assertEqual(respuesta.status_code, 409)
        self.assertNotIn("Emiliano", str(respuesta.data))
        self.assertFalse(self.diego.evaluaciones.exists())

    def test_no_corrige_una_evaluacion_ajena(self):
        respuesta = self.corregir(self.ajena, {"pase": 1})
        self.assertEqual(respuesta.status_code, 404)
        self.ajena.refresh_from_db()
        self.assertEqual(self.ajena.pase, 7)

    def test_pierde_el_acceso_si_le_quitan_el_grupo(self):
        AsignacionEntrenador.objects.filter(entrenador=self.profe).delete()
        self.assertEqual(self.historial(self.diego.id).status_code, 404)
        respuesta = self.client.get(reverse("api_alumnos"), {"grupo": "MENOR-MAR_JUE"})
        self.assertEqual(respuesta.status_code, 403)

    def test_pierde_el_acceso_si_el_alumno_cambia_a_un_grupo_ajeno(self):
        self.diego.categoria = Categoria.MAYOR
        self.diego.save()
        self.assertEqual(self.historial(self.diego.id).status_code, 404)


class ObservacionesApiTests(EntrenadorTestCase):
    def test_se_capturan_con_la_evaluacion(self):
        respuesta = self.capturar(self.diego, observaciones="Buen control orientado.")
        self.assertEqual(respuesta.status_code, 201)
        self.assertEqual(respuesta.data["observaciones"], "Buen control orientado.")
        self.assertEqual(Evaluacion.objects.get().observaciones, "Buen control orientado.")

    def test_son_opcionales(self):
        respuesta = self.capturar(self.diego)
        self.assertEqual(respuesta.status_code, 201)
        self.assertEqual(Evaluacion.objects.get().observaciones, "")

    def test_demasiado_largas_responden_400_con_detail(self):
        respuesta = self.capturar(self.diego, observaciones="x" * 501)
        self.assertEqual(respuesta.status_code, 400)
        self.assertIn("observaciones", respuesta.data["detail"])
        self.assertFalse(Evaluacion.objects.exists())

    def test_se_corrigen_el_mismo_dia_sin_tocar_las_calificaciones(self):
        evaluacion = self.evaluar(self.diego)
        respuesta = self.corregir(evaluacion, {"observaciones": "Llegó tarde."})
        self.assertEqual(respuesta.status_code, 200)
        evaluacion.refresh_from_db()
        self.assertEqual(evaluacion.observaciones, "Llegó tarde.")
        self.assertEqual((evaluacion.pase, evaluacion.recepcion, evaluacion.tiro), (7, 8, 9))


class HistorialDelEntrenadorTests(EntrenadorTestCase):
    def test_no_trae_datos_de_sincronizacion_y_si_quien_capturo(self):
        self.evaluar(self.diego, fecha=date(2026, 4, 10))
        evaluacion = self.historial(self.diego.id).data["evaluaciones"][0]
        self.assertNotIn("client_uuid", evaluacion)
        self.assertNotIn("creada", evaluacion)
        self.assertEqual(evaluacion["capturada_por"], "Luis Ramos")
        self.assertEqual(evaluacion["temporada"], 2026)

    def test_un_entrenador_que_es_papa_no_captura_a_su_hijo_fuera_de_sus_grupos(self):
        # Emiliano es su hijo, pero está en MAYOR, que no le toca.
        self.profe.groups.add(Group.objects.get_or_create(name="tutor")[0])
        Tutor.objects.filter(pk=self.emiliano.tutor_id).update(usuario=self.profe)
        self.assertEqual(self.historial(self.emiliano.id).status_code, 200)
        respuesta = self.capturar(self.emiliano)
        self.assertEqual(respuesta.status_code, 404)
        self.assertFalse(self.emiliano.evaluaciones.exists())


class FamiliaTestCase(ApiTestCase):
    """Dos familias con hijos en categorías distintas.

    papá Hugo   → Renata (MINI) y Mateo (MENOR, dado de baja)
    mamá Ana    → Emiliano (MAYOR)
    """

    def setUp(self):
        super().setUp()
        self.papa = self.crear_familia("5588712210", "Hugo Ocampo", "55 8871 2210")
        self.mama = self.crear_familia("5544029931", "Ana Nava", "55 4402 9931")
        self.renata = self.crear_hijo("Renata Ocampo", Categoria.MINI, self.papa)
        self.mateo = self.crear_hijo("Mateo Ocampo", Categoria.MENOR, self.papa, activo=False)
        self.emiliano = self.crear_hijo("Emiliano Cortés", Categoria.MAYOR, self.mama)
        self.profe = usuario_con_grupo("profe", "entrenador", first_name="Luis", last_name="Ramos")
        self.client.force_authenticate(self.papa)

    def crear_familia(self, username, nombre, telefono):
        usuario = usuario_con_grupo(username, "tutor")
        Tutor.objects.create(nombre=nombre, telefono=telefono, usuario=usuario)
        return usuario

    def crear_hijo(self, nombre, categoria, usuario, **extra):
        return Alumno.objects.create(
            nombre=nombre,
            fecha_nacimiento=date(2016, 1, 1),
            categoria=categoria,
            horario=Horario.LUN_MIE,
            tutor=usuario.tutor,
            **extra,
        )

    def evaluar(self, alumno, fecha, pase=7, recepcion=8, tiro=9):
        return Evaluacion.objects.create(
            alumno=alumno,
            fecha=fecha,
            pase=pase,
            recepcion=recepcion,
            tiro=tiro,
            capturada_por=self.profe,
        )

    def comunicado(self, titulo, categoria="", **extra):
        return Comunicado.objects.create(
            titulo=titulo, cuerpo="…", categoria=categoria, **extra
        )

    def mis_hijos(self):
        return self.client.get(reverse("api_mis_hijos"))

    def historial(self, alumno):
        return self.client.get(reverse("api_historial", args=[alumno.id]))

    def titulos_de_comunicados(self):
        respuesta = self.client.get(reverse("api_comunicados"))
        self.assertEqual(respuesta.status_code, 200)
        return [c["titulo"] for c in respuesta.data]


class MisHijosTests(FamiliaTestCase):
    def test_lista_sus_hijos_activos_primero_con_categoria_y_horario(self):
        respuesta = self.mis_hijos()
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual([h["nombre"] for h in respuesta.data], ["Renata Ocampo", "Mateo Ocampo"])
        renata = respuesta.data[0]
        self.assertEqual(renata["folio"], self.renata.folio)
        self.assertEqual(renata["categoria"], "MINI")
        self.assertEqual(renata["categoria_nombre"], "Mini")
        self.assertEqual(renata["horario"], "LUN_MIE")
        self.assertEqual(renata["horario_nombre"], "Lunes y Miércoles")

    def test_marca_al_hijo_dado_de_baja(self):
        activos = {h["nombre"]: h["activo"] for h in self.mis_hijos().data}
        self.assertEqual(activos, {"Renata Ocampo": True, "Mateo Ocampo": False})

    def test_trae_la_ultima_evaluacion_con_su_promedio(self):
        self.evaluar(self.renata, date(2026, 9, 8), pase=8, recepcion=9, tiro=10)
        self.evaluar(self.renata, date(2026, 4, 10), pase=5, recepcion=5, tiro=5)
        renata = self.mis_hijos().data[0]
        ultima = renata["ultima_evaluacion"]
        self.assertEqual(ultima["fecha"], "2026-09-08")
        self.assertEqual(ultima["promedio"], 9.0)
        self.assertEqual(ultima["capturada_por"], "Luis Ramos")

    def test_sin_evaluaciones_la_ultima_es_null(self):
        self.assertIsNone(self.mis_hijos().data[0]["ultima_evaluacion"])

    def test_tutor_sin_ficha_de_tutor_no_tiene_hijos(self):
        # Está en el grupo tutor pero nadie le ligó un Tutor del padrón.
        self.client.force_authenticate(usuario_con_grupo("suelto", "tutor"))
        respuesta = self.mis_hijos()
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.data, [])

    def test_entrenador_y_administrador_reciben_403(self):
        for usuario in [self.profe, User.objects.create_superuser("jefe", password=CLAVE)]:
            with self.subTest(usuario=usuario.username):
                self.client.force_authenticate(usuario)
                self.assertEqual(self.mis_hijos().status_code, 403)

    def test_sin_sesion_responde_401(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.mis_hijos().status_code, 401)


class HistorialDelTutorTests(FamiliaTestCase):
    def test_ve_el_historico_de_su_hijo_con_lo_necesario_para_la_grafica(self):
        self.evaluar(self.renata, date(2026, 9, 8))
        self.evaluar(self.renata, date(2025, 10, 1))
        respuesta = self.historial(self.renata)
        self.assertEqual(respuesta.status_code, 200)
        evaluaciones = respuesta.data["evaluaciones"]
        self.assertEqual([e["fecha"] for e in evaluaciones], ["2025-10-01", "2026-09-08"])
        self.assertEqual([e["temporada"] for e in evaluaciones], [2025, 2026])
        self.assertEqual(
            set(evaluaciones[0]),
            {"id", "fecha", "temporada", "pase", "recepcion", "tiro", "promedio",
             "observaciones", "capturada_por"},
        )

    def test_ve_las_observaciones_con_el_nombre_de_quien_las_escribio(self):
        evaluacion = self.evaluar(self.renata, date(2026, 9, 8))
        evaluacion.observaciones = "Ya tira a portería sin miedo."
        evaluacion.save()
        ultima = self.historial(self.renata).data["evaluaciones"][-1]
        self.assertEqual(ultima["observaciones"], "Ya tira a portería sin miedo.")
        self.assertEqual(ultima["capturada_por"], "Luis Ramos")
        hijo = self.mis_hijos().data[0]
        self.assertEqual(hijo["ultima_evaluacion"]["observaciones"], "Ya tira a portería sin miedo.")

    def test_ve_el_historico_completo_del_hijo_dado_de_baja(self):
        self.evaluar(self.mateo, date(2026, 4, 10))
        respuesta = self.historial(self.mateo)
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(len(respuesta.data["evaluaciones"]), 1)


class AislamientoEntreFamiliasTests(FamiliaTestCase):
    """Un tutor no puede ver nada de un alumno que no es su hijo.

    El papá de Renata y Mateo intenta todo contra Emiliano, hijo de otra mamá.
    """

    def setUp(self):
        super().setUp()
        self.evaluar(self.emiliano, date(2026, 9, 8))

    def test_no_aparece_en_mis_hijos(self):
        respuesta = self.mis_hijos()
        self.assertNotIn(self.emiliano.id, [h["id"] for h in respuesta.data])
        self.assertNotIn("Emiliano", str(respuesta.data))

    def test_su_historico_responde_404_sin_revelar_nada(self):
        respuesta = self.historial(self.emiliano)
        self.assertEqual(respuesta.status_code, 404)
        self.assertNotIn("Emiliano", str(respuesta.data))

    def test_no_recibe_comunicados_de_la_categoria_de_otro(self):
        self.comunicado("Torneo de la Mayor", Categoria.MAYOR)
        self.assertNotIn("Torneo de la Mayor", self.titulos_de_comunicados())

    def test_pierde_el_acceso_si_el_alumno_cambia_de_tutor(self):
        self.renata.tutor = self.mama.tutor
        self.renata.save()
        self.assertEqual(self.historial(self.renata).status_code, 404)
        self.assertEqual([h["nombre"] for h in self.mis_hijos().data], ["Mateo Ocampo"])

    def test_sin_el_grupo_tutor_no_ve_a_sus_hijos(self):
        self.papa.groups.clear()
        self.assertEqual(self.historial(self.renata).status_code, 404)
        self.assertEqual(self.mis_hijos().status_code, 403)

    def test_un_tutor_no_puede_capturar_ni_corregir(self):
        evaluacion = self.evaluar(self.renata, timezone.localdate())
        respuesta = self.client.post(
            reverse("api_evaluaciones"),
            {"client_uuid": str(uuid.uuid4()), "alumno": self.renata.id,
             "pase": 10, "recepcion": 10, "tiro": 10},
            format="json",
        )
        self.assertEqual(respuesta.status_code, 403)
        respuesta = self.client.patch(
            reverse("api_evaluacion", args=[evaluacion.id]), {"pase": 10}, format="json"
        )
        self.assertEqual(respuesta.status_code, 403)
        evaluacion.refresh_from_db()
        self.assertEqual(evaluacion.pase, 7)


class ComunicadosTests(FamiliaTestCase):
    def test_recibe_los_generales_y_los_de_las_categorias_de_sus_hijos(self):
        self.comunicado("Suspensión por lluvia")
        self.comunicado("Uniformes de la Mini", Categoria.MINI)
        self.assertEqual(
            sorted(self.titulos_de_comunicados()),
            ["Suspensión por lluvia", "Uniformes de la Mini"],
        )

    def test_no_recibe_los_de_la_categoria_de_un_hijo_dado_de_baja(self):
        # Mateo está en MENOR pero ya se dio de baja.
        self.comunicado("Partido de la Menor", Categoria.MENOR)
        self.assertEqual(self.titulos_de_comunicados(), [])

    def test_del_mas_reciente_al_mas_antiguo(self):
        ahora = timezone.now()
        self.comunicado("Viejo", publicado=ahora - timedelta(days=3))
        self.comunicado("Nuevo", publicado=ahora - timedelta(hours=1))
        self.assertEqual(self.titulos_de_comunicados(), ["Nuevo", "Viejo"])

    def test_uno_programado_a_futuro_todavia_no_aparece(self):
        self.comunicado("Mañana", publicado=timezone.now() + timedelta(days=1))
        self.assertEqual(self.titulos_de_comunicados(), [])

    def test_entrenador_recibe_403(self):
        self.client.force_authenticate(self.profe)
        self.assertEqual(self.client.get(reverse("api_comunicados")).status_code, 403)


class DispositivosTests(FamiliaTestCase):
    TOKEN = "ExponentPushToken[xxxxxxxxxxxxxxxxxxxxxx]"

    def registrar(self, token=TOKEN):
        return self.client.post(reverse("api_dispositivos"), {"token": token}, format="json")

    def test_registra_el_token_del_usuario(self):
        respuesta = self.registrar()
        self.assertEqual(respuesta.status_code, 201)
        self.assertEqual(Dispositivo.objects.get(token=self.TOKEN).usuario, self.papa)

    def test_registrarlo_otra_vez_no_lo_duplica(self):
        self.registrar()
        respuesta = self.registrar()
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(Dispositivo.objects.count(), 1)

    def test_si_otro_usuario_inicia_sesion_en_el_celular_el_token_pasa_a_el(self):
        self.registrar()
        self.client.force_authenticate(self.mama)
        respuesta = self.registrar()
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(Dispositivo.objects.count(), 1)
        self.assertEqual(Dispositivo.objects.get().usuario, self.mama)

    def test_el_entrenador_tambien_registra_su_celular(self):
        self.client.force_authenticate(self.profe)
        self.assertEqual(self.registrar().status_code, 201)

    def test_token_que_no_es_de_expo_responde_400_con_detail(self):
        respuesta = self.registrar("cualquier-cosa")
        self.assertEqual(respuesta.status_code, 400)
        self.assertIn("token", respuesta.data["detail"])
        self.assertFalse(Dispositivo.objects.exists())

    def test_sin_sesion_responde_401(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.registrar().status_code, 401)
