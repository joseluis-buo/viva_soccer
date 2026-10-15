"""Roles del sistema. Se apoyan en los grupos creados en las migraciones 0002 y 0004."""

from functools import wraps

from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect


def es_administrador(user):
    """Padrón completo: superusuario o miembro del grupo 'administrador'."""
    return user.is_authenticated and (
        user.is_superuser or user.groups.filter(name="administrador").exists()
    )


def es_secretaria(user):
    """Padrón, tutores, corrección de evaluaciones y boletas (los administradores también pueden)."""
    return user.is_authenticated and (
        es_administrador(user) or user.groups.filter(name="secretaria").exists()
    )


def es_entrenador(user):
    """Captura: miembro del grupo 'entrenador' (los administradores también pueden)."""
    return user.is_authenticated and (
        es_administrador(user) or user.groups.filter(name="entrenador").exists()
    )


def _exigir(prueba):
    """Anónimo → login. Con sesión pero sin el rol → a su pantalla de inicio.

    No se manda al login a quien ya tiene sesión: el login lo regresaría a la
    misma URL y el navegador entraría en un ciclo de redirecciones.
    """

    def decorador(vista):
        @wraps(vista)
        def envoltura(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect_to_login(request.get_full_path())
            if prueba(request.user):
                return vista(request, *args, **kwargs)
            if es_secretaria(request.user) or es_entrenador(request.user):
                return redirect("raiz")
            raise PermissionDenied

        return envoltura

    return decorador


# Decoradores listos para usar en las vistas.
solo_administrador = _exigir(es_administrador)
solo_secretaria = _exigir(es_secretaria)
solo_entrenador = _exigir(es_entrenador)
