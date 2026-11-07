"""
Tests del motor fiscal andorrano.
Cada assert compara contra un valor OFICIAL PUBLICADO (CASS / Govern d'Andorra / BOPA).
Si la normativa cambia, estos tests avisan. No se "ajusta" el motor para que
pase: se actualiza la fuente y se documenta.
"""

import sys
import os
from decimal import Decimal

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from engine.fiscal_andorra import (  # noqa: E402
    tramo_cass_para,
    cass_anual,
    irpf,
    igi,
    crossover_cass,
    punto_optimo_facturacion,
    comparar_escenarios,
    Escenario,
    simular_contratacion,
    pago_fraccionado,
    SALARIO_MEDIO_MENSUAL_CASS_2026,
)

D = Decimal

# Valores oficiales publicados por la CASS para 2026 (cuota mensual)
CUOTAS_OFICIALES = {
    "25%": D("146.99"),
    "50%": D("335.57"),
    "62,5%": D("367.47"),
    "75%": D("440.97"),
    "100%": D("587.95"),
    "125%": D("734.94"),
    "137,5%": D("808.44"),
}

# Bases oficiales publicadas por la CASS para 2026
BASES_OFICIALES = {
    "25%": D("668.13"),
    "50%": D("1525.33"),
    "62,5%": D("1670.33"),
    "75%": D("2004.39"),
    "100%": D("2672.52"),
    "125%": D("3340.65"),
    "137,5%": D("3674.72"),
}

fallos = []


def check(nombre, obtenido, esperado):
    ok = obtenido == esperado
    if not ok:
        fallos.append(f"{nombre}: obtenido {obtenido} != esperado {esperado}")
    print(f"  {'PASS' if ok else 'FAIL'}  {nombre}: {obtenido}"
          + ("" if ok else f" (esperado {esperado})"))
    return ok


_RENTA_POR_TRAMO = {
    "25%": D("4000"), "50%": D("8000"), "62,5%": D("15000"), "75%": D("20000"),
    "100%": D("30000"), "125%": D("45000"), "137,5%": D("60000"),
}

print("\n=== CASS: bases oficiales 2026 (BOPA Decret 28/2026) ===")
# El motor usa la tabla publicada por la CASS como fuente de verdad. La CASS
# redondea cada base desde un salari global sin truncar, por eso el 62,5%
# oficial es 1.670,33 y no 1.670,32 (lo que daria 62,5% de 2.672,52 ya redondeado).
from engine.fiscal_andorra import _BASES_PUBLICADAS as _BP
for nombre, base_esperada in BASES_OFICIALES.items():
    check(f"base {nombre}", _BP[nombre], base_esperada)

print("\n=== CASS: cuotas oficiales por tramo (22%) ===")
from engine.fiscal_andorra import _CUOTAS_PUBLICADAS as _CP
for nombre, cuota_esperada in CUOTAS_OFICIALES.items():
    check(f"cuota {nombre}", _CP[nombre], cuota_esperada)

# Y que el motor, con la base estandar, devuelve exactamente la cuota oficial
for nombre in CUOTAS_OFICIALES:
    t_x = tramo_cass_para(_RENTA_POR_TRAMO[nombre], salario_minimo=D("1525.33"))
    check(f"motor cuota {nombre}", t_x.cuota_mensual, CUOTAS_OFICIALES[nombre])

print("\n=== CASS: tramo 50% con salari minim vigente ===")
# Base oficial del 50% = 1.525,33 EUR (salari minim S1 2026).
# Desde el 1 de julio de 2026 el salari minim sube a 1.568,67 EUR y el tramo
# 50% se eleva automaticamente (regla CASS / art. 99).
t50_s1 = tramo_cass_para(D("8000"), salario_minimo=D("1525.33"))
check("tramo 50% base S1", t50_s1.base, D("1525.33"))
check("tramo 50% cuota S1", t50_s1.cuota_mensual, D("335.57"))

t50_s2 = tramo_cass_para(D("8000"), salario_minimo=D("1568.67"))
check("tramo 50% base desde julio (salari minim)", t50_s2.base, D("1568.67"))
check("tramo 50% cuota desde julio", t50_s2.cuota_mensual, D("345.11"))

print("\n=== CASS: seleccion de tramo por renta neta ===")
casos_tramo = [
    (D("4000"), "25%", "renta < 6.000"),
    (D("8000"), "50%", "renta 6.000-12.000"),
    (D("15000"), "62,5%", "renta 12.000-18.000"),
    (D("20000"), "75%", "renta 18.000-24.000"),
    (D("30000"), "100%", "renta 24.000-40.000"),
    (D("45000"), "125%", "renta 40.000-50.000"),
    (D("60000"), "137,5%", "renta > 50.000"),
]
for renta, esperado, nota in casos_tramo:
    t = tramo_cass_para(renta)
    check(f"tramo para {nota} ({renta})", t.nombre, esperado)

print("\n=== CASS: detraccion rama general vs jubilacion en tramo 100% ===")
t100 = tramo_cass_para(D("30000"))
check("rama general (10%)", t100.rama_general, D("267.25"))
check("rama jubilacion (12%)", t100.rama_jubilacion, D("320.70"))
# La cuota oficial puede diferir 0,01 € de la suma de las ramas redondeadas
diff_ramas = t100.rama_general + t100.rama_jubilacion - t100.cuota_mensual
check("desviacion ramas vs cuota <= 0.01", abs(diff_ramas) <= D("0.01"), True)
check("rama general 10%", t100.rama_general, D("267.25"))
check("rama jubilacion 12%", t100.rama_jubilacion, D("320.70"))

