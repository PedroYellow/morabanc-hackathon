"""
Tests del modulo de tesoreria: parsing de extracto, clasificacion, proyeccion
y deteccion de fugas.
"""

import sys, os
from datetime import date
from decimal import Decimal as D

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from engine.tesoreria import (  # noqa: E402
    Movimiento, clasificar_movimiento, normalizar_importe, parse_extracto_csv,
    analizar_tesoreria, proyectar_caja, detectar_fugas, resumen_fugas,
    desglose_categoria,
)

fallos = []


def check(nombre, obtenido, esperado):
    ok = obtenido == esperado
    if not ok:
        fallos.append(f"{nombre}: obtenido {obtenido} != esperado {esperado}")
    print(f"  {'PASS' if ok else 'FAIL'}  {nombre}: {obtenido}"
          + ("" if ok else f" (esperado {esperado})"))
    return ok


# ---------------------------------------------------------------------------
print("\n=== Normalizacion de importes (formatos de extracto reales) ===")
casos_importe = [
    ("1.234,56", D("1234.56"), "formato europeo"),
    ("1234.56", D("1234.56"), "formato anglosajon"),
    ("-45,00", D("-45.00"), "negativo delante"),
    ("45,00-", D("-45.00"), "negativo detras (formato andorra/estatal)"),
    ("1.234,56-", D("-1234.56"), "negativo detras con miles"),
    ("0,00", D("0"), "cero"),
    ("", D("0"), "vacio"),
    ("12.345.678,90", D("12345678.90"), "millones formato europeo"),
    ("1,234.56", D("1234.56"), "formato anglosajon con coma de miles"),
    ("78,90", D("78.90"), "decimal simple"),
]
for texto, esperado, nota in casos_importe:
    check(f"importe '{texto}' ({nota})", normalizar_importe(texto), esperado)

# ---------------------------------------------------------------------------
print("\n=== Clasificacion de conceptos ===")
casos_cat = [
    ("CASS cotitzacio treball per compte propi", "seguridad_social"),
    ("Impost IGI trimestre", "impuestos"),
    ("Lloguer coworking", "alquiler"),
    ("Electricitat ENEL", "suministros"),
    ("Suscripcion ADOBE CREATIVE CLOUD", "herramientas"),
    ("NOMINA ADMINISTRATIVA SL", "nomina"),
    ("Sous empleat", "nomina"),
    ("Compra mercaderia", "material"),
    ("Gasoil Repsol", "transporte"),
]
for concepto, esperado in casos_cat:
    cat, met, conf = clasificar_movimiento(concepto)
    check(f"categoria '{concepto[:34]}'", cat, esperado)

cat, met, conf = clasificar_movimiento("Suscripcion ADOBE CREATIVE CLOUD")
check("metodico suscripcion", met, "suscripcion")
cat, met, conf = clasificar_movimiento("NOMINA ADMINISTRATIVA SL")
check("metodico payroll", met, "payroll")
cat, met, conf = clasificar_movimiento("CASS cotitzacio treball per compte propi")
check("metodico social_security", met, "social_security")
cat, met, conf = clasificar_movimiento("Texto sin ninguna pista")
check("sin pista -> confianza baja", conf <= D("0.5"), True)

# ---------------------------------------------------------------------------
print("\n=== Parsing de extracto CSV ===")
CSV_EJEMPLO = """Fecha;Concepto;Importe
03/10/2025;FACTURA SERVICIOS;2.750,00
04/10/2025;NETFLIX.COM;-12,99
05/10/2025;Lloguer coworking;-450,00
15/11/2025;CASS cotitzacio;-587,95
"""
movs = parse_extracto_csv(CSV_EJEMPLO)
check("movimientos parseados", len(movs), D("4"))
check("primer movimiento fecha", movs[0].fecha, date(2025, 10, 3))
check("primer movimiento importe", movs[0].importe, D("2750.00"))
check("negativo parseado", movs[1].importe, D("-12.99"))
check("ordenado por fecha", movs[-1].fecha, date(2025, 11, 15))
check("renta neta calculada", sum(m.importe for m in movs), D("1699.06"))

# Formato con debe/haber
CSV_DEBE_HABER = """Fecha,Concepto,Debe,Haber
03/10/2025,Factura A,,1500.00
04/10/2025,Gasto B,320.00,
"""
movs2 = parse_extracto_csv(CSV_DEBE_HABER)
check("debe/haber: ingresos", movs2[0].importe, D("1500.00"))
check("debe/haber: gastos", movs2[1].importe, D("-320.00"))

# ---------------------------------------------------------------------------
print("\n=== Analisis de tesoreria ===")
movs_test = [
    Movimiento(date(2026, 1, 5), "Factura clientes", D("3000")),
    Movimiento(date(2026, 1, 10), "Lloguer", D("-1200")),
    Movimiento(date(2026, 2, 5), "Factura clientes", D("3500")),
    Movimiento(date(2026, 2, 10), "Lloguer", D("-1200")),
    Movimiento(date(2026, 3, 5), "Factura clientes", D("3200")),
    Movimiento(date(2026, 3, 10), "Lloguer", D("-1200")),
]
t = analizar_tesoreria(movs_test)
check("ingresos totales", t["ingresos_totales"], D("9700.00"))
check("gastos totales", t["gastos_totales"], D("3600.00"))
check("flujo neto", t["flujo_neto"], D("6100.00"))
check("ingresos/mes", t["ingresos_mes"], D("3233.33"))
check("gastos/mes", t["gastos_mes"], D("1200.00"))
check("categoria alquiler presente", "alquiler" in t["por_categoria"], True)

