import django.core.validators
import django.db.models.deletion
from django.db import migrations, models

# El tutor deja de ser texto en el alumno y pasa a ser su propio registro.
# Los alumnos con el mismo nombre de tutor y teléfono comparten tutor (hermanos).


def separar_tutores(apps, schema_editor):
    Alumno = apps.get_model("escuela", "Alumno")
    Tutor = apps.get_model("escuela", "Tutor")
    for alumno in Alumno.objects.all():
        tutor, _ = Tutor.objects.get_or_create(
            nombre=alumno.tutor.strip(), telefono=alumno.telefono
        )
        alumno.tutor_nuevo = tutor
        alumno.save(update_fields=["tutor_nuevo"])


def juntar_tutores(apps, schema_editor):
    Alumno = apps.get_model("escuela", "Alumno")
    for alumno in Alumno.objects.select_related("tutor_nuevo"):
        alumno.tutor = alumno.tutor_nuevo.nombre
        alumno.telefono = alumno.tutor_nuevo.telefono
        alumno.save(update_fields=["tutor", "telefono"])


class Migration(migrations.Migration):
    dependencies = [
        ("escuela", "0002_grupos_administrador_entrenador"),
    ]

    operations = [
        migrations.CreateModel(
            name="Tutor",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("nombre", models.CharField(max_length=120, verbose_name="nombre completo")),
                ("telefono", models.CharField(help_text="Formato: 55 1234 5678", max_length=14, validators=[django.core.validators.RegexValidator(message="Ingresa 10 dígitos con el formato 55 1234 5678.", regex="^\\d{2} \\d{4} \\d{4}$")], verbose_name="teléfono de contacto")),
                ("correo", models.EmailField(blank=True, max_length=254, verbose_name="correo electrónico")),
            ],
            options={
                "verbose_name": "tutor",
                "verbose_name_plural": "tutores",
                "ordering": ["nombre"],
            },
        ),
        migrations.AddField(
            model_name="alumno",
            name="tutor_nuevo",
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, to="escuela.tutor"),
        ),
        migrations.RunPython(separar_tutores, juntar_tutores),
        # Default temporal: al revertir, las columnas vuelven a crearse con filas existentes.
        migrations.AlterField(model_name="alumno", name="tutor", field=models.CharField(default="", max_length=120, verbose_name="tutor")),
        migrations.AlterField(model_name="alumno", name="telefono", field=models.CharField(default="", max_length=14, verbose_name="teléfono de contacto")),
        migrations.RemoveField(model_name="alumno", name="tutor"),
        migrations.RemoveField(model_name="alumno", name="telefono"),
        migrations.RenameField(model_name="alumno", old_name="tutor_nuevo", new_name="tutor"),
        migrations.AlterField(
            model_name="alumno",
            name="tutor",
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="alumnos", to="escuela.tutor", verbose_name="tutor"),
        ),
    ]
