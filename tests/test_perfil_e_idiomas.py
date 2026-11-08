"""
Tests del perfil del cliente y de los idiomas.

Estos dos modulos son lo que hace que el producto sea un ASESOR y no
un formulario: el perfil es lo que el banco ya sabe del cliente (y
por tanto lo que el agente NO debe preguntar) y los idiomas son lo que
permite que un cliente habla en cualquier idioma.

Run: python3 tests/test_perfil_e_idiomas.py
"""

import os
import sys
from decimal import Decimal

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

from engine.perfil_cliente import (
    ProductoContratado,
    ProfileCliente,
    evaluar_compra,
    evaluar_contratacion,
    sugerir_siguiente_pregunta,
)
from engine.idiomas import detectar_idioma, instruction_de_idioma

fallos = 0


def check(nombre, condicion):
    global fallos
    if not condicion:
        fallos += 1
        print(f"  FAIL {nombre}")
    else:
        print(f"  PASS {nombre}")


# ─────────────────────────────────────────────────────────────────────
print("=== EL PERFIL: lo que el banco ya sabe ===")
# ─────────────────────────────────────────────────────────────────────

p = ProfileCliente(
    nombre="Pedro",
    figura_fiscal="autonomo",
    actividad="Freelance de servicios",
    renta_neta_anual=Decimal("30000"),
    margen_bruto=Decimal("0.70"),
    saldo_actual=Decimal("8500"),
    gasto_fijo_mensual=Decimal("900"),
    colchon_meses=Decimal("3.6"),
    productos=[ProductoContratado(tipo="hipoteca", cuota_mensual=Decimal("900"))],
)
dossier = p.resumen_para_el_agente()
check("el dossier tiene la renta neta", "30000" in dossier)
check("el dossier tiene el saldo", "8500" in dossier)
check("el dossier dice la figura fiscal", "autonomo" in dossier)
check("el dossier dice que es una sociedad andorrana si lo es",
      "ANDORRANA" in ProfileCliente(
          figura_fiscal="sociedad", sociedad_andorrana=True
      ).resumen_para_el_agente())
check("el dossier avisa si no consta si la sociedad es andorrana",
      "no consta" in ProfileCliente(
          figura_fiscal="sociedad"
      ).resumen_para_el_agente())
check("el dossier lista los productos que ya tiene", "hipoteca" in dossier)
check("el dossier NO inventa lo que no sabe",
      "renta neta" not in ProfileCliente().resumen_para_el_agente().lower()
      or "Renta neta anual" not in ProfileCliente().resumen_para_el_agente())

# ─────────────────────────────────────────────────────────────────────
print("\n=== LO QUE EL AGENTE NO DEBE PREGUNTAR ===")
# ─────────────────────────────────────────────────────────────────────

# Con la renta ya en el dossier, la siguiente pregunta es el importe.
check("con la renta sabida, pregunta el importe de la compra",
      "importe" in sugerir_siguiente_pregunta(p, "coche").lower())
# Sin renta, solo pregunta la renta (una sola cosa, no un cuestionario).
pregunta = sugerir_siguiente_pregunta(ProfileCliente(figura_fiscal="autonomo"), "coche")
check("sin renta, pregunta solo la renta neta", "renta neta" in pregunta.lower())
check("sin renta, no pregunta el saldo ni el margen",
      "saldo" not in pregunta.lower() and "margen" not in pregunta.lower())
# Para contratar, el dato que falta es el bruto.
check("para contratar, pregunta el bruto",
      "bruto" in sugerir_siguiente_pregunta(p, "contratar").lower())
# Para contratar, el bruto SI se pregunta: es la decision nueva, no
# un dato que el banco tenga. Pero no se pregunta nada mas.
pregunta_contrato = sugerir_siguiente_pregunta(p, "contratar")
check("para contratar solo pregunta el bruto",
      "bruto" in pregunta_contrato.lower()
      and "renta neta" not in pregunta_contrato.lower()
      and "saldo" not in pregunta_contrato.lower())

