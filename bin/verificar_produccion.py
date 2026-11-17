"""Revisa que producción sirva la web completa después de un despliegue.

    python bin/verificar_produccion.py https://vivasoccer-production.up.railway.app

Solo hace peticiones GET; no inicia sesión ni escribe nada. Revisa:
1. /acceso/ responde 200 y trae su región <main>;
2. el CSS de Tailwind con hash que enlaza esa página responde 200 como text/css;
3. el favicon con hash responde 200 como image/svg+xml.

Existe porque el 16 de noviembre de 2026 un despliegue terminó como "success"
sin haber corrido collectstatic: /static/ daba 404 y todas las páginas HTML
500, y ni el CI ni el estado del despliegue lo mostraban.

Sale con código 1 y un mensaje claro si algo falla, para que el job quede en
rojo. Reintenta unas veces, porque justo al terminar el despliegue Railway
puede seguir cambiando de versión.
"""

import re
import sys
import time
import urllib.error
import urllib.request

INTENTOS = 5
ESPERA_SEGUNDOS = 15


def pedir(url):
    """(código, content-type, cuerpo) de un GET; los errores HTTP también se devuelven."""
    peticion = urllib.request.Request(url, headers={"User-Agent": "verificar-produccion"})
    try:
        with urllib.request.urlopen(peticion, timeout=20) as r:
            return r.status, r.headers.get("Content-Type", ""), r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get("Content-Type", ""), ""


def revisar(base, pedir=pedir):
    """Lista de problemas encontrados; vacía si producción está bien."""
    base = base.rstrip("/")
    codigo, _, html = pedir(base + "/acceso/")
    if codigo != 200:
        return [f"/acceso/ respondió {codigo} (se esperaba 200)."]
    problemas = []
    if "<main" not in html:
        problemas.append("/acceso/ no trae su región <main>.")

    esperados = [
        ("CSS", r'href="(/static/css/tailwind\.[0-9a-f]+\.css)"', "text/css"),
        ("favicon", r'href="(/static/img/favicon\.[0-9a-f]+\.svg)"', "image/svg+xml"),
    ]
    for nombre, patron, tipo in esperados:
        m = re.search(patron, html)
        if not m:
            # Sin hash en el nombre: collectstatic no corrió o no hay manifiesto.
            problemas.append(f"/acceso/ no enlaza el {nombre} con hash (¿corrió collectstatic?).")
            continue
        codigo, content_type, _ = pedir(base + m.group(1))
        if codigo != 200 or not content_type.startswith(tipo):
            problemas.append(f"{m.group(1)} respondió {codigo} {content_type!r} (se esperaba 200 {tipo}).")
    return problemas


def main():
    if len(sys.argv) != 2:
        sys.exit("Uso: python bin/verificar_produccion.py https://dominio")
    base = sys.argv[1]
    for intento in range(1, INTENTOS + 1):
        problemas = revisar(base)
        if not problemas:
            print(f"Producción bien: {base}/acceso/, CSS y favicon responden 200.")
            return
        print(f"Intento {intento}/{INTENTOS}:", *problemas, sep="\n  ")
        if intento < INTENTOS:
            time.sleep(ESPERA_SEGUNDOS)
    sys.exit("Producción NO está bien después del despliegue (ver arriba).")


if __name__ == "__main__":
    main()
