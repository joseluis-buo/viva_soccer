"""Monitoreo de errores con Sentry, sin datos personales de los alumnos.

Solo se activa si existe la variable SENTRY_DSN (la pone Railway). En
desarrollo, en las pruebas y en el CI no existe, así que no se manda nada.

Los alumnos son menores de edad: a Sentry solo le llega el tipo de error, el
archivo y la línea, la ruta sin parámetros y la hora. Nunca nombres, teléfonos
ni observaciones. Por eso, además de las opciones de `configurar_sentry`,
quitar_datos_personales limpia cada evento antes de que salga del servidor.
"""

import sentry_sdk


def quitar_datos_personales(evento, hint):
    """Se ejecuta con cada error antes de enviarlo. Devuelve el evento ya limpio.

    - URL sin query string: la búsqueda del padrón lleva nombres (?q=Diego).
    - Sin encabezados, cookies ni cuerpo de la petición.
    - Sin datos del usuario que hizo la petición.
    """
    peticion = evento.get("request")
    if peticion:
        if "url" in peticion:
            peticion["url"] = peticion["url"].split("?", 1)[0]
        for campo in ("query_string", "headers", "cookies", "data", "env"):
            peticion.pop(campo, None)
    evento.pop("user", None)
    return evento


def configurar_sentry(dsn, entorno):
    sentry_sdk.init(
        dsn=dsn,
        environment=entorno,
        # Sin IP, cookies ni usuario.
        send_default_pii=False,
        # Las variables locales de un traceback pueden traer un alumno completo.
        include_local_variables=False,
        # El cuerpo de un POST trae observaciones, nombres y teléfonos.
        max_request_body_size="never",
        before_send=quitar_datos_personales,
        # Solo errores; sin monitoreo de rendimiento.
        traces_sample_rate=0,
    )