# ---------------------------------------------------------------------------
print("\n=== Proyeccion de caja ===")
proy = proyectar_caja(movs_test, saldo_inicial=D("5000"), meses=6)
check("6 meses proyectados", len(proy.meses), D("6"))
check("mes 1 saldo", proy.meses[0]["saldo"], D("7033.33"))
check("sin quiebre con este ritmo", proy.mes_quiebre, None)

# Caso con quiebre: gasto alto
movs_roto = [
    Movimiento(date(2026, 1, 5), "Factura clientes", D("2000")),
    Movimiento(date(2026, 1, 10), "Lloguer", D("-3000")),
    Movimiento(date(2026, 2, 5), "Factura clientes", D("2000")),
    Movimiento(date(2026, 2, 10), "Lloguer", D("-3000")),
]
# Con 5.000 € de saldo y -1.000 €/mes de flujo, la caja llega a 0 en el mes 5
# y se vuelve negativa en el mes 6 (saldo -1.000 €).
proy2 = proyectar_caja(movs_roto, saldo_inicial=D("5000"), meses=8)
check("quiebre detectado en el mes 6", proy2.mes_quiebre, 6)
check("deuda en el mes del quiebre = 1.000 €", proy2.deuda_maxima, D("1000.00"))
check("deuda al final del horizonte = 3.000 €", proy2.deuda_final, D("3000.00"))
print(f"       {proy2.resumen}")

# Con decision puntual (contratacion)
proy3 = proyectar_caja(
    movs_test,
    saldo_inicial=D("5000"),
    meses=6,
    decisiones=[{"mes": 2, "nombre": "Contratacion", "importe": -28800}],
)
check("evento registrado en mes 2", "Contratacion" in proy3.meses[1]["eventos"], True)
check("saldo cae tras el evento", proy3.meses[2]["saldo"] < proy3.meses[0]["saldo"], True)

# ---------------------------------------------------------------------------
print("\n=== Deteccion de fugas ===")
# Suscripcion repetida 6 meses
movs_fuga = []
for m in range(6):
    movs_fuga.append(Movimiento(date(2026, m + 1, 5), "Suscripcion NOTION", D("-12.00")))
    movs_fuga.append(Movimiento(date(2026, m + 1, 5), "Suscripcion FIGMA", D("-15.00")))
    movs_fuga.append(Movimiento(date(2026, m + 1, 20), "Factura clientes", D("4000")))

fugas = detectar_fugas(movs_fuga)
tipos = {f.tipo for f in fugas}
check("detecta suscripciones", "suscripcion" in tipos, True)
check("n de fugas = 2", len(fugas), D("2"))
resumen = resumen_fugas(fugas)
check("recuperable anual", resumen["recuperable_anual"], D("324.00"))  # 27*12
print(f"       {resumen['mensaje']}")

# Cobro duplicado
movs_dup = [
    Movimiento(date(2026, 3, 10), "Comissio gestoria", D("-180.00")),
    Movimiento(date(2026, 3, 12), "Comissio gestoria", D("-180.00")),
]
fugas2 = detectar_fugas(movs_dup)
check("detecta cobro duplicado", any(f.tipo == "cobro_duplicado" for f in fugas2), True)

# Sin fugas
check("sin fugas -> vacio", detectar_fugas(movs_test), [])
check("resumen vacio", resumen_fugas([])["n_fugas"], D("0"))

# ---------------------------------------------------------------------------
print("\n=== Integracion: los 3 perfiles demo generados ===")
data_dir = os.path.join(os.path.dirname(__file__), "..", "data")
for nombre in ["demo_freelance.csv", "demo_comercio.csv", "demo_freelancer_contratar.csv"]:
    ruta = os.path.join(data_dir, nombre)
    if not os.path.exists(ruta):
        print(f"  SKIP  {nombre} (no generado)")
        continue
    with open(ruta, encoding="utf-8") as f:
        contenido = f.read()
    movs = parse_extracto_csv(contenido)
    check(f"{nombre}: parseados", len(movs) > 50, True)
    t = analizar_tesoreria(movs)
    check(f"{nombre}: flujo neto", t["flujo_neto"] != D("0"), True)
    fg = detectar_fugas(movs)
    print(f"       {nombre}: flujo {t['flujo_neto']} €, {len(fg)} fugas detectadas")

print("\n" + "=" * 62)
if fallos:
    print(f"FALLOS: {len(fallos)}")
    for f in fallos:
        print("  -", f)
    sys.exit(1)
print("TODOS LOS TESTS PASAN")
print("=" * 62)
