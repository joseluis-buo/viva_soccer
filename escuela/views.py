from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Avg, Count, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.utils.formats import date_format
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .forms import AlumnoForm, EvaluacionForm, TutorForm
from .models import GRUPOS, Alumno, Categoria, Evaluacion, Tutor
from .roles import (
    es_administrador,
    es_entrenador,
    es_secretaria,
    solo_administrador,
    solo_entrenador,
    solo_secretaria,
)

def _redondear(valor):
    return round(valor, 1) if valor is not None else 0.0


def _polilinea(valores, ancho=380, alto=110, vmin=0, vmax=10):
    """Puntos 'x,y x,y …' para un <polyline> SVG escalado al viewBox."""
    if not valores:
        return ""
    paso = ancho / max(len(valores) - 1, 1)
    puntos = []
    for i, v in enumerate(valores):
        x = round(i * paso, 1)
        y = round(alto - (v - vmin) / (vmax - vmin) * alto, 1)
        puntos.append(f"{x},{y}")
    return " ".join(puntos)


@login_required
def raiz(request):
    """Manda a cada rol a su pantalla principal."""
    if es_administrador(request.user):
        return redirect("dashboard")
    if es_secretaria(request.user):
        return redirect("padron")
    if es_entrenador(request.user):
        return redirect("captura")
    # Sin rol: mandarlo al login lo regresaría aquí en ciclo.
    raise PermissionDenied


@solo_administrador
def dashboard(request):
    activos = Alumno.objects.filter(activo=True)

    conteo = {c.value: 0 for c in Categoria}
    for fila in activos.values("categoria").annotate(n=Count("id")):
        conteo[fila["categoria"]] = fila["n"]
    max_cat = max(conteo.values()) or 1
    por_categoria = [
        {
            "nombre": c.label,
            "n": conteo[c.value],
            "pct": round(conteo[c.value] / max_cat * 100),
        }
        for c in Categoria
    ]

    hoy = timezone.localdate()
    eval_mes = Evaluacion.objects.filter(
        fecha__year=hoy.year, fecha__month=hoy.month
    ).count()

    agg = Evaluacion.objects.aggregate(
        p=Avg("pase"), r=Avg("recepcion"), t=Avg("tiro")
    )
    promedio_pase = _redondear(agg["p"])
    promedio_recepcion = _redondear(agg["r"])
    promedio_tiro = _redondear(agg["t"])
    promedio_general = _redondear(
        (promedio_pase + promedio_recepcion + promedio_tiro) / 3
    )

    grafica = {"categorias": [], "pase": [], "recepcion": [], "tiro": []}
    for c in Categoria:
        a = Evaluacion.objects.filter(alumno__categoria=c.value).aggregate(
            p=Avg("pase"), r=Avg("recepcion"), t=Avg("tiro")
        )
        grafica["categorias"].append(c.label)
        grafica["pase"].append(_redondear(a["p"]))
        grafica["recepcion"].append(_redondear(a["r"]))
        grafica["tiro"].append(_redondear(a["t"]))

    progreso = []
    for alumno in activos.select_related("tutor").prefetch_related("evaluaciones"):
        evs = sorted(alumno.evaluaciones.all(), key=lambda e: e.fecha)
        if len(evs) >= 2:
            progreso.append(
                {"alumno": alumno, "delta": round(evs[-1].promedio - evs[0].promedio, 1)}
            )
    progreso.sort(key=lambda x: x["delta"], reverse=True)

    return render(
        request,
        "escuela/dashboard.html",
        {
            "total_activos": activos.count(),
            "por_categoria": por_categoria,
            "eval_mes": eval_mes,
            "promedio_general": promedio_general,
            "promedio_pase": promedio_pase,
            "promedio_recepcion": promedio_recepcion,
            "promedio_tiro": promedio_tiro,
            "grafica": grafica,
            "progreso": progreso[:5],
            "hoy": hoy,
        },
    )


