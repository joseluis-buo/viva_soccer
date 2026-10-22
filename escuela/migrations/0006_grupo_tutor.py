from django.db import migrations

# La secretaria ya administra a los tutores; ahora también sus códigos de
# activación, para entregarle al padre el acceso a la app.
PERMISOS_SECRETARIA_NUEVOS = [
    f"{accion}_codigoactivacion" for accion in ("add", "change", "delete", "view")
]


def crear_grupo(apps, schema_editor):
    from django.apps import apps as global_apps
    from django.contrib.auth.management import create_permissions

    # Igual que en 0002 y 0004: los permisos de los modelos nuevos aún no existen.
    create_permissions(global_apps.get_app_config("escuela"), apps=apps, verbosity=0)

    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")

    # El administrador sigue teniendo todo, incluidos los modelos de la app móvil.
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

    # tutor: sin permisos de modelo. Solo usa la API, que filtra por sus hijos.
    Group.objects.get_or_create(name="tutor")


def borrar_grupo(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    Group.objects.filter(name="tutor").delete()
    for secretaria in Group.objects.filter(name="secretaria"):
        secretaria.permissions.remove(
            *Permission.objects.filter(codename__in=PERMISOS_SECRETARIA_NUEVOS)
        )


class Migration(migrations.Migration):
    dependencies = [
        ("escuela", "0005_app_movil"),
    ]

    operations = [
        migrations.RunPython(crear_grupo, borrar_grupo),
    ]
