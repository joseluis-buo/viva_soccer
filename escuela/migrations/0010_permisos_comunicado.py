from django.db import migrations

# La secretaria publica los comunicados de la app desde el admin, igual que
# asigna grupos a los entrenadores.
PERMISOS_SECRETARIA_NUEVOS = [
    f"{accion}_comunicado" for accion in ("add", "change", "delete", "view")
]


def dar_permisos(apps, schema_editor):
    from django.apps import apps as global_apps
    from django.contrib.auth.management import create_permissions

    # Igual que en 0002, 0004, 0006 y 0008: los permisos del modelo nuevo aún no existen.
    create_permissions(global_apps.get_app_config("escuela"), apps=apps, verbosity=0)

    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")

    administrador, _ = Group.objects.get_or_create(name="administrador")
    administrador.permissions.set(
        Permission.objects.filter(content_type__app_label="escuela")
    )

    secretaria, _ = Group.objects.get_or_create(name="secretaria")
    secretaria.permissions.add(
        *Permission.objects.filter(
            content_type__app_label="escuela", codename__in=PERMISOS_SECRETARIA_NUEVOS
        )
    )


def quitar_permisos(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    permisos = Permission.objects.filter(codename__in=PERMISOS_SECRETARIA_NUEVOS)
    for grupo in Group.objects.filter(name__in=["administrador", "secretaria"]):
        grupo.permissions.remove(*permisos)


class Migration(migrations.Migration):
    dependencies = [
        ("escuela", "0009_evaluacion_observaciones"),
    ]

    operations = [
        migrations.RunPython(dar_permisos, quitar_permisos),
    ]
