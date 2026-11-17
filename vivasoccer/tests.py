"""Pruebas de la configuración de Sentry (vivasoccer/sentry.py).

Cada prueba importa settings en otro proceso, porque sentry_sdk.init es global:
activarlo aquí dejaría a Sentry encendido para el resto de las pruebas.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

from django.test import SimpleTestCase

from .sentry import quitar_datos_personales

RAIZ = Path(__file__).resolve().parent.parent
DSN_FALSO = "https://clave@o0.ingest.sentry.io/0"  # nunca se le envía nada

# Corre una petición que truena dentro de Django con datos personales por todos
# lados, y en lugar de mandar el evento a Sentry lo imprime como JSON.
SCRIPT_PETICION_CON_ERROR = """
import io, json, sentry_sdk
from sentry_sdk.transport import Transport
from django.core.wsgi import get_wsgi_application

# La aplicación WSGI real, la misma que corre gunicorn: así Sentry ve la
# petición completa. (El Client de pruebas de Django no pasa por aquí.)
aplicacion = get_wsgi_application()

class Grabadora(Transport):
    eventos = []
    def capture_envelope(self, envelope):
        for item in envelope.items:
            if item.type == "event":
                self.eventos.append(item.payload.json)

cliente = sentry_sdk.get_client()
assert cliente.is_active(), "Sentry no se activó con SENTRY_DSN"
cliente.transport = Grabadora(cliente.options)

import django.contrib.auth.forms as formularios

def autenticar_que_truena(request=None, **credenciales):
    telefono_del_tutor = "55 1234 5678"  # variable local con un dato personal
    raise RuntimeError("falla de prueba")

formularios.authenticate = autenticar_que_truena

TOKEN = "a" * 32  # token CSRF válido: el mismo en la cookie y en el formulario
cuerpo = f"username=Diego+Salinas+Ruiz&password=secreta-de-prueba&csrfmiddlewaretoken={TOKEN}".encode()
entorno_wsgi = {
    "REQUEST_METHOD": "POST", "PATH_INFO": "/acceso/", "QUERY_STRING": "q=Diego+Salinas",
    "SERVER_NAME": "localhost", "SERVER_PORT": "80", "HTTP_HOST": "localhost",
    "wsgi.url_scheme": "http", "wsgi.input": io.BytesIO(cuerpo), "wsgi.errors": io.StringIO(),
    "CONTENT_TYPE": "application/x-www-form-urlencoded", "CONTENT_LENGTH": str(len(cuerpo)),
    "HTTP_COOKIE": f"csrftoken={TOKEN}; sessionid=cookie-de-prueba",
    "HTTP_X_ALUMNO": "Diego Salinas Ruiz", "REMOTE_ADDR": "10.9.8.7",
}
estado = []
aplicacion(entorno_wsgi, lambda s, h, *a: estado.append(s))
sentry_sdk.flush()
print(json.dumps({"estado": estado[0], "eventos": Grabadora.eventos}))
"""


def correr(codigo, **variables):
    entorno = {
        k: v for k, v in os.environ.items()
        if k not in ("SENTRY_DSN", "DATABASE_URL", "RAILWAY_ENVIRONMENT_NAME")
    }
    entorno.update(DJANGO_SETTINGS_MODULE="vivasoccer.settings", DJANGO_DEBUG="1", **variables)
    return subprocess.run(
        [sys.executable, "-c", codigo], cwd=RAIZ, env=entorno, capture_output=True, text=True
    )


class SentryActivacionTests(SimpleTestCase):
    CODIGO = (
        "import json, sentry_sdk, vivasoccer.settings; "
        "c = sentry_sdk.get_client(); o = c.options; "
        "print(json.dumps({'activo': c.is_active(), 'pii': o['send_default_pii'], "
        "'locales': o['include_local_variables'], 'cuerpo': o['max_request_body_size'], "
        "'trazas': o['traces_sample_rate'], 'entorno': o['environment'], "
        "'before_send': getattr(o['before_send'], '__name__', None)}))"
    )

    def test_sin_sentry_dsn_no_se_activa(self):
        proceso = correr(self.CODIGO)
        self.assertEqual(proceso.returncode, 0, proceso.stderr)
        self.assertFalse(json.loads(proceso.stdout)["activo"])

    def test_con_sentry_dsn_se_activa_con_minimizacion_de_datos(self):
        proceso = correr(self.CODIGO, SENTRY_DSN=DSN_FALSO)
        self.assertEqual(proceso.returncode, 0, proceso.stderr)
        self.assertEqual(
            json.loads(proceso.stdout),
            {
                "activo": True,
                "pii": False,
                "locales": False,
                "cuerpo": "never",
                "trazas": 0,
                "entorno": "desarrollo",
                "before_send": "quitar_datos_personales",
            },
        )


class SentrySinDatosPersonalesTests(SimpleTestCase):
    def test_un_error_real_no_manda_datos_del_alumno(self):
        proceso = correr(SCRIPT_PETICION_CON_ERROR, SENTRY_DSN=DSN_FALSO)
        self.assertEqual(proceso.returncode, 0, proceso.stderr)
        salida = json.loads(proceso.stdout.strip().splitlines()[-1])
        self.assertTrue(salida["estado"].startswith("500"), salida["estado"])
        self.assertEqual(len(salida["eventos"]), 1, "el error debió generar un evento")
        evento = salida["eventos"][0]

        # Lo útil sí llega: el error, y la ruta sin parámetros.
        self.assertEqual(evento["exception"]["values"][-1]["value"], "falla de prueba")
        self.assertEqual(evento["request"]["url"], "http://localhost/acceso/")

        # Ningún dato personal, en ninguna parte del evento.
        texto = json.dumps(evento)
        datos = ("Diego", "Salinas", "55 1234 5678", "secreta-de-prueba", "cookie-de-prueba", "10.9.8.7")
        for dato in datos:
            self.assertNotIn(dato, texto)
        self.assertNotIn("user", evento)

    def test_quitar_datos_personales_limpia_la_peticion(self):
        evento = {
            "request": {
                "url": "https://vivasoccer.mx/padron/?q=Diego",
                "method": "GET",
                "query_string": "q=Diego",
                "headers": {"Referer": "https://vivasoccer.mx/padron/?q=Diego"},
                "cookies": {"sessionid": "x"},
                "data": {"nombre": "Diego"},
                "env": {"REMOTE_ADDR": "10.0.0.1"},
            },
            "user": {"id": 3, "ip_address": "10.0.0.1"},
        }
        self.assertEqual(
            quitar_datos_personales(evento, hint={}),
            {"request": {"url": "https://vivasoccer.mx/padron/", "method": "GET"}},
        )

    def test_un_evento_sin_peticion_pasa_igual(self):
        evento = {"message": "tarea fallida"}
        self.assertEqual(quitar_datos_personales(evento, hint={}), {"message": "tarea fallida"})
