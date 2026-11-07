"""Tests del asistente de voz y de la carga de archivos.

Comprueban lo que NO se puede ver en el navegador sin montarlo:
  - El texto del saludo y de la guia sale bien en los tres idiomas.
  - La guia se decide por codigo (que slots faltan), no por el LLM.
  - Los slots que se miran son los que el motor usa de verdad.
  - Los ficheros que se aceptan incluyen el CSV (el que lee el motor).
"""

from __future__ import annotations

import json
import os
import re

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONT = os.path.join(RAIZ, "frontend")
APP_JS = os.path.join(FRONT, "assets", "app.js")
INDEX_HTML = os.path.join(FRONT, "index.html")

fallos: list[str] = []
n = 0


def check(nombre: str, obtenido, esperado=True) -> None:
    global n
    n += 1
    if obtenido != esperado:
        fallos.append(f"{nombre}: se esperaba {esperado!r}, se obtuvo {obtenido!r}")
        print(f"  FAIL  {nombre}")
    else:
        print(f"  PASS  {nombre}")


def check_msg(nombre: str, condicion, explicacion: str = "") -> None:
    """Como check(), pero el tercer argumento es una EXPLICACION, no un
    valor esperado. Para booleanos con texto explicativo."""
    global n
    n += 1
    if not condicion:
        fallos.append(f"{nombre}: {explicacion}")
        print(f"  FAIL  {nombre}")
    else:
        print(f"  PASS  {nombre}")


app = open(APP_JS, encoding="utf-8").read()
html = open(INDEX_HTML, encoding="utf-8").read()

print("\n=== EL ASISTENTE SALUDA ===")
check("existe la funcion saludar", "function saludar" in app)
check("el saludo se dispara al arrancar la voz", "saludar()" in app)
check("el saludo va al agente de voz", "decirAlAgente(saludo)" in app)
check("el saludo tiene su propio texto", "vozSaludo" in app)

print("\n=== EL ASISTENTE ACOMPANIA ===")
check("existe la guia de lo que falta", "function slotFaltante" in app)
check("la guia pregunta por la renta", "vozFaltaRenta" in app)
check("la guia pregunta por el saldo", "vozFaltaSaldo" in app)
check("la guia pregunta por la actividad", "vozFaltaActividad" in app)
check("avisa cuando ya no falta nada", "vozListo" in app)
check("confirma lo que ha entendido", "function confirmarDato" in app)
check("la confirmacion se llama al capturar", "confirmarDato(etq)" in app)

print("\n=== LA GUIA LA DECIDE EL CODIGO, NO EL LLM ===")
# La guia sale de slotFaltante(), que mira el contexto. No puede haber
# una llamada al backend dentro de esa funcion.
m = re.search(r"function slotFaltante\(\)\s*\{(.*?)\n  \}", app, re.S)
check("slotFaltante existe", m is not None)
if m:
    cuerpo = m.group(1)
    check("slotFaltante no llama a la API", "preguntar(" not in cuerpo and "fetch(" not in cuerpo)
    check("slotFaltante mira la renta", "renta" in cuerpo)
    check("slotFaltante mira el saldo", "saldo" in cuerpo)
    check("slotFaltante mira la actividad", "actividad" in cuerpo)

# Los slots que mira la guia tienen que ser los que usa el motor de verdad.
# OJO: el saldo no vive en el motor fiscal sino en el de tesoreria, y ahi
# se llama saldo_inicial/saldo_final (el front lo manda como saldo_actual
# al backend, que es quien lo traduce).
motor_fiscal = open(os.path.join(RAIZ, "engine", "fiscal_andorra.py"), encoding="utf-8").read()
motor_teso = open(os.path.join(RAIZ, "engine", "tesoreria.py"), encoding="utf-8").read()
check("el motor fiscal conoce renta_neta_anual", "renta_neta_anual" in motor_fiscal)
check("el motor de tesoreria conoce el saldo", "saldo_inicial" in motor_teso)
check("el motor conoce la actividad", "actividad" in motor_fiscal)

print("\n=== LOS TRES IDIOMAS ===")
for lang in ("es", "ca", "en"):
    bloque = re.search(rf"\n    {lang}: \{{(.*?)\n    \}},", app, re.S)
    check(f"el bloque {lang} existe", bloque is not None)
    if bloque:
        cuerpo = bloque.group(1)
        for clave in ("vozSaludo", "vozFaltaRenta", "vozFaltaSaldo", "vozFaltaActividad", "vozListo"):
            check(f"{lang}: {clave}", clave in cuerpo)

print("\n=== CARGA DE ARCHIVOS ===")
check("el overlay de arrastre existe en el HTML", 'id="dropOverlay"' in html)
check("el input acepta varios ficheros", 'id="fileInput" multiple' in html)
check("el input acepta CSV", ".csv" in html)
check("el input acepta PDF", ".pdf" in html)
check("el input acepta Excel", ".xlsx" in html)
check("el input acepta imagenes", "image/*" in html)
check("hay arrastre sobre toda la pagina",
      'window.addEventListener("dragenter"' in app and 'window.addEventListener("drop"' in app)
check("el motor sigue leyendo el CSV", "extracto_csv: contexto.csv" in app)
check("el motor recibe el fichero subido", "csv: texto" in app or "csv: texto," in app)

print("\n=== LA MARCA ===")
check("el HTML usa PlanificAND", "PlanificAND" in html)
check("MoraBanc sigue como partner", "MoraBanc" in html)
check("el titulo lleva PlanificAND", "<title>PlanificAND" in html)

print("\n=== EL PROXY DE /api EN EL VPS ===")
# El vhost de nginx tiene que tener el bloque /api: sin el, el POST
# devuelve 404 y la web se queda en modo demo sin que se note.
deploy = open(os.path.join(RAIZ, "scripts", "deploy_welcome.sh"), encoding="utf-8").read()
check("el vhost de nginx tiene bloque /api", "location /api/" in deploy)
check("el proxy apunta a la API de AWS", "proxy_pass" in deploy and "API_UPSTREAM" in deploy)
check_msg("la API key la pone nginx, no el navegador",
      'proxy_set_header x-api-key' in deploy,
      "si la clave viaja en el HTML, se puede leer en el codigo fuente")
check_msg("el Host es el de API Gateway, no el del dominio",
      "proxy_set_header Host ${API_HOST}" in deploy
      and "proxy_set_header Host $host" not in deploy,
      "con el Host del dominio propio, API Gateway responde 403")
check_msg("se recorta la barra final de la URL de la API",
      'API_UPSTREAM="${API_URL%/}"' in deploy,
      "con barra final proxy_pass la usaria como ruta y daria 404")


print("\n" + "=" * 62)
if fallos:
    print(f"FALLOS: {len(fallos)} de {n}")
    for f in fallos[:10]:
        print("  -", f)
    raise SystemExit(1)
print(f"TODOS LOS TESTS DEL ASISTENTE PASAN ({n})")
print("=" * 62)
