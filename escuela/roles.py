"""Roles del sistema. Se apoyan en los grupos creados en la migración 0002."""

from django.contrib.auth.decorators import user_passes_test


def es_administrador(user):
    """Padrón completo: superusuario o miembro del grupo 'administrador'."""
    return user.is_authenticated and (
        user.is_superuser or user.groups.filter(name="administrador").exists()
    )


def es_entrenador(user):
    """Captura: miembro del grupo 'entrenador' (los administradores también pueden)."""
    return user.is_authenticated and (
        es_administrador(user) or user.groups.filter(name="entrenador").exists()
    )


# Decoradores listos para usar en las vistas.
solo_administrador = user_passes_test(es_administrador)
solo_entrenador = user_passes_test(es_entrenador)
