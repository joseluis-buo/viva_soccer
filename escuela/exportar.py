"""RF-10: exportar a CSV el padrón y las evaluaciones.

Solo administrador y secretaria (`solo_secretaria`). Los archivos van en
UTF-8 con BOM: sin esa marca al inicio, Excel los abre como Latin-1 y los
acentos salen rotos ("RecepciÃ³n").
"""

import csv

from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone

from .models import GRUPOS, Alumno, Evaluacion
from .roles import solo_secretaria
from .views import filtrar_padron

BOM = "﻿"

ENCABEZADOS_EVALUACIONES = [
    "Folio", "Alumno", "Categoría", "Horario", "Fecha",
    "Pase", "Recepción", "Tiro", "Promedio", "Observaciones", "Capturada por",
]


def _celda(valor):
    """Texto seguro para Excel.

    Una celda que empieza con = + - @ Excel la ejecuta como fórmula. Los nombres
    y las observaciones los escribe la gente, así que se les antepone un apóstrofo.
    """
    texto = "" if valor is None else str(valor)
    return "'" + texto if texto[:1] in ("=", "+", "-", "@") else texto


def _respuesta_csv(nombre_archivo, encabezados, filas):
    respuesta = HttpResponse(content_type="text/csv; charset=utf-8")
    respuesta["Content-Disposition"] = f'attachment; filename="{nombre_archivo}"'
    respuesta.write(BOM)
    escritor = csv.writer(respuesta)
    escritor.writerow(encabezados)
    for fila in filas:
        escritor.writerow([_celda(v) for v in fila])
    return respuesta


def _filas_evaluaciones(evaluaciones):
    for e in evaluaciones:
        a = e.alumno
        yield [
            a.folio, a.nombre, a.get_categoria_display(), a.get_horario_display(),
            e.fecha.strftime("%d/%m/%Y"), e.pase, e.recepcion, e.tiro, e.promedio,
            e.observaciones, e.capturada_por.username if e.capturada_por else "",
        ]


@solo_secretaria
def padron_csv(request):
    """El padrón con la misma búsqueda y grupo que se ven en pantalla, incluidas las bajas."""
    alumnos, grupo = filtrar_padron(
        request.GET.get("q", "").strip(), request.GET.get("grupo", "")
    )
    filas = (
        [
            a.folio, a.nombre, a.fecha_nacimiento.strftime("%d/%m/%Y"),
            a.get_categoria_display(), a.get_horario_display(),
            "Activo" if a.activo else "Baja",
            a.tutor.nombre, a.tutor.telefono, a.tutor.correo,
            timezone.localtime(a.fecha_alta).strftime("%d/%m/%Y"),
        ]
        for a in alumnos
    )
    encabezados = [
        "Folio", "Nombre", "Fecha de nacimiento", "Categoría", "Horario", "Estado",
        "Tutor", "Teléfono", "Correo", "Fecha de alta",
    ]
    hoy = timezone.localdate().isoformat()
    nombre = f"padron_{grupo}_{hoy}.csv" if grupo else f"padron_{hoy}.csv"
    return _respuesta_csv(nombre, encabezados, filas)


@solo_secretaria
def evaluaciones_grupo_csv(request):
    """Evaluaciones de los alumnos activos de un grupo, como las boletas del grupo."""
    grupo = request.GET.get("grupo", "")
    if grupo not in dict(GRUPOS):
        messages.error(request, "Elige un grupo para exportar sus evaluaciones.")
        return redirect("padron")
    categoria, horario = grupo.split("-")
    evaluaciones = (
        Evaluacion.objects.filter(
            alumno__activo=True, alumno__categoria=categoria, alumno__horario=horario
        )
        .select_related("alumno", "capturada_por")
        .order_by("alumno__nombre", "fecha")
    )
    nombre = f"evaluaciones_{grupo}_{timezone.localdate().isoformat()}.csv"
    return _respuesta_csv(nombre, ENCABEZADOS_EVALUACIONES, _filas_evaluaciones(evaluaciones))


@solo_secretaria
def evaluaciones_alumno_csv(request, pk):
    """Todo el histórico de un alumno, aunque esté dado de baja."""
    alumno = get_object_or_404(Alumno, pk=pk)
    evaluaciones = (
        alumno.evaluaciones.select_related("alumno", "capturada_por").order_by("fecha")
    )
    nombre = f"evaluaciones_{alumno.folio}.csv"
    return _respuesta_csv(nombre, ENCABEZADOS_EVALUACIONES, _filas_evaluaciones(evaluaciones))