@solo_secretaria
def padron(request):
    q = request.GET.get("q", "").strip()
    grupo = request.GET.get("grupo", "")

    alumnos = Alumno.objects.select_related("tutor")
    if q:
        alumnos = alumnos.filter(Q(nombre__icontains=q) | Q(tutor__nombre__icontains=q))
    if grupo:
        try:
            categoria, horario = grupo.split("-")
            alumnos = alumnos.filter(categoria=categoria, horario=horario)
        except ValueError:
            grupo = ""

    paginator = Paginator(alumnos, 25)
    pagina = paginator.get_page(request.GET.get("page"))

    chips = [{"valor": "", "label": "TODOS", "activo": grupo == ""}]
    for valor, label in GRUPOS:
        chips.append({"valor": valor, "label": label, "activo": grupo == valor})

    return render(
        request,
        "escuela/padron.html",
        {
            "pagina": pagina,
            "q": q,
            "grupo": grupo,
            "chips": chips,
            "total": paginator.count,
        },
    )


@solo_secretaria
def padron_detalle(request, pk):
    """Panel lateral del padrón (se carga con hx-get al hacer clic en la fila)."""
    alumno = get_object_or_404(Alumno, pk=pk)
    evs = list(alumno.evaluaciones.order_by("fecha"))
    ultima = evs[-1] if evs else None
    serie = {
        "pase": _polilinea([e.pase for e in evs]),
        "recepcion": _polilinea([e.recepcion for e in evs]),
        "tiro": _polilinea([e.tiro for e in evs]),
    }
    return render(
        request,
        "escuela/_padron_detalle.html",
        {"alumno": alumno, "ultima": ultima, "serie": serie},
    )


@solo_secretaria
def alumno_nuevo(request):
    return _guardar_alumno(request, Alumno(), "AGREGAR ALUMNO", reverse("alumno_nuevo"))


@solo_secretaria
def alumno_editar(request, pk):
    alumno = get_object_or_404(Alumno, pk=pk)
    return _guardar_alumno(
        request, alumno, "EDITAR ALUMNO", reverse("alumno_editar", args=[pk])
    )


def _modal(request, plantilla, contexto):
    """Formulario en modal: fragmento si llega por HTMX, página completa si no."""
    es_htmx = request.headers.get("HX-Request") == "true"
    contexto["plantilla_base"] = "escuela/_vacio.html" if es_htmx else "base.html"
    return render(request, plantilla, contexto)


def _redirigir_htmx(destino):
    respuesta = HttpResponse(status=204)
    respuesta["HX-Redirect"] = destino
    return respuesta


def _guardar_alumno(request, instancia, titulo, accion):
    form = AlumnoForm(request.POST or None, instance=instancia)
    if request.method == "POST" and form.is_valid():
        alumno = form.save()
        messages.success(request, f"Alumno {alumno.nombre} guardado.")
        # Vuelve a la pantalla desde donde se abrió el modal (padrón o ficha).
        origen = request.headers.get("HX-Current-URL", "")
        if not url_has_allowed_host_and_scheme(origen, {request.get_host()}):
            origen = reverse("padron")
        return _redirigir_htmx(origen)
    return _modal(
        request,
        "escuela/_alumno_form.html",
        {"form": form, "titulo": titulo, "accion": accion},
    )


@solo_secretaria
@require_POST
def alumno_baja(request, pk):
    alumno = get_object_or_404(Alumno, pk=pk)
    alumno.activo = False
    alumno.save(update_fields=["activo"])
    messages.success(request, f"{alumno.nombre} quedó dado de baja. Su histórico se conserva.")
    return redirect("ficha", pk=pk)


@solo_secretaria
@require_POST
def alumno_reactivar(request, pk):
    alumno = get_object_or_404(Alumno, pk=pk)
    alumno.activo = True
    alumno.save(update_fields=["activo"])
    messages.success(request, f"{alumno.nombre} está activo otra vez.")
    return redirect("ficha", pk=pk)


def _promedio_categoria(categoria):
    cat = Evaluacion.objects.filter(alumno__categoria=categoria).aggregate(
        p=Avg("pase"), r=Avg("recepcion"), t=Avg("tiro")
    )
    if cat["p"] is None:
        return None
    return round((cat["p"] + cat["r"] + cat["t"]) / 3, 1)


