"""Pruebas de las reglas de dominio y de los permisos por rol.

Cubren lo que una entrega de avance necesita demostrar:
- cálculo de promedio y folio del alumno,
- restricción de una evaluación por alumno y fecha,
- validación del teléfono,
- separación de accesos entre administrador y entrenador,
- guardado de la pantalla de captura.
"""

from datetime import date

from django.contrib.auth.models import Group, User
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from .models import Alumno, Categoria, Evaluacion, Horario
from .roles import es_administrador, es_entrenador


def crear_alumno(**extra):
    datos = {
        "nombre": "Diego Salinas Ruiz",
        "fecha_nacimiento": date(2017, 3, 14),
        "categoria": Categoria.MENOR,
        "horario": Horario.MAR_JUE,
        "tutor": "Marisol Ruiz",
        "telefono": "55 1234 5678",
    }
    datos.update(extra)
    return Alumno.objects.create(**datos)


class AlumnoModeloTests(TestCase):
    def test_folio_deriva_del_id_con_ceros(self):
        alumno = crear_alumno()
        self.assertEqual(alumno.folio, f"VS-{alumno.pk:04d}")

    def test_folio_sin_id_es_marcador(self):
        self.assertEqual(Alumno().folio, "VS-----")

    def test_telefono_con_formato_incorrecto_no_valida(self):
        alumno = crear_alumno(telefono="5512345678")
        with self.assertRaises(ValidationError):
            alumno.full_clean()

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
        self.assertFalse(es_entrenador(self.suelto))


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
        respuesta = self.client.get(reverse("dashboard"))
        self.assertEqual(respuesta.status_code, 302)
        self.assertIn(reverse("login"), respuesta["Location"])

    def test_entrenador_no_entra_al_padron(self):
        self.client.force_login(self.entrenador)
        self.assertEqual(self.client.get(reverse("padron")).status_code, 302)

    def test_administrador_entra_a_panel_padron_y_captura(self):
        self.client.force_login(self.admin)
        for nombre in ("dashboard", "padron", "captura"):
            self.assertEqual(self.client.get(reverse(nombre)).status_code, 200, nombre)

    def test_raiz_manda_a_cada_rol_a_su_pantalla(self):
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