print("\n=== IRPF: escala oficial (Govern d'Andorra / art. 35-46) ===")
# Hasta 24.000 -> 0%
r = irpf(base_general=D("24000"))
check("24.000 -> cuota 0", r.cuota_total, D("0"))

r = irpf(base_general=D("30000"))
# (30.000 - 24.000) * 10% = 600 ; bonificacio 50% = 300 (bajo el cap de 800)
check("30.000 -> cuota 300", r.cuota_total, D("300.00"))
check("30.000 -> bonificacion 300", r.bonificacion_actividades, D("300.00"))

r = irpf(base_general=D("40000"))
# (40.000-24.000)*10% = 1.600 ; bonificacio 800 (cap) -> 800
check("40.000 -> cuota 800", r.cuota_total, D("800.00"))
check("40.000 -> bonificacion tope 800", r.bonificacion_actividades, D("800.00"))

r = irpf(base_general=D("50000"))
# (50.000-24.000)*10% = 2.600 ; bonificacio 800 -> 1.800
check("50.000 -> cuota 1.800", r.cuota_total, D("1800.00"))

r = irpf(base_general=D("100000"))
# (100.000-24.000)*10% = 7.600 ; bonificacio 800 -> 6.800
check("100.000 -> cuota 6.800", r.cuota_total, D("6800.00"))

print("\n=== IRPF: matiz del 5% (hallazgo de mercado) ===")
# El "5%" que se publica es una simplificacion. El tipo efectivo real sube
# del 0% al 2% entre 24.000 y 40.000 €, y la bonificacion topa en 800 € justo
# en 40.000 €. Ningun ERP muestra este matiz.
for bg, esperado in [
    (D("24000"), D("0.00")), (D("26000"), D("100.00")), (D("30000"), D("300.00")),
    (D("35000"), D("550.00")), (D("40000"), D("800.00")), (D("45000"), D("1300.00")),
]:
    rr = irpf(base_general=bg)
    check(f"IRPF cuota sobre {bg}", rr.cuota_total, esperado)

# El tope de 800 se alcanza exactamente en 40.000
r39 = irpf(base_general=D("39000"))
r40 = irpf(base_general=D("40000"))
check("bonificacion bajo el tope a 39.000", r39.bonificacion_actividades, D("750.00"))
check("bonificacion en el tope a 40.000", r40.bonificacion_actividades, D("800.00"))
check("tipo efectivo maximo en el tramo 24k-40k es 2%", irpf(base_general=D("40000")).tipo_efectivo, D("2.00"))

print("\n=== IRPF: base de ahorro ===")
r = irpf(base_general=D("0"), base_ahorro=D("5000"))
check("ahorro 5.000 -> cuota 200", r.cuota_ahorro, D("200.00"))

print("\n=== IRPF: tipo efectivo ===")
r = irpf(base_general=D("40000"))
check("efectivo en 40.000", r.tipo_efectivo, D("2.00"))

print("\n=== Pago fraccionado (5%) ===")
check("fraccionado 30.000", pago_fraccionado(D("30000")), D("1500.00"))

print("\n=== IGI 4,5% ===")
g = igi(D("40000"))
check("IGI sobre 40.000", g.cuota, D("1800.00"))
check("IGI 4 trimestres", len(g.calendario), 4)

print("\n=== Crossover: deteccion de saltos ===")
c = crossover_cass(D("26000"))
check("crossover existe a 26.000", c.existe, True)
check("crossover tipo a 26.000", c.tipo, "Bonificacion IRPF art. 46 toca su techo de 800 €")
check("punto de corte", c.renta_punto, D("40000"))

c = crossover_cass(D("45000"))
check("crossover existe a 45.000", c.existe, True)
check("crossover tipo a 45.000", c.tipo, "CASS 100% -> 125%")
# (734.94 - 587.95) * 12 = 1763.88
check("delta CASS anual 100->125", c.delta_anual, D("1763.88"))

c = crossover_cass(D("15000"))
check("sin crossover a 15.000", c.existe, False)

print("\n=== Comparativa de escenarios ===")
comp = comparar_escenarios(
    Escenario("Sin contratar", D("30000")),
    Escenario("Contratando", D("30000"), {"nota": "test"}),
)
check("delta neto cero si no cambia la renta", comp.delta_neto_anual, D("0.00"))

print("\n=== Simular contratacion ===")
sim = simular_contratacion(
    renta_neta_actual=D("30000"),
    margen_bruto=D("0.70"),
    coste_nuevo_empleado_mensual=D("2400"),
)
# 2.400 * 12 = 28.800 / 0.70 = 41.142.857 + IGI 4,5% = 42.994.28
check("facturacion adicional requerida", sim["facturacion_adicional_para_cubrirlo"], D("42994.29"))
check("IGI adicional", sim["igi_adicional"], D("1851.43"))

print("\n=== Punto optimo de facturacion ===")
po = punto_optimo_facturacion(D("30000"), D("0.70"))
check("tiene mejor punto", po["mejor_punto"] is not None, True)
print(f"       mejor punto: {po['mejor_punto']}")

print("\n" + "=" * 62)
if fallos:
    print(f"FALLOS: {len(fallos)}")
    for f in fallos:
        print("  -", f)
    sys.exit(1)
print("TODOS LOS TESTS PASAN")
print("=" * 62)
