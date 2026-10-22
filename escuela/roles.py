"""Roles del sistema. Se apoyan en los grupos creados en las migraciones 0002, 0004 y 0006."""

from functools import wraps

from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.shortcuts import redirect

from .models import GRUPOS, Alumno


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


def es_tutor(user):
    """Padre con cuenta en la app móvil: miembro del grupo 'tutor'.

    A diferencia de los otros roles, el administrador no lo hereda: ser tutor
    no es un permiso más, es ser el papá de alumnos concretos (ver Tutor.usuario).
    """
    return user.is_authenticated and user.groups.filter(name="tutor").exists()


def grupos_de(user):
    """Claves de GRUPOS que le tocan: todas al administrador, las asignadas al entrenador."""
    if es_administrador(user):
        return [clave for clave, _ in GRUPOS]
    if not es_entrenador(user):
        return []
    asignados = {a.grupo for a in user.asignaciones.all()}
    return [clave for clave, _ in GRUPOS if clave in asignados]


def alumnos_del_entrenador(user):
    """Alumnos activos que hoy están en alguno de sus grupos.

    Toda la API del entrenador parte de aquí: lo que no sale en esta consulta,
    para él no existe.
    """
    filtro = Q(pk__in=[])  # sin grupos, ningún alumno
    for clave in grupos_de(user):
        categoria, horario = clave.split("-")
        filtro |= Q(categoria=categoria, horario=horario)
    return Alumno.objects.filter(filtro, activo=True)


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
solo_tutor = _exigir(es_tutor)
