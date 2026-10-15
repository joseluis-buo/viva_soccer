from django.contrib import admin

from .models import Alumno, Evaluacion, Tutor

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


@admin.register(Tutor)
class TutorAdmin(admin.ModelAdmin):
    list_display = ["nombre", "telefono", "correo"]
    search_fields = ["nombre", "telefono", "correo"]
    inlines = [AlumnoInline]


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
