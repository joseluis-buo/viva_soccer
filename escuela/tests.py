"""Pruebas de las reglas de dominio y de los permisos por rol.

Cubren lo que una entrega de avance necesita demostrar:
- cálculo de promedio y folio del alumno,
- restricción de una evaluación por alumno y fecha,
- validación del teléfono,
- separación de accesos entre administrador, secretaria y entrenador,
- guardado de la pantalla de captura,
- funciones de secretaria: tutores, baja, corrección de evaluaciones y boletas,
- app móvil: cuenta del tutor, sus hijos y códigos de activación de un solo uso,
- grupos asignados a cada entrenador,
- observaciones de las evaluaciones y comunicados en el admin,
- configuración de producción (Railway) leída del entorno.
"""

import os
import subprocess
import sys
from datetime import date, timedelta
from io import StringIO
from pathlib import Path
from unittest import mock

from dotenv import dotenv_values

from django.contrib.auth.models import Group, User
from django.core.management import CommandError, call_command
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .management.commands.seed_demo import nombre_de_la_base
from .models import (
    GRUPOS,
    Alumno,
    AsignacionEntrenador,
    Categoria,
    CodigoActivacion,
    CodigoYaUsado,
    Comunicado,
    Evaluacion,
    Horario,
    Tutor,
)
from .roles import (
    alumnos_del_entrenador,
    alumnos_del_tutor,
    es_administrador,
    es_entrenador,
    es_secretaria,
    es_tutor,
    grupos_de,
)


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
        self.assertFalse(es_tutor(self.suelto))

    def test_tutor_no_tiene_roles_de_la_escuela(self):
        tutor = usuario_con_grupo("papa", "tutor")
        self.assertTrue(es_tutor(tutor))
        self.assertFalse(es_administrador(tutor))
        self.assertFalse(es_secretaria(tutor))
        self.assertFalse(es_entrenador(tutor))

    def test_administrador_no_es_tutor(self):
        # Ser tutor es ser papá de alumnos concretos, no un permiso que se hereda.
        self.assertFalse(es_tutor(self.admin))

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

    def test_guarda_las_observaciones_y_las_vuelve_a_mostrar(self):
        url = reverse("captura") + "?grupo=MINI-LUN_MIE&fecha=2026-09-08"
        self.client.post(
            url,
            {
                f"pase_{self.alumno.id}": "7",
                f"recepcion_{self.alumno.id}": "8",
                f"tiro_{self.alumno.id}": "6",
                f"observaciones_{self.alumno.id}": "  Mejoró el pase largo.  ",
            },
        )
        ev = Evaluacion.objects.get(alumno=self.alumno)
        self.assertEqual(ev.observaciones, "Mejoró el pase largo.")
        self.assertContains(self.client.get(url), "Mejoró el pase largo.")

    def test_sin_observaciones_se_guarda_vacia(self):
        url = reverse("captura") + "?grupo=MINI-LUN_MIE&fecha=2026-09-08"
        self.client.post(
            url,
            {
                f"pase_{self.alumno.id}": "7",
                f"recepcion_{self.alumno.id}": "8",
                f"tiro_{self.alumno.id}": "6",
            },
        )
        self.assertEqual(Evaluacion.objects.get(alumno=self.alumno).observaciones, "")

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

    def test_corrige_las_observaciones_desde_la_ficha(self):
        ev = Evaluacion.objects.create(
            alumno=self.alumno, fecha=date(2026, 9, 8), pase=5, recepcion=5, tiro=5
        )
        self.client.post(
            reverse("evaluacion_editar", args=[ev.pk]),
            {"fecha": "2026-09-08", "pase": 5, "recepcion": 5, "tiro": 5,
             "observaciones": "Faltó por lesión a media sesión."},
        )
        ev.refresh_from_db()
        self.assertEqual(ev.observaciones, "Faltó por lesión a media sesión.")

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



