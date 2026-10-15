"""Pruebas de las reglas de dominio y de los permisos por rol.

Cubren lo que una entrega de avance necesita demostrar:
- cálculo de promedio y folio del alumno,
- restricción de una evaluación por alumno y fecha,
- validación del teléfono,
- separación de accesos entre administrador, secretaria y entrenador,
- guardado de la pantalla de captura,
- funciones de secretaria: tutores, baja, corrección de evaluaciones y boletas.
"""

from datetime import date

from django.contrib.auth.models import Group, User
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from .models import Alumno, Categoria, Evaluacion, Horario, Tutor
from .roles import es_administrador, es_entrenador, es_secretaria


def crear_tutor(**extra):
    datos = {"nombre": "Marisol Ruiz", "telefono": "55 1234 5678"}
    datos.update(extra)
    return Tutor.objects.create(**datos)


def crear_alumno(**extra):
    datos = {
        "nombre": "Diego Salinas Ruiz",
        "fecha_nacimiento": date(2017, 3, 14),
        "categoria": Categoria.MENOR,
        "horario": Horario.MAR_JUE,
    }
    datos.update(extra)
    if "tutor" not in datos:
        datos["tutor"] = crear_tutor()
    return Alumno.objects.create(**datos)


def usuario_con_grupo(username, grupo):
    user = User.objects.create_user(username, password="x")
    user.groups.add(Group.objects.get_or_create(name=grupo)[0])
    return user


class AlumnoModeloTests(TestCase):
    def test_folio_deriva_del_id_con_ceros(self):
        alumno = crear_alumno()
        self.assertEqual(alumno.folio, f"VS-{alumno.pk:04d}")

    def test_folio_sin_id_es_marcador(self):
        self.assertEqual(Alumno().folio, "VS-----")

    def test_telefono_con_formato_incorrecto_no_valida(self):
        tutor = Tutor(nombre="Marisol Ruiz", telefono="5512345678")
        with self.assertRaises(ValidationError):
            tutor.full_clean()

    def test_orden_por_nombre(self):
        crear_alumno(nombre="Zaira Núñez")
        crear_alumno(nombre="Ana Beltrán")
        self.assertEqual(
            list(Alumno.objects.values_list("nombre", flat=True)),
            ["Ana Beltrán", "Zaira Núñez"],
        )


