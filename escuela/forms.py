from django import forms

from .models import Alumno

# Clases Tailwind compartidas por los campos del formulario (tokens del diseño).
CAMPO = (
    "h-11 w-full rounded-lg border border-border bg-bg-base px-3 text-[15px] "
    "text-text-primary outline-none focus:border-accent "
    "focus:ring-2 focus:ring-accent/20"
)


class AlumnoForm(forms.ModelForm):
    class Meta:
        model = Alumno
        fields = [
            "nombre",
            "categoria",
            "horario",
            "fecha_nacimiento",
            "tutor",
            "telefono",
            "activo",
        ]
        widgets = {
            "nombre": forms.TextInput(attrs={"class": CAMPO, "placeholder": "Nombre completo"}),
            "categoria": forms.Select(attrs={"class": CAMPO}),
            "horario": forms.Select(attrs={"class": CAMPO}),
            "fecha_nacimiento": forms.DateInput(
                attrs={"class": CAMPO, "type": "date"}, format="%Y-%m-%d"
            ),
            "tutor": forms.TextInput(attrs={"class": CAMPO, "placeholder": "Nombre del tutor"}),
            "telefono": forms.TextInput(attrs={"class": CAMPO, "placeholder": "55 1234 5678"}),
            "activo": forms.CheckboxInput(
                attrs={"class": "h-4 w-4 rounded border-border bg-bg-base accent-accent"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["fecha_nacimiento"].input_formats = ["%Y-%m-%d"]
