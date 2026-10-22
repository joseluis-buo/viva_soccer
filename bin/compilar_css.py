"""Compila el CSS de Tailwind: static/src/input.css -> static/css/tailwind.css.

El binario standalone de Tailwind no se versiona (pesa ~40 MB). Si no está en
bin/tailwindcss, este script descarga la versión fijada abajo y luego compila.
Lo usa el build de Railway y sirve igual en local:

    python bin/compilar_css.py
"""

import platform
import stat
import subprocess
import sys
import urllib.request
from pathlib import Path

VERSION = "v3.4.17"  # La misma con la que se hizo el diseño; no subir sin probar.
RAIZ = Path(__file__).resolve().parent.parent
BINARIO = RAIZ / "bin" / ("tailwindcss.exe" if sys.platform == "win32" else "tailwindcss")


def nombre_del_binario():
    """Nombre del archivo en los releases de Tailwind para este sistema."""
    sistema = {"linux": "linux", "darwin": "macos", "win32": "windows"}[sys.platform]
    arquitectura = "arm64" if platform.machine().lower() in ("arm64", "aarch64") else "x64"
    extension = ".exe" if sistema == "windows" else ""
    return f"tailwindcss-{sistema}-{arquitectura}{extension}"


def descargar_binario():
    url = (
        "https://github.com/tailwindlabs/tailwindcss/releases/download/"
        f"{VERSION}/{nombre_del_binario()}"
    )
    print(f"Descargando {url}")
    urllib.request.urlretrieve(url, BINARIO)
    BINARIO.chmod(BINARIO.stat().st_mode | stat.S_IEXEC)


def main():
    if not BINARIO.exists():
        descargar_binario()
    subprocess.run(
        [
            str(BINARIO),
            "-i", str(RAIZ / "static" / "src" / "input.css"),
            "-o", str(RAIZ / "static" / "css" / "tailwind.css"),
            "--minify",
        ],
        cwd=RAIZ,  # tailwind.config.js busca las plantillas con rutas relativas
        check=True,
    )


if __name__ == "__main__":
    main()
