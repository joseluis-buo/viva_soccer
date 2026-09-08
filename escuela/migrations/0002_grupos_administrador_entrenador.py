from django.db import migrations

# administrador: padrón completo (todo el CRUD de la escuela).
# entrenador: solo captura (ve alumnos, registra y corrige evaluaciones).
PERMISOS_ENTRENADOR = [
    ("view", "alumno"),
    ("add", "evaluacion"),
    ("change", "evaluacion"),
    ("view", "evaluacion"),
]


def crear_grupos(apps, schema_editor):
    from django.apps import apps as global_apps
    from django.contrib.auth.management import create_permissions

    # Los permisos de un modelo se crean en la señal post_migrate, que aún no
    # corrió cuando se ejecuta esta migración de datos. Los forzamos aquí.
    create_permissions(global_apps.get_app_config("escuela"), apps=apps, verbosity=0)

    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")

    administrador, _ = Group.objects.get_or_create(name="administrador")
    administrador.permissions.set(
        Permission.objects.filter(content_type__app_label="escuela")
    )

    entrenador, _ = Group.objects.get_or_create(name="entrenador")
    entrenador.permissions.set(
        Permission.objects.filter(
            content_type__app_label="escuela",
            codename__in=[f"{accion}_{modelo}" for accion, modelo in PERMISOS_ENTRENADOR],
        )
    )


def borrar_grupos(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.filter(name__in=["administrador", "entrenador"]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("escuela", "0001_initial"),
        ("auth", "0012_alter_user_first_name_max_length"),
        ("contenttypes", "0002_remove_content_type_name"),
    ]

    operations = [
        migrations.RunPython(crear_grupos, borrar_grupos),
    ]