def _comparativo(alumno, promedio_categoria):
    """Histórico del alumno y su promedio frente al de su categoría (ficha y boleta)."""
    evs = list(alumno.evaluaciones.order_by("fecha"))
    ultima = evs[-1] if evs else None
    promedio_actual = ultima.promedio if ultima else None

    diferencia_txt = "—"
    diferencia_clase = ""
    if promedio_actual is not None and promedio_categoria is not None:
        diferencia = round(promedio_actual - promedio_categoria, 1)
        diferencia_txt = f"+{diferencia}" if diferencia > 0 else str(diferencia)
        diferencia_clase = "text-success" if diferencia >= 0 else "text-danger"

    return {
        "alumno": alumno,
        "evs": evs,
        "ultima": ultima,
        "promedio_actual": promedio_actual,
        "promedio_categoria": promedio_categoria,
        "diferencia_txt": diferencia_txt,
        "diferencia_clase": diferencia_clase,
    }


@solo_secretaria
def ficha(request, pk):
    alumno = get_object_or_404(Alumno.objects.select_related("tutor"), pk=pk)
    datos = _comparativo(alumno, _promedio_categoria(alumno.categoria))
    evs = datos.pop("evs")

    serie = {
        "fechas": [date_format(e.fecha, "d M").upper() for e in evs],
        "pase": [e.pase for e in evs],
        "recepcion": [e.recepcion for e in evs],
        "tiro": [e.tiro for e in evs],
    }

    return render(
        request,
        "escuela/ficha.html",
        {**datos, "evaluaciones": list(reversed(evs)), "serie": serie},
    )


@solo_secretaria
def evaluacion_nueva(request, pk):
    alumno = get_object_or_404(Alumno, pk=pk)
    return _guardar_evaluacion(
        request, alumno, Evaluacion(capturada_por=request.user), "NUEVA EVALUACIÓN",
        reverse("evaluacion_nueva", args=[pk]),
    )


@solo_secretaria
def evaluacion_editar(request, pk):
    evaluacion = get_object_or_404(Evaluacion.objects.select_related("alumno"), pk=pk)
    return _guardar_evaluacion(
        request, evaluacion.alumno, evaluacion, "EDITAR EVALUACIÓN",
        reverse("evaluacion_editar", args=[pk]),
    )


def _guardar_evaluacion(request, alumno, instancia, titulo, accion):
    form = EvaluacionForm(request.POST or None, instance=instancia, alumno=alumno)
    if request.method == "POST" and form.is_valid():
        evaluacion = form.save()
        messages.success(request, f"Evaluación del {evaluacion.fecha:%d/%m/%Y} guardada.")
        return _redirigir_htmx(reverse("ficha", args=[alumno.pk]))
    return _modal(
        request,
        "escuela/_evaluacion_form.html",
        {"form": form, "alumno": alumno, "titulo": titulo, "accion": accion},
    )


@solo_secretaria
@require_POST
def evaluacion_eliminar(request, pk):
    evaluacion = get_object_or_404(Evaluacion, pk=pk)
    evaluacion.delete()
    messages.success(request, f"Se eliminó la evaluación del {evaluacion.fecha:%d/%m/%Y}.")
    return redirect("ficha", pk=evaluacion.alumno_id)


# ---------- Tutores ----------


@solo_secretaria
def tutores(request):
    q = request.GET.get("q", "").strip()
    lista = Tutor.objects.prefetch_related("alumnos")
    if q:
        lista = lista.filter(
            Q(nombre__icontains=q) | Q(telefono__icontains=q) | Q(alumnos__nombre__icontains=q)
        ).distinct()
    pagina = Paginator(lista, 25).get_page(request.GET.get("page"))
    return render(request, "escuela/tutores.html", {"pagina": pagina, "q": q})


@solo_secretaria
def tutor_nuevo(request):
    return _guardar_tutor(request, Tutor(), "AGREGAR TUTOR", reverse("tutor_nuevo"))


@solo_secretaria
def tutor_editar(request, pk):
    tutor = get_object_or_404(Tutor, pk=pk)
    return _guardar_tutor(request, tutor, "EDITAR TUTOR", reverse("tutor_editar", args=[pk]))