class CuentaTutorTests(TestCase):
    def test_hijos_del_tutor_son_los_alumnos_que_ya_lo_tienen_asignado(self):
        tutor = crear_tutor()
        diego = crear_alumno(nombre="Diego Salinas Ruiz", tutor=tutor)
        sofia = crear_alumno(nombre="Sofía Salinas Ruiz", tutor=tutor)
        crear_alumno(nombre="Otro Niño")  # con otro tutor
        CodigoActivacion.objects.create(tutor=tutor).canjear("cancha-2026")
        usuario = User.objects.get(username="5512345678")
        self.assertQuerySetEqual(usuario.tutor.alumnos.all(), [diego, sofia], ordered=False)

    def test_tutor_sin_cuenta_por_omision(self):
        self.assertIsNone(crear_tutor().usuario)

    def test_un_usuario_solo_puede_ser_cuenta_de_un_tutor(self):
        usuario = User.objects.create_user("5512345678")
        crear_tutor(usuario=usuario)
        with self.assertRaises(IntegrityError), transaction.atomic():
            crear_tutor(nombre="Otra Persona", usuario=usuario)

    def test_borrar_la_cuenta_no_borra_al_tutor_ni_a_sus_hijos(self):
        tutor = crear_tutor()
        alumno = crear_alumno(tutor=tutor)
        usuario = CodigoActivacion.objects.create(tutor=tutor).canjear("cancha-2026")
        usuario.delete()
        tutor.refresh_from_db()
        self.assertIsNone(tutor.usuario)
        self.assertQuerySetEqual(tutor.alumnos.all(), [alumno])


class CodigoActivacionTests(TestCase):
    def setUp(self):
        self.tutor = crear_tutor()
        self.codigo = CodigoActivacion.objects.create(tutor=self.tutor)

    def test_codigo_se_genera_solo_y_sin_caracteres_confusos(self):
        self.assertEqual(len(self.codigo.codigo), 8)
        self.assertFalse(set(self.codigo.codigo) & set("01OIL"))
        self.assertTrue(self.codigo.vigente)

    def test_canjear_crea_la_cuenta_con_el_telefono_y_rol_tutor(self):
        usuario = self.codigo.canjear("cancha-2026")
        self.tutor.refresh_from_db()
        self.assertEqual(self.tutor.usuario, usuario)
        self.assertEqual(usuario.username, "5512345678")
        self.assertTrue(usuario.is_active)
        self.assertTrue(usuario.check_password("cancha-2026"))
        self.assertTrue(es_tutor(usuario))
        self.assertFalse(self.codigo.vigente)

    def test_codigo_nuevo_cambia_la_contrasena_de_la_cuenta_existente(self):
        # Si el padre olvida su contraseña, la escuela le da otro código.
        usuario = self.codigo.canjear("cancha-2026")
        otro = CodigoActivacion.objects.create(tutor=self.tutor)
        self.assertEqual(otro.canjear("nueva-clave"), usuario)
        usuario.refresh_from_db()
        self.assertTrue(usuario.check_password("nueva-clave"))
        self.assertEqual(User.objects.filter(username="5512345678").count(), 1)

    def test_codigo_no_se_puede_usar_dos_veces(self):
        self.codigo.canjear("cancha-2026")
        with self.assertRaises(CodigoYaUsado):
            self.codigo.canjear("otra-clave")
        self.tutor.refresh_from_db()
        self.assertTrue(self.tutor.usuario.check_password("cancha-2026"))

    def test_segundo_uso_falla_aunque_se_cargue_de_nuevo_de_la_base(self):
        # Simula dos peticiones que leyeron el código antes de que se usara.
        copia = CodigoActivacion.objects.get(pk=self.codigo.pk)
        self.codigo.canjear("cancha-2026")
        with self.assertRaises(CodigoYaUsado):
            copia.canjear("otra-clave")
        self.tutor.refresh_from_db()
        self.assertTrue(self.tutor.usuario.check_password("cancha-2026"))

    def test_codigo_vencido_no_se_puede_usar(self):
        self.codigo.vence = timezone.now() - timedelta(minutes=1)
        self.codigo.save()
        with self.assertRaises(CodigoYaUsado):
            self.codigo.canjear("cancha-2026")
        self.tutor.refresh_from_db()
        self.assertIsNone(self.tutor.usuario)

    def test_si_falla_la_creacion_de_la_cuenta_el_codigo_sigue_vigente(self):
        # Otro usuario ya ocupa ese teléfono como nombre de usuario.
        User.objects.create_user("5512345678")
        with self.assertRaises(IntegrityError):
            self.codigo.canjear("cancha-2026")
        self.codigo.refresh_from_db()
        self.assertTrue(self.codigo.vigente)


