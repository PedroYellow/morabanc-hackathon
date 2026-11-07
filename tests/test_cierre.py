#!/usr/bin/env python3
"""
Tests del bucle de cierre (engine/cierre.py).
=================================================
El modulo mas nuevo del motor y el que mas se usa en el pitch: comprueba que
el sistema se reporte sobre su propio consejo pasado.

Cada test imprime PASS/FAIL con el formato que espera scripts/verificar.sh.
"""

import os
import sys
from datetime import date, timedelta
from decimal import Decimal as D

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

from engine.tesoreria import Movimiento, parse_extracto_csv, detectar_fugas
from engine.cierre import (
    Consejo,
    TIPO_CONSEJO_SUSCRIPCION,
    construir_consejos,
    cerrar_consejos,
    guardar_consejos,
    cargar_consejos,
    informe_cierre,
    _coincide_concepto,
    MIN_MOVIMIENTOS_EVALUABLES,
)

fallos = []
n = 0


def check(nombre, ok, extra=""):
    global n
    n += 1
    print(f"  {'PASS' if ok else 'FAIL'}  {nombre}{(' -> ' + str(extra)) if extra else ''}")
    if not ok:
        fallos.append(nombre)


def mov(fecha, concepto, importe, cat=None):
    return Movimiento(fecha=fecha, concepto=concepto, importe=D(str(importe)))


BASE = date(2026, 1, 10)


# ==========================================================================
print("\n=== CONSTRUCCION DE CONSEJOS ===")
# ==========================================================================

# 5 meses con la misma suscripcion -> fuga de tipo 'suscripcion'
movs_hist = [
    mov(BASE + timedelta(days=30 * i), "NETFLIX.COM 12,99", -12.99)
    for i in range(5)
]
fugas = detectar_fugas(movs_hist)
check("detecta la suscripcion", any(f.tipo == "suscripcion" for f in fugas),
      [f.tipo for f in fugas])

consejos = construir_consejos(fugas, fecha=BASE)
check("genera un consejo", len(consejos) == 1, len(consejos))
if consejos:
    c = consejos[0]
    check("el consejo es de tipo suscripcion", c.tipo == TIPO_CONSEJO_SUSCRIPCION, c.tipo)
    check("el consejo guarda el importe esperado", c.esperado_mensual == D("12.99"),
          c.esperado_mensual)
    check("el consejo guarda la fecha", c.fecha == BASE, c.fecha)
    check("el consejo tiene regla citada", bool(c.regla), c.regla[:40])

# Un consejo de tipo no-suscripcion no debe generar nada (las fugas de tipo
# 'cobro_duplicado' no son verificables como suscripcion)
fugas_dup = detectar_fugas([
    mov(BASE, "GESTORIA 300,00", -300.0),
    mov(BASE + timedelta(days=2), "GESTORIA 300,00", -300.0),
])
check("no crea consejo de un cobro duplicado",
      len(construir_consejos(fugas_dup, fecha=BASE)) == 0,
      [f.tipo for f in fugas_dup])


# ==========================================================================
print("\n=== VERIFICACION: CUMPLIDO ===")
# ==========================================================================

# Tras el consejo, la suscripcion desaparece y hay otros movimientos.
movs_post = [
    mov(BASE + timedelta(days=40), "CLIENTE FACTURA 01", 1800.0),
    mov(BASE + timedelta(days=50), "SUMINISTROS ELECTRICIDAD", -90.0),
    mov(BASE + timedelta(days=65), "CLIENTE FACTURA 02", 2200.0),
    mov(BASE + timedelta(days=80), "ALQUILER OFICINA", -600.0),
]
cierres = cerrar_consejos(consejos, movs_post)
check("produce un cierre", len(cierres) == 1, len(cierres))
if cierres:
    cl = cierres[0]
    check("es evaluable", cl.evaluable is True)
    check("veredicto = cumplido", cl.veredicto == "cumplido", cl.veredicto)
    check("ahorro real = importe esperado", cl.ahorro_real_mensual == D("12.99"),
          cl.ahorro_real_mensual)
    check("desviacion = 0%", cl.desviacion_pct == D("0"), cl.desviacion_pct)
    check("cuenta los meses observados", cl.meses_observados >= 2, cl.meses_observados)


# ==========================================================================
print("\n=== VERIFICACION: INCUMPLIDO ===")
# ==========================================================================

movs_sigue = [
    mov(BASE + timedelta(days=40), "CLIENTE FACTURA 01", 1800.0),
    mov(BASE + timedelta(days=45), "NETFLIX.COM 12,99", -12.99),
    mov(BASE + timedelta(days=55), "CLIENTE FACTURA 02", 2200.0),
    mov(BASE + timedelta(days=70), "NETFLIX.COM 12,99", -12.99),
    mov(BASE + timedelta(days=85), "SUMINISTROS AGUA", -45.0),
]
cierres = cerrar_consejos(consejos, movs_sigue)
if cierres:
    cl = cierres[0]
    check("veredicto = incumplido", cl.veredicto == "incumplido", cl.veredicto)
    check("ahorro real = 0", cl.ahorro_real_mensual == D("0"), cl.ahorro_real_mensual)
    check("desviacion = -100%", cl.desviacion_pct == D("-100"), cl.desviacion_pct)
    check("explica que sigue pagando", "sigue apareciendo" in cl.detalle.get("explicacion", ""),
          cl.detalle.get("explicacion", "")[:60])