def _guardar_tutor(request, instancia, titulo, accion):
    form = TutorForm(request.POST or None, instance=instancia)
    if request.method == "POST" and form.is_valid():
        tutor = form.save()
        messages.success(request, f"Tutor {tutor.nombre} guardado.")
        return _redirigir_htmx(reverse("tutores"))
    return _modal(
        request,
        "escuela/_tutor_form.html",
        {"form": form, "titulo": titulo, "accion": accion},
    )


@solo_secretaria
@require_POST
def tutor_eliminar(request, pk):
    tutor = get_object_or_404(Tutor, pk=pk)
    if tutor.alumnos.exists():
        messages.error(request, f"{tutor.nombre} tiene alumnos registrados; no se puede eliminar.")
    else:
        tutor.delete()
        messages.success(request, f"Se eliminó al tutor {tutor.nombre}.")
    return redirect("tutores")


# ---------- Boletas ----------


@solo_secretaria
def boleta(request, pk):
    alumno = get_object_or_404(Alumno.objects.select_related("tutor"), pk=pk)
    boletas = [_comparativo(alumno, _promedio_categoria(alumno.categoria))]
    return render(request, "escuela/boleta.html", {"boletas": boletas, "hoy": timezone.localdate()})


@solo_secretaria
def boletas_grupo(request):
    """Todas las boletas de un grupo (alumnos activos), una por hoja."""
    grupo = request.GET.get("grupo", "")
    if grupo not in dict(GRUPOS):
        messages.error(request, "Elige un grupo para imprimir sus boletas.")
        return redirect("padron")
    categoria, horario = grupo.split("-")
    promedio_categoria = _promedio_categoria(categoria)
    alumnos = Alumno.objects.filter(
        activo=True, categoria=categoria, horario=horario
    ).select_related("tutor")
    boletas = [_comparativo(a, promedio_categoria) for a in alumnos]
    return render(
        request,
        "escuela/boleta.html",
        {"boletas": boletas, "grupo": dict(GRUPOS)[grupo], "hoy": timezone.localdate()},
    )


@solo_entrenador
def captura(request):
    grupo = request.GET.get("grupo") or GRUPOS[0][0]
    if grupo not in dict(GRUPOS):
        grupo = GRUPOS[0][0]
    categoria, horario = grupo.split("-")

    fecha = parse_date(request.GET.get("fecha", "")) or timezone.localdate()

    alumnos = list(
        Alumno.objects.filter(activo=True, categoria=categoria, horario=horario).order_by(
            "nombre"
        )
    )
    existentes = {
        e.alumno_id: e
        for e in Evaluacion.objects.filter(alumno__in=alumnos, fecha=fecha)
    }

    if request.method == "POST":
        guardadas = 0
        for alumno in alumnos:
            crudo = (
                request.POST.get(f"pase_{alumno.id}"),
                request.POST.get(f"recepcion_{alumno.id}"),
                request.POST.get(f"tiro_{alumno.id}"),
            )
            if not all(crudo):
                continue
            try:
                pase, recepcion, tiro = (int(x) for x in crudo)
            except ValueError:
                continue
            if not all(1 <= v <= 10 for v in (pase, recepcion, tiro)):
                continue
            Evaluacion.objects.update_or_create(
                alumno=alumno,
                fecha=fecha,
                defaults={
                    "pase": pase,
                    "recepcion": recepcion,
                    "tiro": tiro,
                    "capturada_por": request.user,
                },
            )
            guardadas += 1
        messages.success(request, f"Se guardaron {guardadas} evaluaciones.")
        destino = f"{reverse('captura')}?grupo={grupo}&fecha={fecha.isoformat()}"
        return redirect(destino)

    filas = []
    for alumno in alumnos:
        e = existentes.get(alumno.id)
        filas.append(
            {
                "alumno": alumno,
                "pase": e.pase if e else "",
                "recepcion": e.recepcion if e else "",
                "tiro": e.tiro if e else "",
                "completa": e is not None,
            }
        )
    capturados = sum(1 for f in filas if f["completa"])

    return render(
        request,
        "escuela/captura.html",
        {
            "grupos": GRUPOS,
            "grupo": grupo,
            "fecha": fecha,
            "filas": filas,
            "capturados": capturados,
            "total": len(filas),
            "pct": round(capturados / len(filas) * 100) if filas else 0,
        },
    )
