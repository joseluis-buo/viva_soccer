from django.db import migrations

# secretaria: padrón (alta, baja y edición de alumnos), tutores, corrección de
# evaluaciones y boletas. No ve el panel ni la captura de cancha.
PERMISOS_SECRETARIA = [
    (accion, modelo)
    for modelo in ("alumno", "tutor", "evaluacion")
    for accion in ("add", "change", "delete", "view")
]


def crear_grupo(apps, schema_editor):
    from django.apps import apps as global_apps
    from django.contrib.auth.management import create_permissions

    # Igual que en 0002: los permisos del modelo nuevo (Tutor) aún no existen.
    create_permissions(global_apps.get_app_config("escuela"), apps=apps, verbosity=0)

    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")

    # El administrador sigue teniendo todo, incluido Tutor.
    administrador, _ = Group.objects.get_or_create(name="administrador")
    administrador.permissions.set(
        Permission.objects.filter(content_type__app_label="escuela")
    )

    secretaria, _ = Group.objects.get_or_create(name="secretaria")
    secretaria.permissions.set(
        Permission.objects.filter(
            content_type__app_label="escuela",
            codename__in=[f"{accion}_{modelo}" for accion, modelo in PERMISOS_SECRETARIA],
        )
    )


def borrar_grupo(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.filter(name="secretaria").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("escuela", "0003_tutor"),
    ]

    operations = [
        migrations.RunPython(crear_grupo, borrar_grupo),
    ]
