from .roles import es_administrador, es_entrenador


def roles(request):
    """Expone los roles del usuario a todas las plantillas (nav, permisos de UI)."""
    return {
        "es_administrador": es_administrador(request.user),
        "es_entrenador": es_entrenador(request.user),
    }
