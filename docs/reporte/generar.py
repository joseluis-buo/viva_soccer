"""Genera Reporte_Final_VIVA_SOCCER.pdf a partir de docs/reporte/.

    source .venv/bin/activate
    pip install -r requirements-e2e.txt && playwright install chromium   # una vez
    python docs/reporte/generar.py                 # capturas + figuras + PDF
    python docs/reporte/generar.py --sin-capturas  # solo vuelve a armar el PDF

Pasos:
1. Capturas de pantalla con Playwright contra un runserver local con una base
   SQLite temporal y seed_demo. Nunca usa Neon: fija DATABASE_URL a SQLite (le
   gana al .env) y se detiene si Django no está usando SQLite.
2. Recorta el mapa del sitio y el flujo de captura de la propuesta (PDF).
3. Lee datos reales: pruebas por clase, Lighthouse antes/después, git.
4. Arma reporte.html, lo imprime con Chromium y calcula el índice en dos pasadas
   (busca en qué página cae cada título con pdftotext).
5. Imprime la portada aparte (sin encabezado ni pie) y une todo con pdfunite.

Herramientas: Playwright (requirements-e2e.txt) y poppler-utils (pdftotext,
pdftoppm, pdfunite). No agrega dependencias al proyecto.
"""

import html
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import unicodedata
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parent.parent
CAPTURAS = AQUI / "capturas"
FIGURAS = AQUI / "figuras"
CONSTRUCCION = AQUI / "construccion"   # intermedios (no se versionan)
SALIDA = RAIZ / "Reporte_Final_VIVA_SOCCER.pdf"
PROPUESTA = Path("~/Downloads/Propuesta_Proyecto_Final_VIVA_SOCCER.pdf").expanduser()


# ---------------------------------------------------------------- 1. Capturas

def puerto_libre():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def entorno_local(base):
    entorno = {
        k: v for k, v in os.environ.items()
        if not k.startswith(("DJANGO_", "RAILWAY_", "SENTRY_"))
        and k not in ("DATABASE_URL", "TEST_POSTGRES")
    }
    entorno.update(DJANGO_DEBUG="1", DATABASE_URL=f"sqlite:///{base}")
    return entorno


def manage(entorno, *args):
    return subprocess.run(
        [sys.executable, "manage.py", *args],
        cwd=RAIZ, env=entorno, check=True, capture_output=True, text=True,
    ).stdout