class EvaluacionModeloTests(TestCase):
    def setUp(self):
        self.alumno = crear_alumno()

    def test_promedio_redondea_a_un_decimal(self):
        ev = Evaluacion(alumno=self.alumno, fecha=date(2026, 4, 10), pase=7, recepcion=8, tiro=8)
        self.assertEqual(ev.promedio, 7.7)

    def test_una_evaluacion_por_alumno_y_fecha(self):
        Evaluacion.objects.create(
            alumno=self.alumno, fecha=date(2026, 4, 10), pase=6, recepcion=6, tiro=6
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Evaluacion.objects.create(
                    alumno=self.alumno, fecha=date(2026, 4, 10), pase=7, recepcion=7, tiro=7
                )


class RolesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        for nombre in ("administrador", "entrenador"):
            Group.objects.get_or_create(name=nombre)
        cls.admin = User.objects.create_user("ada", password="x")
        cls.admin.groups.add(Group.objects.get(name="administrador"))
        cls.entrenador = User.objects.create_user("eze", password="x")
        cls.entrenador.groups.add(Group.objects.get(name="entrenador"))
        cls.suelto = User.objects.create_user("sam", password="x")

    def test_administrador_es_tambien_entrenador(self):
        self.assertTrue(es_administrador(self.admin))
        self.assertTrue(es_entrenador(self.admin))

    def test_entrenador_no_es_administrador(self):
        self.assertTrue(es_entrenador(self.entrenador))
        self.assertFalse(es_administrador(self.entrenador))

    def test_usuario_sin_grupo_no_tiene_rol(self):
        self.assertFalse(es_administrador(self.suelto))
        self.assertFalse(es_secretaria(self.suelto))
        self.assertFalse(es_entrenador(self.suelto))

    def test_administrador_es_tambien_secretaria(self):
        self.assertTrue(es_secretaria(self.admin))

    def test_secretaria_no_es_administrador_ni_entrenador(self):
        secretaria = usuario_con_grupo("sec", "secretaria")
        self.assertTrue(es_secretaria(secretaria))
        self.assertFalse(es_administrador(secretaria))
        self.assertFalse(es_entrenador(secretaria))


class AccesoPorRolTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        for nombre in ("administrador", "entrenador"):
            Group.objects.get_or_create(name=nombre)
        cls.admin = User.objects.create_user("ada", password="x")
        cls.admin.groups.add(Group.objects.get(name="administrador"))
        cls.entrenador = User.objects.create_user("eze", password="x")
        cls.entrenador.groups.add(Group.objects.get(name="entrenador"))

    def test_entrenador_no_entra_al_panel(self):
        self.client.force_login(self.entrenador)
        # Va a su pantalla de inicio, no al login (que lo regresaría aquí en ciclo).
        respuesta = self.client.get(reverse("dashboard"), follow=True)
        self.assertEqual(respuesta.redirect_chain[-1][0], reverse("captura"))

    def test_anonimo_en_pantalla_protegida_va_a_login(self):
        respuesta = self.client.get(reverse("padron"))
        self.assertIn(reverse("login"), respuesta["Location"])

    def test_usuario_sin_rol_recibe_403(self):
        self.client.force_login(User.objects.create_user("sam", password="x"))
        self.assertEqual(self.client.get(reverse("padron")).status_code, 403)

    def test_entrenador_no_entra_al_padron(self):
        self.client.force_login(self.entrenador)
        self.assertEqual(self.client.get(reverse("padron")).status_code, 302)

    def test_administrador_entra_a_panel_padron_y_captura(self):
        self.client.force_login(self.admin)
        for nombre in ("dashboard", "padron", "captura"):
            self.assertEqual(self.client.get(reverse(nombre)).status_code, 200, nombre)

    def test_secretaria_entra_a_padron_y_tutores_pero_no_al_panel_ni_captura(self):
        self.client.force_login(usuario_con_grupo("sec", "secretaria"))
        for nombre in ("padron", "tutores"):
            self.assertEqual(self.client.get(reverse(nombre)).status_code, 200, nombre)
        for nombre in ("dashboard", "captura"):
            respuesta = self.client.get(reverse(nombre), follow=True)
            self.assertEqual(respuesta.redirect_chain[-1][0], reverse("padron"), nombre)

    def test_entrenador_no_entra_a_tutores(self):
        self.client.force_login(self.entrenador)
        self.assertEqual(self.client.get(reverse("tutores")).status_code, 302)

    def test_raiz_manda_a_cada_rol_a_su_pantalla(self):
        self.client.force_login(usuario_con_grupo("sec", "secretaria"))
        self.assertIn(reverse("padron"), self.client.get(reverse("raiz"))["Location"])
        self.client.force_login(self.admin)
        self.assertIn(reverse("dashboard"), self.client.get(reverse("raiz"))["Location"])
        self.client.force_login(self.entrenador)
        self.assertIn(reverse("captura"), self.client.get(reverse("raiz"))["Location"])

    def test_anonimo_va_a_login(self):
        self.assertIn(reverse("login"), self.client.get(reverse("raiz"))["Location"])


class CapturaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        Group.objects.get_or_create(name="entrenador")
        cls.entrenador = User.objects.create_user("eze", password="x")
        cls.entrenador.groups.add(Group.objects.get(name="entrenador"))
        cls.alumno = crear_alumno(categoria=Categoria.MINI, horario=Horario.LUN_MIE)

    def setUp(self):
        self.client.force_login(self.entrenador)

    def test_guarda_evaluacion_y_registra_quien_captura(self):
        url = reverse("captura") + "?grupo=MINI-LUN_MIE&fecha=2026-09-08"
        self.client.post(
            url,
            {
                f"pase_{self.alumno.id}": "7",
                f"recepcion_{self.alumno.id}": "8",
                f"tiro_{self.alumno.id}": "6",
            },
        )
        ev = Evaluacion.objects.get(alumno=self.alumno, fecha=date(2026, 9, 8))
        self.assertEqual((ev.pase, ev.recepcion, ev.tiro), (7, 8, 6))
        self.assertEqual(ev.capturada_por, self.entrenador)

    def test_reenviar_actualiza_en_lugar_de_duplicar(self):
        url = reverse("captura") + "?grupo=MINI-LUN_MIE&fecha=2026-09-08"
        base = {
            f"pase_{self.alumno.id}": "5",
            f"recepcion_{self.alumno.id}": "5",
            f"tiro_{self.alumno.id}": "5",
        }
        self.client.post(url, base)
        self.client.post(url, {**base, f"pase_{self.alumno.id}": "9"})
        self.assertEqual(Evaluacion.objects.filter(alumno=self.alumno).count(), 1)
        self.assertEqual(Evaluacion.objects.get(alumno=self.alumno).pase, 9)

    def test_fila_incompleta_o_fuera_de_rango_se_ignora(self):
        url = reverse("captura") + "?grupo=MINI-LUN_MIE&fecha=2026-09-08"
        self.client.post(
            url,
            {
                f"pase_{self.alumno.id}": "7",
                f"recepcion_{self.alumno.id}": "",  # incompleta
                f"tiro_{self.alumno.id}": "6",
            },
        )
        self.client.post(
            url,
            {
                f"pase_{self.alumno.id}": "11",  # fuera de rango
                f"recepcion_{self.alumno.id}": "5",
                f"tiro_{self.alumno.id}": "5",
            },
        )
        self.assertFalse(Evaluacion.objects.filter(alumno=self.alumno).exists())


class SecretariaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.secretaria = usuario_con_grupo("sec", "secretaria")
        cls.tutor = crear_tutor()
        cls.alumno = crear_alumno(tutor=cls.tutor)

    def setUp(self):
        self.client.force_login(self.secretaria)

    def _alta(self, **extra):
        datos = {
            "nombre": "Lucía Ruiz",
            "categoria": Categoria.MINI,
            "horario": Horario.LUN_MIE,
            "fecha_nacimiento": "2020-01-15",
        }
        datos.update(extra)
        return self.client.post(reverse("alumno_nuevo"), datos, HTTP_HX_REQUEST="true")

    def test_alta_de_alumno_con_tutor_existente(self):
        respuesta = self._alta(tutor=self.tutor.pk)
        self.assertEqual(respuesta.status_code, 204)
        self.assertEqual(self.tutor.alumnos.count(), 2)

    def test_alta_de_alumno_con_tutor_nuevo(self):
        self._alta(tutor_nombre="Hugo Ocampo", tutor_telefono="55 8871 2210")
        alumno = Alumno.objects.get(nombre="Lucía Ruiz")
        self.assertEqual(alumno.tutor.nombre, "Hugo Ocampo")

    def test_alta_sin_tutor_no_guarda(self):
        respuesta = self._alta()
        self.assertEqual(respuesta.status_code, 200)
        self.assertFalse(Alumno.objects.filter(nombre="Lucía Ruiz").exists())
        self.assertFalse(Tutor.objects.filter(alumnos=None).exists())

    def test_baja_y_reactivacion_conservan_historico(self):
        Evaluacion.objects.create(
            alumno=self.alumno, fecha=date(2026, 9, 8), pase=7, recepcion=7, tiro=7
        )
        self.client.post(reverse("alumno_baja", args=[self.alumno.pk]))
        self.alumno.refresh_from_db()
        self.assertFalse(self.alumno.activo)
        self.assertEqual(self.alumno.evaluaciones.count(), 1)
        self.client.post(reverse("alumno_reactivar", args=[self.alumno.pk]))
        self.alumno.refresh_from_db()
        self.assertTrue(self.alumno.activo)

    def test_baja_solo_por_post(self):
        self.assertEqual(self.client.get(reverse("alumno_baja", args=[self.alumno.pk])).status_code, 405)

    def test_edita_evaluacion(self):
        ev = Evaluacion.objects.create(
            alumno=self.alumno, fecha=date(2026, 9, 8), pase=5, recepcion=5, tiro=5
        )
        self.client.post(
            reverse("evaluacion_editar", args=[ev.pk]),
            {"fecha": "2026-09-08", "pase": 9, "recepcion": 8, "tiro": 7},
        )
        ev.refresh_from_db()
        self.assertEqual((ev.pase, ev.recepcion, ev.tiro), (9, 8, 7))

    def test_no_permite_dos_evaluaciones_en_la_misma_fecha(self):
        Evaluacion.objects.create(
            alumno=self.alumno, fecha=date(2026, 9, 8), pase=5, recepcion=5, tiro=5
        )
        respuesta = self.client.post(
            reverse("evaluacion_nueva", args=[self.alumno.pk]),
            {"fecha": "2026-09-08", "pase": 9, "recepcion": 9, "tiro": 9},
        )
        self.assertContains(respuesta, "ya tiene una evaluación en esa fecha")
        self.assertEqual(self.alumno.evaluaciones.count(), 1)

    def test_elimina_evaluacion(self):
        ev = Evaluacion.objects.create(
            alumno=self.alumno, fecha=date(2026, 9, 8), pase=5, recepcion=5, tiro=5
        )
        self.client.post(reverse("evaluacion_eliminar", args=[ev.pk]))
        self.assertFalse(Evaluacion.objects.filter(pk=ev.pk).exists())

    def test_no_elimina_tutor_con_alumnos(self):
        self.client.post(reverse("tutor_eliminar", args=[self.tutor.pk]))
        self.assertTrue(Tutor.objects.filter(pk=self.tutor.pk).exists())

    def test_alta_de_tutor(self):
        self.client.post(
            reverse("tutor_nuevo"),
            {"nombre": "Ana Nava", "telefono": "55 4402 9931", "correo": ""},
        )
        self.assertTrue(Tutor.objects.filter(nombre="Ana Nava").exists())

    def test_boleta_individual_y_de_grupo(self):
        Evaluacion.objects.create(
            alumno=self.alumno, fecha=date(2026, 9, 8), pase=7, recepcion=8, tiro=9
        )
        respuesta = self.client.get(reverse("boleta", args=[self.alumno.pk]))
        self.assertContains(respuesta, "BOLETA DE EVALUACIÓN")
        self.assertContains(respuesta, self.tutor.nombre)
        respuesta = self.client.get(reverse("boletas_grupo") + "?grupo=MENOR-MAR_JUE")
        self.assertContains(respuesta, self.alumno.nombre)
