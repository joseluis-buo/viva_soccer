"""Prueba de punta a punta (E2E) con Playwright: el entrenador captura en el celular.

Levanta un servidor local con una base SQLite nueva y los datos de seed_demo,
y maneja un navegador real como lo haría el entrenador en la cancha.
Nunca usa Neon: DATABASE_URL se fija a un archivo SQLite temporal (eso le gana
al .env, porque load_dotenv no pisa variables que ya existen) y además se
comprueba antes de empezar.

    pip install -r requirements-e2e.txt
    playwright install chromium
    python -m unittest discover -s e2e -v

No está en un paquete (sin __init__.py), así que `manage.py test` no la corre.
"""

import os
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

RAIZ = Path(__file__).resolve().parent.parent
ALUMNO = "Renata Ocampo Vela"  # del seed_demo: MINI · Lunes y Miércoles, el primer grupo


def puerto_libre():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def entorno_local(base):
    """Entorno del servidor: DEBUG encendido y SQLite, sin nada de producción."""
    entorno = {
        k: v for k, v in os.environ.items()
        if not k.startswith(("DJANGO_", "RAILWAY_")) and k not in ("DATABASE_URL", "TEST_POSTGRES")
    }
    entorno.update(DJANGO_DEBUG="1", DATABASE_URL=f"sqlite:///{base}")
    return entorno


def manage(entorno, *args):
    return subprocess.run(
        [sys.executable, "manage.py", *args],
        cwd=RAIZ, env=entorno, check=True, capture_output=True, text=True,
    ).stdout


class CapturaE2ETests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.carpeta = tempfile.TemporaryDirectory()
        cls.base = Path(cls.carpeta.name) / "e2e.sqlite3"
        entorno = entorno_local(cls.base)

        # Seguro: si por cualquier motivo Django no usara SQLite, no seguir.
        salida = manage(entorno, "shell", "-c",
                        "from django.db import connection; print(connection.vendor)")
        motor = salida.strip().splitlines()[-1]  # el shell de Django imprime un aviso antes
        if motor != "sqlite":
            raise RuntimeError(f"La prueba E2E solo corre con SQLite, no con {motor!r}.")

        manage(entorno, "migrate", "--noinput")
        manage(entorno, "seed_demo")

        cls.url = f"http://127.0.0.1:{puerto_libre()}"
        cls.servidor = subprocess.Popen(
            [sys.executable, "manage.py", "runserver", "--noreload", cls.url.removeprefix("http://")],
            cwd=RAIZ, env=entorno, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        cls.esperar_servidor()

        cls.playwright = sync_playwright().start()
        cls.navegador = cls.playwright.chromium.launch()

    @classmethod
    def esperar_servidor(cls, segundos=30):
        limite = time.monotonic() + segundos
        while time.monotonic() < limite:
            try:
                urllib.request.urlopen(f"{cls.url}/acceso/", timeout=1)
                return
            except OSError:
                time.sleep(0.3)
        raise RuntimeError("El servidor local no arrancó.")

    @classmethod
    def tearDownClass(cls):
        cls.navegador.close()
        cls.playwright.stop()
        cls.servidor.terminate()
        cls.servidor.wait(timeout=10)
        cls.carpeta.cleanup()

    def setUp(self):
        # Pantalla de celular: la captura es mobile-first y se usa en la cancha.
        self.contexto = self.navegador.new_context(
            viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True
        )
        self.pagina = self.contexto.new_page()

    def tearDown(self):
        self.contexto.close()

    def tarjeta_del_alumno(self):
        """La tarjeta de captura de ALUMNO: la que tiene su nombre y los campos de calificación."""
        return self.pagina.locator("div.rounded-xl").filter(has_text=ALUMNO).filter(
            has=self.pagina.locator("input[type=number]")
        )

    def evaluacion_guardada(self, fecha):
        """Lee la base directamente: lo que ve la pantalla podría venir de otro lado."""
        with sqlite3.connect(self.base) as conexion:
            return conexion.execute(
                """SELECT e.pase, e.recepcion, e.tiro, e.observaciones, u.username
                   FROM escuela_evaluacion e
                   JOIN escuela_alumno a ON a.id = e.alumno_id
                   JOIN auth_user u ON u.id = e.capturada_por_id
                   WHERE a.nombre = ? AND e.fecha = ?""",
                (ALUMNO, fecha),
            ).fetchall()

    def test_entrenador_captura_y_se_guarda(self):
        pagina = self.pagina
        pagina.goto(f"{self.url}/acceso/")
        pagina.fill("input[name=username]", "entrenador")
        pagina.fill("input[name=password]", "entrenador")
        pagina.click("button:has-text('ENTRAR')")

        # El entrenador cae directo en la captura, con la fecha de hoy.
        expect(pagina).to_have_url(f"{self.url}/captura/")
        fecha = pagina.input_value("input[name=fecha]")
        self.assertEqual(self.evaluacion_guardada(fecha), [], "ya había una evaluación de hoy")

        tarjeta = self.tarjeta_del_alumno()
        tarjeta.get_by_label("PASE").fill("8")
        tarjeta.get_by_label("RECEP.").fill("7")
        tarjeta.get_by_label("TIRO").fill("9")
        tarjeta.get_by_label("OBSERVACIONES").fill("Buen control con la izquierda")
        pagina.get_by_role("button", name="GUARDAR").click()

        expect(pagina.get_by_text("Se guardaron 1 evaluaciones.")).to_be_visible()
        # Después de recargar, la tarjeta conserva lo capturado.
        tarjeta = self.tarjeta_del_alumno()
        expect(tarjeta.get_by_label("PASE")).to_have_value("8")
        expect(tarjeta.get_by_label("TIRO")).to_have_value("9")

        self.assertEqual(
            self.evaluacion_guardada(fecha),
            [(8, 7, 9, "Buen control con la izquierda", "entrenador")],
        )


if __name__ == "__main__":
    unittest.main()