def tomar_capturas():
    CAPTURAS.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory() as carpeta:
        base = Path(carpeta) / "reporte.sqlite3"
        entorno = entorno_local(base)
        motor = manage(entorno, "shell", "-c",
                       "from django.db import connection; print(connection.vendor)")
        if motor.strip().splitlines()[-1] != "sqlite":
            raise RuntimeError("Las capturas solo se toman con SQLite, nunca con Neon.")
        subprocess.run([sys.executable, "bin/compilar_css.py"], cwd=RAIZ, check=True,
                       capture_output=True)
        manage(entorno, "migrate", "--noinput")
        manage(entorno, "seed_demo")

        url = f"http://127.0.0.1:{puerto_libre()}"
        servidor = subprocess.Popen(
            [sys.executable, "manage.py", "runserver", "--noreload", url[7:]],
            cwd=RAIZ, env=entorno, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        try:
            for _ in range(100):
                try:
                    urllib.request.urlopen(url + "/acceso/", timeout=1)
                    break
                except OSError:
                    time.sleep(0.3)
            with sync_playwright() as p:
                # En español: el campo de fecha se muestra dd/mm/aaaa. Chromium sin
                # ventana toma ese formato de LANG, no de --lang ni del contexto.
                navegador = p.chromium.launch(
                    args=["--lang=es-MX"],
                    env={**os.environ, "LANG": "es_MX.UTF-8", "LANGUAGE": "es_MX:es"},
                )
                capturar_pantallas(navegador, url)
                navegador.close()
        finally:
            servidor.terminate()
            servidor.wait(timeout=10)


def entrar(navegador, url, usuario, viewport):
    contexto = navegador.new_context(viewport=viewport, device_scale_factor=2,
                                     locale="es-MX", timezone_id="America/Tijuana")
    pagina = contexto.new_page()
    pagina.goto(url + "/acceso/")
    pagina.fill("input[name=username]", usuario)
    pagina.fill("input[name=password]", usuario)
    pagina.click("button:has-text('ENTRAR')")
    pagina.wait_for_load_state("networkidle")
    return contexto, pagina


def capturar_pantallas(navegador, url):
    escritorio = {"width": 1366, "height": 768}
    celular = {"width": 390, "height": 844}

    # Login, sin sesión.
    contexto = navegador.new_context(viewport=escritorio, device_scale_factor=2)
    pagina = contexto.new_page()
    pagina.goto(url + "/acceso/")
    pagina.wait_for_load_state("networkidle")
    pagina.screenshot(path=CAPTURAS / "login.png")
    contexto.close()

    # Administrador: panel, padrón, ficha, tutores y boleta.
    contexto, pagina = entrar(navegador, url, "admin", escritorio)
    pagina.goto(url + "/panel/")
    pagina.wait_for_load_state("networkidle")
    pagina.wait_for_timeout(800)  # animación de Chart.js
    pagina.screenshot(path=CAPTURAS / "panel.png", full_page=True)

    pagina.goto(url + "/padron/?grupo=MENOR-MAR_JUE")
    pagina.locator("tbody tr").first.click()
    pagina.wait_for_selector("#panel .tarjeta, #panel h2, #panel p.titulo", timeout=5000)
    pagina.wait_for_timeout(400)
    pagina.screenshot(path=CAPTURAS / "padron.png")

    pagina.goto(url + "/padron/?q=VS-0003")
    pagina.wait_for_load_state("networkidle")
    pagina.screenshot(path=CAPTURAS / "padron_folio.png",
                      clip={"x": 0, "y": 0, "width": 1366, "height": 430})

    pk = pagina.locator("tbody tr a").first.get_attribute("href").strip("/").split("/")[-1]
    pagina.goto(url + f"/padron/{pk}/")
    pagina.wait_for_load_state("networkidle")
    pagina.wait_for_timeout(800)
    pagina.screenshot(path=CAPTURAS / "ficha.png", full_page=True)

    pagina.goto(url + "/tutores/")
    pagina.wait_for_load_state("networkidle")
    pagina.screenshot(path=CAPTURAS / "tutores.png")

    pagina.goto(url + f"/padron/{pk}/boleta/")
    pagina.wait_for_load_state("networkidle")
    pagina.wait_for_timeout(500)
    pagina.screenshot(path=CAPTURAS / "boleta.png", full_page=True)
    contexto.close()

    # Entrenador en el celular: captura una evaluación y guarda.
    contexto, pagina = entrar(navegador, url, "entrenador", celular)
    tarjeta = pagina.locator("div.rounded-xl").filter(
        has=pagina.locator("input[type=number]")).first
    tarjeta.get_by_label("PASE").fill("8")
    tarjeta.get_by_label("RECEP.").fill("7")
    tarjeta.get_by_label("TIRO").fill("9")
    pagina.get_by_role("button", name="GUARDAR").click()
    pagina.wait_for_load_state("networkidle")
    pagina.screenshot(path=CAPTURAS / "captura_movil.png",
                      clip={"x": 0, "y": 0, "width": 390, "height": 1100}, full_page=True)
    contexto.close()


# ------------------------------------------------------- 2. Figuras propuesta

def recortar_propuesta():
    """Mapa del sitio (pág. 9) y flujo de captura (pág. 10) de la propuesta."""
    FIGURAS.mkdir(exist_ok=True)
    if not PROPUESTA.exists():
        print("Aviso: no está la propuesta; se usan las figuras ya recortadas.")
        return
    dpi = 200
    escala = dpi / 72
    recortes = {
        "mapa_sitio": (9, 40, 210, 532, 293),    # página, x, y, ancho, alto (puntos)
        "flujo_captura": (10, 40, 160, 532, 185),
    }
    for nombre, (pag, x, y, w, h) in recortes.items():
        subprocess.run(
            ["pdftoppm", "-f", str(pag), "-l", str(pag), "-r", str(dpi), "-png",
             "-singlefile", "-x", str(int(x * escala)), "-y", str(int(y * escala)),
             "-W", str(int(w * escala)), "-H", str(int(h * escala)),
             str(PROPUESTA), str(FIGURAS / nombre)],
            check=True,
        )


# ------------------------------------------------------------- 3. Datos reales

def pruebas_por_clase():
    filas = []
    for archivo in ("escuela/tests.py", "api/tests.py", "vivasoccer/tests.py"):
        fuente = (RAIZ / archivo).read_text()
        bloques = re.split(r"\n(?=(?:@[^\n]*\n)*class )", fuente)
        for bloque in bloques:
            m = re.search(r"class (\w+)\(", bloque)
            n = len(re.findall(r"\n    def test_", bloque))
            if m and n:
                filas.append((archivo.split("/")[0], m.group(1), n))
    return filas


GRUPOS_DE_PRUEBAS = [
    ("Dominio: folio, promedio, una evaluación por fecha",
     {"AlumnoModeloTests", "EvaluacionModeloTests"}),
    ("Roles y acceso por rol", {"RolesTests", "AccesoPorRolTests"}),
    ("Captura web", {"CapturaTests"}),
    ("Funciones de secretaria", {"SecretariaTests"}),
    ("RF-03, RF-07 y RF-10", {"BusquedaPadronTests", "GruposSinEvaluarTests", "ExportarCsvTests"}),
    ("Accesibilidad (Lighthouse)", {"AccesibilidadTests"}),
    ("Cuentas de tutor, códigos, asignaciones y comunicados",
     {"CuentaTutorTests", "CodigoActivacionTests", "AdminAppMovilTests",
      "AsignacionEntrenadorTests", "ComunicadoAdminTests"}),
    ("seed_demo y reset protegido", {"SeedDemoTests", "ResetProtegidoTests"}),
    ("Configuración de producción", {"ConfiguracionProduccionTests"}),
    ("Rendimiento (sin consultas N+1)", {"RendimientoConsultasTests"}),
    ("Sentry sin datos personales", {"SentryActivacionTests", "SentrySinDatosPersonalesTests"}),
    ("Las pruebas nunca tocan Neon", {"PruebasSinNeonTests"}),
]


def tabla_pruebas():
    filas = pruebas_por_clase()
    usadas, renglones, total = set(), [], 0
    for nombre, clases in GRUPOS_DE_PRUEBAS:
        n = sum(c for _, cl, c in filas if cl in clases)
        usadas |= clases
        renglones.append((nombre, n))
    api = sum(c for app, cl, c in filas if app == "api")
    renglones.insert(7, ("API REST para la app móvil (login, captura, aislamiento, familia)", api))
    usadas |= {cl for app, cl, _ in filas if app == "api"}
    sobrantes = [cl for _, cl, _ in filas if cl not in usadas]
    if sobrantes:
        raise RuntimeError(f"Clases de prueba sin grupo en el reporte: {sobrantes}")
    total = sum(n for _, n in renglones)
    cuerpo = "".join(f"<tr><td>{html.escape(n)}</td><td class='num'>{c}</td></tr>"
                     for n, c in renglones)
    cuerpo += f"<tr class='total'><td>Total</td><td class='num'>{total}</td></tr>"
    return cuerpo, total


CATEGORIAS = ["performance", "accessibility", "best-practices", "seo"]


def puntajes_lighthouse(carpeta):
    datos = {}
    for archivo in sorted((RAIZ / "docs/lighthouse" / carpeta).glob("*.html")):
        texto = archivo.read_text(encoding="utf-8")
        m = re.search(r"window\.__LIGHTHOUSE_JSON__ = (\{.*?\});</script>", texto, re.S)
        r = json.loads(m.group(1))
        a = r["audits"]
        datos[archivo.stem] = {
            **{c: round(r["categories"][c]["score"] * 100) for c in CATEGORIAS},
            "fcp": a["first-contentful-paint"]["displayValue"],
            "lcp": a["largest-contentful-paint"]["displayValue"],
            "cls": a["cumulative-layout-shift"]["displayValue"],
        }
    return datos


def tabla_lighthouse():
    antes, despues = puntajes_lighthouse("antes"), puntajes_lighthouse("despues")
    nombres = {"login": "Login", "panel": "Panel", "captura": "Captura",
               "movil": "Móvil", "escritorio": "Escritorio"}
    filas = ""
    for pagina in ("login", "panel", "captura"):
        for formato in ("movil", "escritorio"):
            clave = f"{pagina}-{formato}"
            a, d = antes[clave], despues[clave]
            celdas = ""
            for c in CATEGORIAS:
                celdas += (f"<td class='num'>{a[c]} → <b>{d[c]}</b></td>" if a[c] != d[c]
                           else f"<td class='num'>{d[c]}</td>")
            filas += (f"<tr><td>{nombres[pagina]}</td><td>{nombres[formato]}</td>{celdas}"
                      f"<td class='num'>{d['fcp']}</td><td class='num'>{d['lcp']}</td></tr>")
    return filas


def datos_git():
    total = int(subprocess.run(["git", "rev-list", "--count", "HEAD"], cwd=RAIZ,
                               capture_output=True, text=True, check=True).stdout)
    desde = int(subprocess.run(["git", "rev-list", "--count", "--since=2026-10-14", "HEAD"],
                               cwd=RAIZ, capture_output=True, text=True, check=True).stdout)
    return total, desde


# ---------------------------------------------------------------- 4. PDF

PIE = """<div style="width:100%; padding:0 0.9in; font-family:'P052', serif; font-size:8.5pt;
  color:#444;"><div style="border-top:1px solid #A67C2E; padding-top:5px; text-align:center;">
  <span class="pageNumber"></span></div></div>"""
ENCABEZADO = """<div style="width:100%; padding:0 0.9in; font-family:'P052', serif; font-size:8pt;
  font-style:italic; color:#555;"><div style="border-bottom:1px solid #A67C2E; padding-bottom:4px;
  display:flex; justify-content:space-between;">
  <span>Reporte del Proyecto Final — VIVA SOCCER</span>
  <span>Diseño y Evaluación de Interfaces · ITT</span></div></div>"""


def imprimir(navegador, origen, destino, con_marcos):
    pagina = navegador.new_page()
    pagina.goto(origen.as_uri())
    pagina.wait_for_load_state("networkidle")
    opciones = dict(path=str(destino), format="Letter", print_background=True,
                    prefer_css_page_size=True)
    if con_marcos:
        opciones.update(display_header_footer=True, header_template=ENCABEZADO,
                        footer_template=PIE)
    pagina.pdf(**opciones)
    pagina.close()


def normalizar(texto):
    """Para comparar el texto del PDF con el HTML: sin ligaduras (ﬁ → fi) y sin
    espacios, porque pdftotext a veces parte palabras por el espaciado ("JW T")."""
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", texto))


def texto_por_pagina(pdf):
    paginas = int(re.search(r"Pages:\s+(\d+)", subprocess.run(
        ["pdfinfo", str(pdf)], capture_output=True, text=True).stdout).group(1))
    textos = []
    for i in range(1, paginas + 1):
        t = subprocess.run(["pdftotext", "-f", str(i), "-l", str(i), str(pdf), "-"],
                           capture_output=True, text=True).stdout
        textos.append(normalizar(t))
    return textos


def armar_pdf():
    CONSTRUCCION.mkdir(exist_ok=True)
    plantilla = (AQUI / "reporte.html").read_text(encoding="utf-8")
    pruebas, total_pruebas = tabla_pruebas()
    commits, commits_desde = datos_git()
    plantilla = (plantilla.replace("<!--TABLA_PRUEBAS-->", pruebas)
                 .replace("<!--TABLA_LIGHTHOUSE-->", tabla_lighthouse())
                 .replace("{{TOTAL_PRUEBAS}}", str(total_pruebas))
                 .replace("{{COMMITS}}", str(commits))
                 .replace("{{COMMITS_DESDE}}", str(commits_desde)))

    # Los títulos que van en el índice: <h2 data-indice> y <h3 data-indice>.
    titulos = re.findall(r'<(h[23])\b[^>]*?\bdata-indice\b[^>]*>(.*?)</\1>', plantilla, re.S)
    titulos = [(n, re.sub(r"<[^>]+>", "", t).strip()) for n, t in titulos]
    figuras = re.findall(r'<figcaption>(Figura \d+\..*?)</figcaption>', plantilla, re.S)
    # En el índice de figuras va solo el inicio del pie, hasta el primer punto o dos puntos.
    figuras = [re.match(r"(Figura \d+\.\s*.*?)(?:[.:](?:\s|$))", re.sub(r"<[^>]+>", "", f).strip()).group(1)
               for f in figuras]

    numeros = {}
    with sync_playwright() as p:
        navegador = p.chromium.launch()
        for pasada in (1, 2):
            indice = "".join(
                f"<li class='{n}'><span>{html.escape(t)}</span><span class='puntos'></span>"
                f"<span class='pag'>{numeros.get(t, '')}</span></li>" for n, t in titulos)
            lista_figuras = "".join(
                f"<li class='h3'><span>{html.escape(f)}</span><span class='puntos'></span>"
                f"<span class='pag'>{numeros.get(f, '')}</span></li>" for f in figuras)
            cuerpo = plantilla.replace("<!--INDICE-->", indice).replace(
                "<!--INDICE_FIGURAS-->", lista_figuras)
            fuente = AQUI / "reporte_armado.html"
            fuente.write_text(cuerpo, encoding="utf-8")
            pdf = CONSTRUCCION / "cuerpo.pdf"
            imprimir(navegador, fuente, pdf, con_marcos=True)
            textos = texto_por_pagina(pdf)
            # Las páginas del índice también contienen los títulos: se buscan después.
            inicio = next(i for i, t in enumerate(textos)
                          if normalizar("1. Título del proyecto") in t
                          and normalizar("Índice") not in t)
            for t in [t for _, t in titulos] + figuras:
                clave = normalizar(html.unescape(t))
                pag = next((i for i in range(inicio, len(textos)) if clave in textos[i]), None)
                if pag is None:
                    raise RuntimeError(f"No encontré «{t}» en el PDF.")
                numeros[t] = pag + 1
        imprimir(navegador, AQUI / "portada.html", CONSTRUCCION / "portada.pdf",
                 con_marcos=False)
        navegador.close()
    fuente.unlink()
    subprocess.run(["pdfunite", str(CONSTRUCCION / "portada.pdf"), str(pdf), str(SALIDA)],
                   check=True)
    print(f"Listo: {SALIDA.relative_to(RAIZ)} ({total_pruebas} pruebas, {commits} commits)")


if __name__ == "__main__":
    if "--sin-capturas" not in sys.argv:
        tomar_capturas()
        recortar_propuesta()
    armar_pdf()