class AdminAppMovilTests(TestCase):
    def test_secretaria_puede_gestionar_codigos_en_el_admin(self):
        secretaria = usuario_con_grupo("sec", "secretaria")
        secretaria.is_staff = True
        secretaria.save()
        self.client.force_login(secretaria)
        tutor = crear_tutor()
        respuesta = self.client.get(reverse("admin:escuela_tutor_change", args=[tutor.pk]))
        self.assertEqual(respuesta.status_code, 200)
        respuesta = self.client.get(reverse("admin:escuela_codigoactivacion_add"))
        self.assertEqual(respuesta.status_code, 200)


class AsignacionEntrenadorTests(TestCase):
    def setUp(self):
        self.profe = usuario_con_grupo("profe", "entrenador")
        AsignacionEntrenador.objects.create(
            entrenador=self.profe, categoria=Categoria.MENOR, horario=Horario.MAR_JUE
        )

    def test_entrenador_solo_tiene_sus_grupos(self):
        self.assertEqual(grupos_de(self.profe), ["MENOR-MAR_JUE"])

    def test_administrador_tiene_los_seis_sin_asignaciones(self):
        jefa = usuario_con_grupo("jefa", "administrador")
        self.assertEqual(grupos_de(jefa), [clave for clave, _ in GRUPOS])

    def test_otros_roles_no_tienen_grupos_aunque_tengan_asignacion(self):
        tutor = usuario_con_grupo("papa", "tutor")
        AsignacionEntrenador.objects.create(
            entrenador=tutor, categoria=Categoria.MINI, horario=Horario.LUN_MIE
        )
        self.assertEqual(grupos_de(tutor), [])
        self.assertFalse(alumnos_del_entrenador(tutor).exists())

    def test_alumnos_del_entrenador_son_los_activos_de_sus_grupos(self):
        tutor = crear_tutor()
        diego = crear_alumno(tutor=tutor)
        crear_alumno(nombre="Baja", activo=False, tutor=tutor)
        crear_alumno(nombre="Otro grupo", categoria=Categoria.MAYOR, tutor=tutor)
        crear_alumno(nombre="Otro horario", horario=Horario.LUN_MIE, tutor=tutor)
        self.assertEqual(list(alumnos_del_entrenador(self.profe)), [diego])

    def test_no_se_repite_el_mismo_grupo_para_un_entrenador(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            AsignacionEntrenador.objects.create(
                entrenador=self.profe, categoria=Categoria.MENOR, horario=Horario.MAR_JUE
            )

    def test_secretaria_asigna_grupos_desde_el_admin(self):
        secretaria = usuario_con_grupo("sec", "secretaria")
        secretaria.is_staff = True
        secretaria.save()
        self.client.force_login(secretaria)
        respuesta = self.client.post(
            reverse("admin:escuela_asignacionentrenador_add"),
            {"entrenador": self.profe.pk, "categoria": "MINI", "horario": "LUN_MIE"},
        )
        self.assertEqual(respuesta.status_code, 302)
        self.assertEqual(grupos_de(self.profe), ["MINI-LUN_MIE", "MENOR-MAR_JUE"])

    def test_en_el_admin_solo_se_elige_entre_entrenadores(self):
        usuario_con_grupo("papa", "tutor")
        self.client.force_login(User.objects.create_superuser("root", password="x"))
        respuesta = self.client.get(reverse("admin:escuela_asignacionentrenador_add"))
        opciones = respuesta.context["adminform"].form.fields["entrenador"].queryset
        self.assertEqual(list(opciones), [self.profe])


class ComunicadoAdminTests(TestCase):
    def setUp(self):
        self.secretaria = usuario_con_grupo("sec", "secretaria")
        self.secretaria.is_staff = True
        self.secretaria.save()
        self.client.force_login(self.secretaria)

    def test_secretaria_publica_un_comunicado_y_queda_como_autora(self):
        respuesta = self.client.post(
            reverse("admin:escuela_comunicado_add"),
            {
                "titulo": "Suspensión por lluvia",
                "cuerpo": "Hoy no hay entrenamiento.",
                "categoria": "",
                "publicado_0": "2026-10-22",
                "publicado_1": "10:00:00",
            },
        )
        self.assertEqual(respuesta.status_code, 302)
        comunicado = Comunicado.objects.get()
        self.assertEqual(comunicado.autor, self.secretaria)
        self.assertEqual(comunicado.categoria, "")

    def test_secretaria_tiene_los_cuatro_permisos(self):
        for accion in ("add", "change", "delete", "view"):
            with self.subTest(accion=accion):
                self.assertTrue(self.secretaria.has_perm(f"escuela.{accion}_comunicado"))

    def test_entrenador_no_entra_a_comunicados(self):
        profe = usuario_con_grupo("profe", "entrenador")
        profe.is_staff = True
        profe.save()
        self.client.force_login(profe)
        respuesta = self.client.get(reverse("admin:escuela_comunicado_add"))
        self.assertEqual(respuesta.status_code, 403)


class SeedDemoTests(TestCase):
    def test_el_entrenador_demo_queda_con_grupos(self):
        call_command("seed_demo", stdout=StringIO())
        call_command("seed_demo", stdout=StringIO())  # idempotente
        entrenador = User.objects.get(username="entrenador")
        self.assertEqual(entrenador.asignaciones.count(), 4)
        self.assertTrue(alumnos_del_entrenador(entrenador).exists())

    def test_deja_comunicados_y_observaciones_para_la_demostracion(self):
        call_command("seed_demo", stdout=StringIO())
        call_command("seed_demo", stdout=StringIO())  # idempotente
        self.assertEqual(Comunicado.objects.count(), 3)
        self.assertTrue(Comunicado.objects.filter(categoria="").exists())
        self.assertTrue(Comunicado.objects.exclude(publicado__gt=timezone.now()).exists())
        self.assertGreaterEqual(Evaluacion.objects.exclude(observaciones="").count(), 3)

    def test_deja_una_mama_con_cuenta_activa_que_ve_a_su_hijo(self):
        call_command("seed_demo", stdout=StringIO())
        call_command("seed_demo", stdout=StringIO())  # idempotente
        mama = User.objects.get(username="5512345678")
        self.assertTrue(mama.check_password("tutor"))
        self.assertTrue(es_tutor(mama))
        self.assertEqual(
            [a.nombre for a in alumnos_del_tutor(mama)], ["Diego Salinas Ruiz"]
        )

    def test_deja_un_codigo_vigente_de_un_papa_sin_cuenta(self):
        call_command("seed_demo", stdout=StringIO())
        codigo = CodigoActivacion.objects.get(codigo="CANCHA26")
        self.assertTrue(codigo.vigente)
        self.assertEqual(codigo.tutor.nombre, "Hugo Ocampo")
        self.assertIsNone(codigo.tutor.usuario)
        papa = codigo.canjear("cancha-2026")
        self.assertEqual(papa.username, "5588712210")

    def test_volver_a_sembrar_renueva_el_codigo_ya_canjeado(self):
        call_command("seed_demo", stdout=StringIO())
        CodigoActivacion.objects.get(codigo="CANCHA26").canjear("cancha-2026")
        call_command("seed_demo", stdout=StringIO())
        self.assertTrue(CodigoActivacion.objects.get(codigo="CANCHA26").vigente)

    @override_settings(DEBUG=True)
    def test_reset_borra_las_cuentas_de_los_papas_para_activar_desde_cero(self):
        call_command("seed_demo", stdout=StringIO())
        CodigoActivacion.objects.get(codigo="CANCHA26").canjear("cancha-2026")
        call_command(
            "seed_demo", "--reset", confirmar=nombre_de_la_base(), stdout=StringIO()
        )
        codigo = CodigoActivacion.objects.get(codigo="CANCHA26")
        self.assertIsNone(codigo.tutor.usuario)
        self.assertFalse(User.objects.filter(username="5588712210").exists())
        self.assertTrue(User.objects.get(username="5512345678").check_password("tutor"))


class ResetProtegidoTests(TestCase):
    """--reset borra datos de todo el equipo: pide el nombre de la base y nunca corre en producción."""

    def setUp(self):
        call_command("seed_demo", stdout=StringIO())
        self.alumnos = Alumno.objects.count()

    def reset(self, **opciones):
        call_command("seed_demo", "--reset", stdout=StringIO(), **opciones)

    def assertNoSeBorroNada(self):
        self.assertEqual(Alumno.objects.count(), self.alumnos)
        self.assertTrue(User.objects.filter(username="5512345678").exists())

    def test_con_debug_apagado_se_niega_aunque_el_nombre_sea_correcto(self):
        # Las pruebas de Django ya corren con DEBUG=False, como producción.
        with self.assertRaisesMessage(CommandError, "DEBUG apagado"):
            self.reset(confirmar=nombre_de_la_base())
        self.assertNoSeBorroNada()

    @override_settings(DEBUG=True)
    def test_con_otro_nombre_no_borra_nada(self):
        with self.assertRaisesMessage(CommandError, "No se borró nada"):
            self.reset(confirmar="otra-base")
        self.assertNoSeBorroNada()

    @override_settings(DEBUG=True)
    def test_pregunta_el_nombre_si_no_viene_confirmado(self):
        CodigoActivacion.objects.get(codigo="CANCHA26").canjear("cancha-2026")
        with mock.patch("builtins.input", return_value=nombre_de_la_base()) as pregunta:
            self.reset()
        pregunta.assert_called_once()
        # Se borró y se volvió a sembrar: la cuenta que Hugo activó ya no está.
        self.assertFalse(User.objects.filter(username="5588712210").exists())
        self.assertEqual(Alumno.objects.count(), self.alumnos)

    @override_settings(DEBUG=True)
    def test_respuesta_equivocada_al_preguntar_no_borra_nada(self):
        CodigoActivacion.objects.get(codigo="CANCHA26").canjear("cancha-2026")
        with mock.patch("builtins.input", return_value="si"):
            with self.assertRaises(CommandError):
                self.reset()
        self.assertTrue(User.objects.filter(username="5588712210").exists())
        self.assertNoSeBorroNada()

    @override_settings(DEBUG=True)
    def test_sin_teclado_no_borra_nada(self):
        with mock.patch("builtins.input", side_effect=EOFError):
            with self.assertRaises(CommandError):
                self.reset()
        self.assertNoSeBorroNada()


class ConfiguracionProduccionTests(TestCase):
    """settings.py se importa en otro proceso con el entorno de Railway simulado."""

    RAIZ = Path(__file__).resolve().parent.parent
    ENTORNO_RAILWAY = {
        "RAILWAY_ENVIRONMENT_NAME": "production",
        "DJANGO_SECRET_KEY": "llave-de-prueba",
        "DATABASE_URL": "postgresql://u:p@ep-prueba.neon.tech/neondb",
        "DJANGO_ALLOWED_HOSTS": "vivasoccer.up.railway.app",
        "DJANGO_CSRF_TRUSTED": "https://vivasoccer.up.railway.app",
    }
    VARIABLES_DEL_PROYECTO = ["DJANGO_DEBUG", *ENTORNO_RAILWAY]

    def importar_settings(self, **variables):
        """Importa settings con solo `variables` (más las del .env) y devuelve el proceso."""
        entorno = {
            k: v for k, v in os.environ.items() if k not in self.VARIABLES_DEL_PROYECTO
        }
        entorno.update(variables)
        codigo = (
            "import vivasoccer.settings as s; "
            "print(s.DEBUG, s.ALLOWED_HOSTS, s.CSRF_TRUSTED_ORIGINS, "
            "s.SESSION_COOKIE_SECURE)"
        )
        return subprocess.run(
            [sys.executable, "-c", codigo],
            cwd=self.RAIZ, env=entorno, capture_output=True, text=True,
        )

    def test_en_railway_debug_queda_apagado_aunque_pidan_encenderlo(self):
        proceso = self.importar_settings(**self.ENTORNO_RAILWAY, DJANGO_DEBUG="1")
        self.assertEqual(proceso.returncode, 0, proceso.stderr)
        self.assertEqual(
            proceso.stdout.strip(),
            "False ['vivasoccer.up.railway.app'] "
            "['https://vivasoccer.up.railway.app'] True",
        )

    def test_sin_allowed_hosts_en_produccion_falla_con_mensaje_claro(self):
        if "DJANGO_ALLOWED_HOSTS" in dotenv_values(self.RAIZ / ".env"):
            self.skipTest("El .env local define DJANGO_ALLOWED_HOSTS.")
        entorno = dict(self.ENTORNO_RAILWAY)
        del entorno["DJANGO_ALLOWED_HOSTS"]
        proceso = self.importar_settings(**entorno)
        self.assertNotEqual(proceso.returncode, 0)
        self.assertIn("Falta DJANGO_ALLOWED_HOSTS", proceso.stderr)

    def test_listas_separadas_por_coma_ignoran_espacios(self):
        entorno = {**self.ENTORNO_RAILWAY, "DJANGO_ALLOWED_HOSTS": " a.up.railway.app , b.mx ,"}
        proceso = self.importar_settings(**entorno)
        self.assertIn("['a.up.railway.app', 'b.mx']", proceso.stdout)
