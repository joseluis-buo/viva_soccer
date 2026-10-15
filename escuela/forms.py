from django import forms

from .models import Alumno, Evaluacion, Tutor, validar_telefono

# Clases Tailwind compartidas por los campos del formulario (tokens del diseño).
CAMPO = (
    "h-11 w-full rounded-lg border border-border bg-bg-base px-3 text-[15px] "
    "text-text-primary outline-none focus:border-accent "
    "focus:ring-2 focus:ring-accent/20"
)


class AlumnoForm(forms.ModelForm):
    """Alta y edición de alumno. El tutor se elige de la lista o se da de alta
    en el mismo formulario (caso común: llega un alumno nuevo con su mamá)."""

    tutor = forms.ModelChoiceField(
        queryset=Tutor.objects.all(),
        required=False,
        empty_label="— Tutor nuevo —",
        widget=forms.Select(attrs={"class": CAMPO}),
    )
    tutor_nombre = forms.CharField(
        max_length=120,
        required=False,
        widget=forms.TextInput(attrs={"class": CAMPO, "placeholder": "Nombre del tutor"}),
    )
    tutor_telefono = forms.CharField(
        max_length=14,
        required=False,
        validators=[validar_telefono],
        widget=forms.TextInput(attrs={"class": CAMPO, "placeholder": "55 1234 5678"}),
    )

    class Meta:
        model = Alumno
        fields = ["nombre", "categoria", "horario", "fecha_nacimiento", "tutor"]
        widgets = {
            "nombre": forms.TextInput(attrs={"class": CAMPO, "placeholder": "Nombre completo"}),
            "categoria": forms.Select(attrs={"class": CAMPO}),
            "horario": forms.Select(attrs={"class": CAMPO}),
            "fecha_nacimiento": forms.DateInput(
                attrs={"class": CAMPO, "type": "date"}, format="%Y-%m-%d"
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["fecha_nacimiento"].input_formats = ["%Y-%m-%d"]

    def clean(self):
        datos = super().clean()
        if datos.get("tutor"):
            return datos
        if not datos.get("tutor_nombre"):
            self.add_error("tutor_nombre", "Elige un tutor de la lista o escribe el nombre del nuevo.")
        if not datos.get("tutor_telefono") and "tutor_telefono" not in self.errors:
            self.add_error("tutor_telefono", "El tutor nuevo necesita teléfono de contacto.")
        return datos

    def save(self, commit=True):
        if not self.cleaned_data.get("tutor"):
            self.instance.tutor = Tutor.objects.create(
                nombre=self.cleaned_data["tutor_nombre"],
                telefono=self.cleaned_data["tutor_telefono"],
            )
        return super().save(commit)


class TutorForm(forms.ModelForm):
    class Meta:
        model = Tutor
        fields = ["nombre", "telefono", "correo"]
        widgets = {
            "nombre": forms.TextInput(attrs={"class": CAMPO, "placeholder": "Nombre completo"}),
            "telefono": forms.TextInput(attrs={"class": CAMPO, "placeholder": "55 1234 5678"}),
            "correo": forms.EmailInput(attrs={"class": CAMPO, "placeholder": "Opcional"}),
        }


class EvaluacionForm(forms.ModelForm):
    """Corrección o registro puntual de una evaluación desde la ficha del alumno."""

    class Meta:
        model = Evaluacion
        fields = ["fecha", "pase", "recepcion", "tiro"]
        widgets = {
            "fecha": forms.DateInput(attrs={"class": CAMPO, "type": "date"}, format="%Y-%m-%d"),
            "pase": forms.NumberInput(attrs={"class": "nota-input", "min": 1, "max": 10}),
            "recepcion": forms.NumberInput(attrs={"class": "nota-input", "min": 1, "max": 10}),
            "tiro": forms.NumberInput(attrs={"class": "nota-input", "min": 1, "max": 10}),
        }

    def __init__(self, *args, alumno, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance.alumno = alumno
        self.fields["fecha"].input_formats = ["%Y-%m-%d"]

    def clean_fecha(self):
        # La restricción única (alumno, fecha) no la revisa el ModelForm porque
        # 'alumno' no es campo del formulario; la revisamos aquí.
        fecha = self.cleaned_data["fecha"]
        repetida = Evaluacion.objects.filter(
            alumno=self.instance.alumno, fecha=fecha
        ).exclude(pk=self.instance.pk)
        if repetida.exists():
            raise forms.ValidationError("Este alumno ya tiene una evaluación en esa fecha.")
        return fecha
