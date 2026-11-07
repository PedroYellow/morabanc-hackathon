#!/usr/bin/env python3
"""
Tests del formato de euros y del texto del pitch.
=================================================
El pitch se lee en pantalla, delante del jurado. "34800.00 €" se lee como
un dato crudo de maquina; "34.800,00 €" se lee como una cuenta. Este modulo
comprueba que el formato es el europeo y que el texto del pitch no suelta
numeros en formato anglosaxon ni frases raras ("0 a medias").
"""

import os
import re
import sys
from decimal import Decimal as D

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

from engine.fiscal_andorra import eur  # noqa: E402
from agent.bedrock_agent import _eur  # noqa: E402

fallos = []
n = 0


def check(nombre, ok, extra=""):
    global n
    n += 1
    print(f"  {'PASS' if ok else 'FAIL'}  {nombre}{(' -> ' + str(extra)) if extra else ''}")
    if not ok:
        fallos.append(nombre)


# ==========================================================================
print("\n=== Formato de euros (motor) ===")
# ==========================================================================

check("entero grande", eur(34800), "34.800,00")
check("decimal", eur(42994.29), "42.994,29")
check("decimal pequeno", eur(23.98), "23,98")
check("cero", eur(0), "0,00")
check("negativo", eur(-12.5), "-12,50")
check("mil", eur(1000), "1.000,00")
check("un millon", eur(1000000), "1.000.000,00")
check("acepta Decimal", eur(D("587.95")), "587,95")
check("acepta string numerico", eur("59.99"), "59,99")
check("texto no numerico", eur("n/a"), "n/a")
check("decimales configurables", eur(34800, 0), "34.800")


# ==========================================================================
print("\n=== Formato de euros (agente) ===")
# ==========================================================================

check("agente: entero", _eur(28800), "28.800,00")
check("agente: decimal", _eur(1851.43), "1.851,43")
check("agente: mismo resultado que el motor",
      _eur(42994.29) == eur(42994.29), True)
check("agente: no numerico", _eur(None), "None")


# ==========================================================================
print("\n=== El texto del pitch usa formato europeo ===")
# ==========================================================================

from agent.bedrock_agent import AgenteFinanciero, ContextoEmpresa  # noqa: E402
from engine.tesoreria import parse_extracto_csv  # noqa: E402

csv = open(os.path.join(RAIZ, "data", "demo_freelancer_contratar.csv"),
           encoding="utf-8").read()
ctx = ContextoEmpresa(
    movimientos=parse_extracto_csv(csv),
    saldo_actual=D("3200"),
    renta_neta_anual=D("28000"),
    margen_bruto=D("0.70"),
)
agente = AgenteFinanciero(ctx, mock=True)

preguntas_pitch = [
    "¿Cuánto se me está escapando cada mes?",
    "¿Cuánto me queda de caja cada mes?",
    "¿Cuándo salta mi tramo de cotización?",
    "¿Puedo contratar a alguien a 2.400 brutos al mes?",
    "¿Y si es de 2900 euros?",
    "¿Cuánto cotizo a la CASS?",
]

# Un numero en formato anglosaxon es: digitos, punto, digitos (sin coma).
# El formato europeo es: digitos, coma, digitos.
PATRON_ANGLO = re.compile(r"\d+\.\d{2}(?!\d)")

for pregunta in preguntas_pitch:
    r = agente.preguntar(pregunta)
    txt = r["respuesta"]
    # Se ignoran las fechas (dd/mm/yyyy no tienen punto) y los porcentajes.
    limpio = re.sub(r"\d+\.\d{2}%", "", txt)
    m = PATRON_ANGLO.search(limpio)
    check(f"sin numeros anglosajones: '{pregunta[:32]}'", m is None,
          m.group(0) if m else "")

# El pitch no debe decir "0 a medias" (suena a error).
r_cierre = agente.preguntar("¿Hiciste caso con mis consejos?")
check("el cierre no dice '0 a medias'", "0 a medias" not in r_cierre["respuesta"])


# ==========================================================================
print("\n=== Las cifras clave del pitch son las esperadas ===")
# ==========================================================================

r = agente.preguntar("¿Puedo contratar a alguien a 2.400 brutos al mes?")
txt = r["respuesta"]
check("el coste anual es 28.800,00", "28.800,00" in txt, txt[:60])
check("la facturacion es 42.994,29", "42.994,29" in txt, txt[:60])

r2 = agente.preguntar("¿Y si es de 2900 euros?")
txt2 = r2["respuesta"]
check("el coste recalculado es 34.800,00", "34.800,00" in txt2, txt2[:60])
check("la facturacion recalculada es 51.951,43", "51.951,43" in txt2, txt2[:60])
check("las dos cifras son distintas", txt != txt2, True)

r3 = agente.preguntar("¿Cuánto cotizo a la CASS?")
check("la cuota CASS es 587,95", "587,95" in r3["respuesta"], r3["respuesta"][:60])


print()
if fallos:
    print(f"FALLOS: {len(fallos)} -> {fallos}")
    sys.exit(1)
print(f"TODOS LOS TESTS PASAN ({n})")