# ==========================================================================
print("\n=== VERIFICACION: PARCIAL (subio el precio) ===")
# ==========================================================================

movs_parcial = [
    mov(BASE + timedelta(days=40), "CLIENTE FACTURA 01", 1800.0),
    mov(BASE + timedelta(days=50), "NETFLIX.COM 9,99", -9.99),
    mov(BASE + timedelta(days=60), "CLIENTE FACTURA 02", 2200.0),
    mov(BASE + timedelta(days=75), "NETFLIX.COM 9,99", -9.99),
]
cierres = cerrar_consejos(consejos, movs_parcial)
if cierres:
    cl = cierres[0]
    check("veredicto = parcial", cl.veredicto == "parcial", cl.veredicto)
    check("ahorro real = 3.00", cl.ahorro_real_mensual == D("3.00"),
          cl.ahorro_real_mensual)
    check("desviacion negativa", cl.desviacion_pct < 0, cl.desviacion_pct)


# ==========================================================================
print("\n=== VERIFICACION: SIN DATOS ===")
# ==========================================================================

cierres = cerrar_consejos(consejos, [])
check("sin movimientos -> no evaluable", cierres[0].evaluable is False)
check("sin movimientos -> veredicto sin_datos", cierres[0].veredicto == "sin_datos",
      cierres[0].veredicto)
check("sin movimientos -> ahorro real 0", cierres[0].ahorro_real_mensual == D("0"))

cierres = cerrar_consejos(consejos, movs_post[:1])
check("un solo movimiento -> no evaluable", cierres[0].evaluable is False)
check("mismo veredicto sin_datos", cierres[0].veredicto == "sin_datos",
      cierres[0].veredicto)


# ==========================================================================
print("\n=== INFORME DE CIERRE ===")
# ==========================================================================

inf = informe_cierre(cerrar_consejos(consejos, movs_post))
check("informe cuenta 1 consejo", inf["n_consejos"] == 1, inf["n_consejos"])
check("informe cuenta 1 evaluable", inf["n_evaluables"] == 1, inf["n_evaluables"])
check("informe cuenta 1 cumplido", inf["cumplidos"] == 1, inf["cumplidos"])
check("informe da el ahorro", inf["ahorro_real_mensual"] == "12.99",
      inf["ahorro_real_mensual"])
check("informe tiene resumen en texto", len(inf["resumen"]) > 20, inf["resumen"][:60])

inf_vacio = informe_cierre([])
check("informe sin consejos no revienta", inf_vacio["n_consejos"] == 0)
check("informe sin consejos avisa", "suficientes" in inf_vacio["resumen"],
      inf_vacio["resumen"][:60])

inf_inc = informe_cierre(cerrar_consejos(consejos, movs_sigue))
check("informe con incumplidos lo dice", "No has aplicado" in inf_inc["resumen"],
      inf_inc["resumen"][:60])


# ==========================================================================
print("\n=== PERSISTENCIA ===")
# ==========================================================================

ruta = "/tmp/test_consejos_cierre.json"
guardar_consejos(consejos, ruta)
cargados = cargar_consejos(ruta)
check("guarda y carga la misma cantidad", len(cargados) == len(consejos),
      f"{len(cargados)} vs {len(consejos)}")
if cargados:
    check("conserva el importe",
          cargados[0].esperado_mensual == consejos[0].esperado_mensual,
          cargados[0].esperado_mensual)
    check("conserva la fecha", cargados[0].fecha == BASE, cargados[0].fecha)
    check("conserva la clave", cargados[0].clave == consejos[0].clave)
os.remove(ruta)


# ==========================================================================
print("\n=== COINCIDENCIA DE CONCEPTOS ===")
# ==========================================================================

check("coincide exacto", _coincide_concepto("NETFLIX", "netflix") is True)
check("coincide contenido", _coincide_concepto("NETFLIX.COM 12,99", "NETFLIX") is True)
check("coincide por token",
      _coincide_concepto("PAGO NETFLIX 12,99", "Netflix") is True)
check("no coincide distinto", _coincide_concepto("SPOTIFY", "NETFLIX") is False)
check("no coincide con vacio", _coincide_concepto("", "NETFLIX") is False)


# ==========================================================================
print("\n=== NO REGRESION: EL RESTO DEL MOTOR SIGUE FUNCIONANDO ===")
# ==========================================================================

csv_demo = open(os.path.join(RAIZ, "data", "demo_freelancer_contratar.csv"),
                encoding="utf-8").read()
movs_demo = parse_extracto_csv(csv_demo)
check("el extracto demo sigue parseando", len(movs_demo) > 100, len(movs_demo))
fugas_demo = detectar_fugas(movs_demo)
check("las fugas demo siguen detectandose", len(fugas_demo) > 0, len(fugas_demo))
consejos_demo = construir_consejos(fugas_demo, fecha=date(2026, 1, 1))
check("las fugas demo producen consejos", len(consejos_demo) > 0, len(consejos_demo))
cierres_demo = cerrar_consejos(consejos_demo, movs_demo)
check("los cierres demo no revientan", len(cierres_demo) == len(consejos_demo),
      f"{len(cierres_demo)} vs {len(consejos_demo)}")


print()
if fallos:
    print(f"FALLOS: {len(fallos)} -> {fallos}")
    sys.exit(1)
print(f"TODOS LOS TESTS PASAN ({n})")
