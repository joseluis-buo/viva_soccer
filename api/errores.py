"""Errores de la API. La app móvil siempre espera {"detail": "..."}."""

from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.views import exception_handler


class Conflicto(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "La operación choca con el estado actual."


class Vencido(APIException):
    """410 Gone: el recurso existió pero ya no sirve (p. ej. un código vencido)."""

    status_code = status.HTTP_410_GONE
    default_detail = "El recurso ya no está disponible."


def manejar_error(exc, context):
    """Usa el manejador de DRF y aplana los errores de validación a un solo "detail".

    DRF responde la validación como {"campo": ["mensaje"]}; aquí se vuelve
    {"detail": "campo: mensaje"} para que el cliente lea siempre la misma llave.
    """
    respuesta = exception_handler(exc, context)
    if respuesta is not None and not (
        isinstance(respuesta.data, dict) and "detail" in respuesta.data
    ):
        respuesta.data = {"detail": " ".join(_mensajes(respuesta.data))}
    return respuesta


def _mensajes(datos, campo=None):
    if isinstance(datos, dict):
        for nombre, valor in datos.items():
            yield from _mensajes(valor, None if nombre == "non_field_errors" else nombre)
    elif isinstance(datos, list):
        for valor in datos:
            yield from _mensajes(valor, campo)
    else:
        yield f"{campo}: {datos}" if campo else str(datos)
