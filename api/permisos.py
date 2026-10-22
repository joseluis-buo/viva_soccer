"""Permisos de la API. Lo que cada quien puede ver se decide aquí, nunca en la app."""

from rest_framework.permissions import BasePermission

from escuela.roles import es_entrenador, es_tutor


class SoloEntrenador(BasePermission):
    """Entrenadores y administradores. Un tutor recibe 403."""

    message = "Esta sección es solo para entrenadores."

    def has_permission(self, request, view):
        return es_entrenador(request.user)


class SoloTutor(BasePermission):
    """Padres con cuenta en la app. El administrador no lo hereda: recibe 403."""

    message = "Esta sección es solo para padres de familia."

    def has_permission(self, request, view):
        return es_tutor(request.user)
