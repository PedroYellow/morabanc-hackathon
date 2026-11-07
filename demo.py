"""
Demo ejecutable del motor — genera los numeros que se Presentaran en el pitch.
Ejecutar: python3 demo.py
"""

import sys, os
from decimal import Decimal as D

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from engine.fiscal_andorra import (
    tramo_cass_para, cass_anual, irpf, igi, crossover_cass,
    punto_optimo_facturacion, comparar_escenarios, Escenario,
    simular_contratacion,
)


def linea(c="="):
    print(c * 74)


def titulo(t):
    print()
    linea()
    print(t)
    linea()


def eur(x):
    return f"{x:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")


# ---------------------------------------------------------------------------
titulo("CASO 1 — Freelance de servicios, 30.000 €/año (el caso de la demo)")

renta = D("30000")
t = tramo_cass_para(renta)
r = irpf(base_general=renta)

print(f"Renda neta anual:              {eur(renta)}")
print(f"Tramo CASS:                   {t.nombre}  (base {eur(t.base)})")
print(f"Cuota CASS mensual:           {eur(t.cuota_mensual)}")
print(f"  - rama general (10%):       {eur(t.rama_general)}")
print(f"  - rama jubilacion (12%):    {eur(t.rama_jubilacion)}")
print(f"Coste CASS anual:             {eur(cass_anual(t))}")
print(f"IRPF (base general):          {eur(r.base_general)} tributables")
print(f"  cuota 10%:                  {eur(r.cuota_general)}")
print(f"  bonificacio art. 46:      -{eur(r.bonificacion_actividades)}  (limit 800)")
print(f"IRPF a pagar:                 {eur(r.cuota_total)}  (efectivo {r.tipo_efectivo}%)")
print()
total_fiscal = cass_anual(t) + r.cuota_total
print(f"CARGA FISCAL TOTAL:           {eur(total_fiscal)}  ({total_fiscal/renta*100:.2f}% sobre la renta)")
print(f"NETO DESPUES DE FISCALIDAD:   {eur(renta - total_fiscal)}")
print()
print(f"Condicion del tramo: {t.condicion}")

# ---------------------------------------------------------------------------
titulo("CASO 1b — EL CROSSOVER: el insight que no da ningun ERP")

for renta_test, etiqueta in [
    (D("26000"), "Autonomo a 26.000 €/año"),
    (D("45000"), "Autonomo a 45.000 €/año"),
    (D("55000"), "Autonomo a 55.000 €/año"),
]:
    c = crossover_cass(renta_test)
    print(f"{etiqueta}:")
    if c.existe:
        print(f"  -> {c.tipo}")
        print(f"  -> {c.detalle}")
        if c.delta_anual > 0:
            print(f"  -> Impacto: +{eur(c.delta_anual)}/año en cotizacion")
    else:
        print(f"  -> {c.detalle}")
    print()

# ---------------------------------------------------------------------------
titulo("CASO 2 — '¿Puedo contratar a alguien?' (la pregunta del pitch)")

sim = simular_contratacion(
    renta_neta_actual=D("30000"),
    margen_bruto=D("0.70"),
    coste_nuevo_empleado_mensual=D("2400"),
)
print(sim["veredicto"])
print()
print(f"Coste del empleado (12 meses):     {eur(sim['coste_nuevo_empleado_anual'])}")
print(f"Facturacion extra necesaria:       {eur(sim['facturacion_adicional_para_cubrirlo'])}")
print(f"  de los cuales IGI adicional:      {eur(sim['igi_adicional'])}")
print()
d = sim["comparativa"]
print()
print("Nota: contratar NO cambia la renta neta (el coste es gasto deducible),")
print("asi que el IRPF y la CASS se mantienen. Lo que cambia es la caja:")
print(f"  - Bajan {eur(sim['coste_nuevo_empleado_anual'])}/año de caja por la nomina")
print(f"  - Hay que facturar {eur(sim['facturacion_adicional_para_cubrirlo'])} adicionales")
print(f"  - Umbral de rentable: facturar mas de {eur(sim['facturacion_adicional_para_cubrirlo'])}")
print(f"    => con margen del {sim['margen_bruto']}% eso son {eur(sim['facturacion_adicional_para_cubrirlo']/D('0.70'))} de facturacion bruta")
print()
print(f"Delta neto anual:                  {eur(d['delta_neto_anual'])}")
print(f"Delta CASS anual:                  {eur(d['delta_cass_anual'])}")
print(f"Delta IRPF anual:                  {eur(d['delta_irpf_anual'])}")
print()
print("Detalle escenario A (sin contratar):")
for k, v in d["detalle"]["a"].items():
    print(f"  {k}: {v}")
print("Detalle escenario B (contratando):")
for k, v in d["detalle"]["b"].items():
    print(f"  {k}: {v}")

# ---------------------------------------------------------------------------
titulo("CASO 3 — 'Subir el sueldo de 2.900 a 3.200 €' (la segunda vuelta del pitch)")

for sueldo in (D("2900"), D("3200"), D("3600")):
    renta_anual = sueldo * 12
    t_x = tramo_cass_para(renta_anual)
    r_x = irpf(base_general=renta_anual)
    carga = cass_anual(t_x) + r_x.cuota_total
    neto = renta_anual - carga
    print(f"Sueldo {eur(sueldo)}/mes -> renta {eur(renta_anual)}/año")
    print(f"   CASS {t_x.nombre} ({eur(t_x.cuota_mensual)}/mes) | IRPF {eur(r_x.cuota_total)} "
          f"| carga {eur(carga)} | neto real {eur(neto)}")
    c = crossover_cass(renta_anual)
    if c.existe:
        print(f"   ATENCION: {c.tipo} en {eur(c.renta_punto)}")
    print()

# ---------------------------------------------------------------------------
titulo("CASO 4 — '¿Facturar mas compensa?' (el insight contraintuitivo)")

po = punto_optimo_facturacion(D("30000"), D("0.70"))
print(f"Renta actual: {eur(po['renta_actual'])} | Margen bruto: {po['margen_bruto']}%")
print(f"Mejor punto de facturacion: {po['mejor_punto']}")
print()
print(po["nota"])

# ---------------------------------------------------------------------------
titulo("CASO 5 — IGI y calendario de pago")

g = igi(D("40000"))
print(g.explicacion.replace("4.500%", "4,5%"))
for c in g.calendario:
    print(f"  {c['trimestre']}: base {eur(c['base_estimada'])} -> cuota {eur(c['cuota_estimada'])}")

# ---------------------------------------------------------------------------
titulo("EJEMPLOS DE SALIDA PARA EL AGENTE DE IA (el LLM explica, el motor calcula)")

resultado = {
    "pregunta": "¿Puedo contratar a alguien a 2.400 brutos?",
    "respuesta_motor": {
        "coste_anual": str(sim["coste_nuevo_empleado_anual"]),
        "facturacion_adicional_requerida": str(sim["facturacion_adicional_para_cubrirlo"]),
        "tramo_cass_actual": tramo_cass_para(D("30000")).nombre,
        "crossover_detectado": crossover_cass(D("30000")).tipo,
        "veredicto": sim["veredicto"],
    },
}
import json
print(json.dumps(resultado, ensure_ascii=False, indent=2))
print()
print(">>> El LLM recibira SOLO este objeto y lo explicara en lenguaje natural.")
print(">>> No puede calcular nada: todos los numeros vienen del motor.")