# ─────────────────────────────────────────────────────────────────────
print("\n=== LAS DECISIONES DE COMPRA ===")
# ─────────────────────────────────────────────────────────────────────

r = evaluar_compra(p, objetivo="coche", importe=Decimal("30000"))
check("un coche de 30.000 cabe para este perfil", r.cabe)
check("el limite no es una cifra absurda",
      Decimal("10000") < r.importe_maximo < Decimal("400000"))
check("el veredicto dice cuanto puede gastar", "puedes gastar" in r.veredicto().lower())
check("avisa del efecto fiscal de la inversion",
      any("deducible" in a.lower() for a in r.avisos))
check("la regla explica el criterio del 30 %", "30 %" in r.regla)

# Una compra que no cabe.
r2 = evaluar_compra(p, objetivo="coche", importe=Decimal("300000"))
check("una compra enorme no cabe", not r2.cabe)

# Sin renta no se puede decir: se pide la renta.
r3 = evaluar_compra(ProfileCliente(figura_fiscal="autonomo"), objetivo="coche",
                     importe=Decimal("30000"))
check("sin renta, se pide la renta en vez de inventar", not r3.cabe)
check("sin renta, el aviso menciona la renta neta",
      any("renta neta" in a.lower() for a in r3.avisos))

# La vivienda tiene su propio criterio (no es gasto del negocio).
r4 = evaluar_compra(p, objetivo="vivienda", importe=Decimal("300000"))
check("la vivienda tiene un limite propio, no el del negocio",
      r4.importe_maximo != r.importe_maximo)
check("la vivienda avisa de que no es deducible",
      any("deduces" in a.lower() or "deducible" in a.lower() for a in r4.avisos))

# ─────────────────────────────────────────────────────────────────────
print("\n=== CONTRATAR ===")
# ─────────────────────────────────────────────────────────────────────

rc = evaluar_contratacion(p, bruto_anual=Decimal("28800"), personas=1)
check("el coste incluye las contribuciones sociales",
      rc.carga_fiscal_adicional > 0)
check("el aviso del CASS por la masa salarial",
      any("CASS" in a for a in rc.avisos))
check("la regla cita el 21 % de seguridad social", "21 %" in rc.regla)

# ─────────────────────────────────────────────────────────────────────
print("\n=== LOS IDIOMAS ===")
# ─────────────────────────────────────────────────────────────────────

for texto, esperado in [
    ("Hola, ¿cuánto me queda este mes?", "es"),
    ("Bon dia, vull comprar un cotxe de 30.000 euros", "ca"),
    ("Bonjour, je voudrais acheter une maison", "fr"),
    ("Hello, I would like to buy a car", "en"),
    ("Boa tarde, quanto custa um carro? obrigado", "pt"),
    ("Buongiorno, vorrei comprare una macchina", "it"),
    ("Buna ziua, cat costa?", "ro"),
    ("Привет, сколько стоит машина?", "ru"),
    ("مرحبا، كم الثمن السيارة؟", "ar"),
    ("你好，我想买车", "zh"),
]:
    cod, conf = detectar_idioma(texto)
    check(f"detecta {esperado} en: {texto[:38]}", cod == esperado)

# Sin senal, espanol (el idioma por defecto del banco).
check("sin senal, espanol", detectar_idioma("xyz abc 123")[0] == "es")

# La instruccion al agente.
inst = instruction_de_idioma("fr", 1.0)
check("la instruccion dice el idioma", "FRANCES" in inst)
check("la instruccion dice que las cifras van en espanol",
      "cifras" in inst.lower() and "espanol" in inst.lower())
check("en espanol no se fuerza nada raro",
      "español" in instruction_de_idioma("es", 1.0).lower()
      or "espanol" in instruction_de_idioma("es", 1.0).lower())

print("\n" + "=" * 60)
if fallos:
    print(f"{fallos} FALLOS")
    sys.exit(1)
print("TODOS LOS TESTS PASAN")
print("=" * 60)
