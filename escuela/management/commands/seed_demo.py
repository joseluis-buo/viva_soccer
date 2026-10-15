"""Carga datos de ejemplo: 8 alumnos del diseño, su histórico de evaluaciones
y tres usuarios demo (admin / secretaria / entrenador). Es idempotente; usa --reset para
borrar el padrón y volver a empezar."""

import random
from datetime import date

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand
from django.db import transaction

from escuela.models import Alumno, Categoria, Evaluacion, Horario, Tutor

User = get_user_model()

# nombre, nacimiento, categoría, horario, tutor, teléfono  (tomados de design/design.html)
ALUMNOS = [
    ("Diego Salinas Ruiz", date(2017, 3, 14), Categoria.MENOR, Horario.MAR_JUE, "Marisol Ruiz", "55 1234 5678"),
    ("Renata Ocampo Vela", date(2019, 9, 2), Categoria.MINI, Horario.LUN_MIE, "Hugo Ocampo", "55 8871 2210"),
    ("Emiliano Cortés Nava", date(2013, 11, 27), Categoria.MAYOR, Horario.LUN_MIE, "Ana Nava", "55 4402 9931"),
    ("Ximena Beltrán Ríos", date(2016, 5, 8), Categoria.MENOR, Horario.LUN_MIE, "Paola Ríos", "55 3390 1188"),
    ("Santiago Muñoz Lara", date(2014, 1, 19), Categoria.MAYOR, Horario.MAR_JUE, "Jorge Muñoz", "55 9912 4470"),
    ("Camila Herrera Sosa", date(2020, 6, 30), Categoria.MINI, Horario.MAR_JUE, "Lucía Sosa", "55 7761 3325"),
    ("Mateo Fuentes Aguilar", date(2016, 10, 11), Categoria.MENOR, Horario.MAR_JUE, "Iván Fuentes", "55 5540 8802"),
    ("Regina Palacios Cruz", date(2013, 2, 23), Categoria.MAYOR, Horario.LUN_MIE, "Sofía Cruz", "55 2218 6693"),
]

# Fechas de sesión de la temporada 2026 (abril → septiembre).
FECHAS = [
    date(2026, 4, 10),
    date(2026, 5, 8),
    date(2026, 6, 5),
    date(2026, 7, 31),
    date(2026, 8, 27),
    date(2026, 9, 8),
]


class Command(BaseCommand):
    help = "Carga alumnos, evaluaciones y usuarios de ejemplo."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Borra alumnos y evaluaciones antes de cargar.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        if options["reset"]:
            Evaluacion.objects.all().delete()
            Alumno.objects.all().delete()
            Tutor.objects.all().delete()
            self.stdout.write(self.style.WARNING("Padrón borrado."))

        for nombre in ("administrador", "secretaria", "entrenador"):
            Group.objects.get_or_create(name=nombre)

        self._usuario("admin", "admin", "administrador", is_staff=True, is_superuser=True)
        self._usuario("secretaria", "secretaria", "secretaria")
        entrenador = self._usuario("entrenador", "entrenador", "entrenador", is_staff=True)

        rnd = random.Random(2026)  # determinista: re-ejecutar da los mismos números
        for nombre, nac, categoria, horario, nombre_tutor, telefono in ALUMNOS:
            tutor, _ = Tutor.objects.get_or_create(nombre=nombre_tutor, telefono=telefono)
            alumno, _ = Alumno.objects.get_or_create(
                nombre=nombre,
                defaults={
                    "fecha_nacimiento": nac,
                    "categoria": categoria,
                    "horario": horario,
                    "tutor": tutor,
                },
            )
            base = rnd.uniform(5.0, 7.0)
            for i, fecha in enumerate(FECHAS):
                objetivo = base + i * rnd.uniform(0.3, 0.7)  # progresión ascendente

                def nota():
                    return max(1, min(10, round(objetivo + rnd.uniform(-0.6, 0.6))))

                Evaluacion.objects.get_or_create(
                    alumno=alumno,
                    fecha=fecha,
                    defaults={
                        "pase": nota(),
                        "recepcion": nota(),
                        "tiro": nota(),
                        "capturada_por": entrenador,
                    },
                )

        self.stdout.write(
            self.style.SUCCESS(
                f"Listo: {Alumno.objects.count()} alumnos, "
                f"{Evaluacion.objects.count()} evaluaciones. "
                "Usuarios: admin/admin, secretaria/secretaria y entrenador/entrenador."
            )
        )

    def _usuario(self, username, password, grupo, *, is_staff=False, is_superuser=False):
        user, nuevo = User.objects.get_or_create(
            username=username,
            defaults={
                "email": f"{username}@vivasoccer.mx",
                "is_staff": is_staff,
                "is_superuser": is_superuser,
            },
        )
        if nuevo:
            user.set_password(password)
            user.save()
        user.groups.add(Group.objects.get(name=grupo))
        return user
