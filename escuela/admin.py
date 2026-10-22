from django.contrib import admin

from .models import (
    AsignacionEntrenador,
    Alumno,
    CodigoActivacion,
    Comunicado,
    Evaluacion,
    Tutor,
)

admin.site.site_header = "VIVA SOCCER — Administración"
admin.site.site_title = "VIVA SOCCER"
admin.site.index_title = "Padrón y evaluaciones"


class EvaluacionInline(admin.TabularInline):
    model = Evaluacion
    extra = 0
    fields = ["fecha", "pase", "recepcion", "tiro", "promedio", "capturada_por"]
    readonly_fields = ["promedio"]

    @admin.display(description="promedio")
    def promedio(self, obj):
        return obj.promedio if obj.promedio is not None else "—"


@admin.register(Alumno)
class AlumnoAdmin(admin.ModelAdmin):
    list_display = [
        "folio",
        "nombre",
        "categoria",
        "horario",
        "fecha_nacimiento",
        "tutor",
        "telefono",
        "activo",
    ]
    list_select_related = ["tutor"]
    list_filter = ["categoria", "horario", "activo"]
    search_fields = ["nombre", "tutor__nombre", "tutor__telefono"]
    list_per_page = 25
    autocomplete_fields = ["tutor"]
    inlines = [EvaluacionInline]

    @admin.display(description="teléfono", ordering="tutor__telefono")
    def telefono(self, obj):
        return obj.tutor.telefono

    @admin.display(description="folio", ordering="id")
    def folio(self, obj):
        return obj.folio


class AlumnoInline(admin.TabularInline):
    model = Alumno
    extra = 0
    fields = ["nombre", "categoria", "horario", "activo"]
    show_change_link = True


class CodigoActivacionInline(admin.TabularInline):
    """Desde la ficha del tutor se genera su código: basta con agregar una fila."""

    model = CodigoActivacion
    extra = 0
    fields = ["codigo", "creado", "vence", "usado"]
    readonly_fields = ["codigo", "creado", "usado"]


@admin.register(Tutor)
class TutorAdmin(admin.ModelAdmin):
    list_display = ["nombre", "telefono", "correo", "tiene_cuenta"]
    search_fields = ["nombre", "telefono", "correo"]
    # La cuenta la crea el canje del código, no se elige a mano.
    readonly_fields = ["usuario"]
    inlines = [AlumnoInline, CodigoActivacionInline]

    @admin.display(description="cuenta de la app", boolean=True)
    def tiene_cuenta(self, obj):
        return obj.usuario_id is not None


@admin.register(CodigoActivacion)
class CodigoActivacionAdmin(admin.ModelAdmin):
    list_display = ["codigo", "tutor", "creado", "vence", "usado"]
    list_select_related = ["tutor"]
    search_fields = ["codigo", "tutor__nombre", "tutor__telefono"]
    autocomplete_fields = ["tutor"]
    readonly_fields = ["codigo", "creado", "usado"]


@admin.register(Evaluacion)
class EvaluacionAdmin(admin.ModelAdmin):
    list_display = [
        "alumno",
        "fecha",
        "pase",
        "recepcion",
        "tiro",
        "promedio",
        "capturada_por",
    ]
    list_filter = ["fecha", "alumno__categoria", "alumno__horario"]
    search_fields = ["alumno__nombre"]
    date_hierarchy = "fecha"
    autocomplete_fields = ["alumno"]

    @admin.display(description="promedio")
    def promedio(self, obj):
        return obj.promedio if obj.promedio is not None else "—"


@admin.register(AsignacionEntrenador)
class AsignacionEntrenadorAdmin(admin.ModelAdmin):
    """Qué grupos ve cada entrenador en la app. La secretaria también los asigna."""

    list_display = ["entrenador", "categoria", "horario"]
    list_select_related = ["entrenador"]
    list_filter = ["categoria", "horario", "entrenador"]


@admin.register(Comunicado)
class ComunicadoAdmin(admin.ModelAdmin):
    """Avisos de la app de los padres. Los publican el administrador y la secretaria."""

    list_display = ["titulo", "dirigido_a", "publicado", "autor"]
    list_select_related = ["autor"]
    list_filter = ["categoria"]
    search_fields = ["titulo", "cuerpo"]
    date_hierarchy = "publicado"
    fields = ["titulo", "cuerpo", "categoria", "publicado", "autor"]
    readonly_fields = ["autor"]

    @admin.display(description="dirigido a", ordering="categoria")
    def dirigido_a(self, obj):
        return obj.get_categoria_display() or "Todas las categorías"

    def save_model(self, request, obj, form, change):
        # El autor es quien lo publicó; no se elige a mano.
        if not change:
            obj.autor = request.user
        super().save_model(request, obj, form, change)
