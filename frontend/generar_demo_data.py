#!/usr/bin/env python3
"""
Genera los datos precalculados del modo demo para el frontend.
==============================================================
El motor de decisiones (Python) corre aqui y vuelca su salida a JSON.
El frontend consume ese JSON: los numeros del modo demo son EXACTAMENTE
los mismos que devuelve la API en AWS, porque los genera el mismo motor.

No hay logica duplicada en JavaScript: el JS no calcula nada.

Uso:
    python3 frontend/generar_demo_data.py
"""

import json
import os
import sys
from dataclasses import asdict
from datetime import date
from decimal import Decimal

D = Decimal

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

from engine.tesoreria import (  # noqa: E402
    analizar_tesoreria, detectar_fugas, resumen_fugas, proyectar_caja,
    parse_extracto_csv,
)
from engine.fiscal_andorra import (  # noqa: E402
    tramo_cass_para, cass_anual, irpf, igi, crossover_cass,
    simular_contratacion, punto_optimo_facturacion,
)

DESTINO = os.path.join(RAIZ, "frontend", "data")

PERFILES = {
    "freelance": {
        "csv": "demo_freelance.csv",
        "saldo": D("8500"), "renta": D("30000"), "margen": D("0.70"),
        "actividad": "Freelance de servicios",
    },
    "contratar": {
        "csv": "demo_freelancer_contratar.csv",
        "saldo": D("3200"), "renta": D("28000"), "margen": D("0.70"),
        "actividad": "Freelancer de servicios",
    },
    "comercio": {
        "csv": "demo_comercio.csv",
        "saldo": D("14200"), "renta": D("45000"), "margen": D("0.35"),
        "actividad": "Comercio con tienda local",
    },
    "cierre": {
        "csv": "demo_freelancer_cierre.csv",
        "saldo": D("6100"), "renta": D("30000"), "margen": D("0.70"),
        "actividad": "Freelance de servicios",
        # Fecha del consejo: 1 de julio de 2026 (ver data/generar_demo.py).
        "fecha_consejo": "2026-07-01",
    },
}


def jsonable(o):
    if isinstance(o, Decimal):
        return float(o)
    if isinstance(o, date):
        return o.isoformat()
    if hasattr(o, "__dataclass_fields__"):
        return {k: jsonable(v) for k, v in asdict(o).items()}
    if isinstance(o, dict):
        return {k: jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [jsonable(v) for v in o]
    return o


def construir(clave, cfg):
    ruta = os.path.join(RAIZ, "data", cfg["csv"])
    with open(ruta, encoding="utf-8") as f:
        movs = parse_extracto_csv(f.read())

    t = analizar_tesoreria(movs)
    fugas = detectar_fugas(movs)
    proy = proyectar_caja(movs, saldo_inicial=cfg["saldo"], meses=12)
    tr = tramo_cass_para(cfg["renta"])
    ir = irpf(base_general=cfg["renta"])
    cr = crossover_cass(cfg["renta"])
    g = igi(cfg["renta"])
    sim = simular_contratacion(
        renta_neta_actual=cfg["renta"],
        margen_bruto=cfg["margen"],
        coste_nuevo_empleado_mensual=D("2400"),
    )
    po = punto_optimo_facturacion(cfg["renta"], cfg["margen"])

    # El cierre del bucle solo tiene sentido cuando hay fecha de consejo:
    # el motor compara los cargos posteriores a esa fecha con los de antes.
    cierre = None
    if cfg.get("fecha_consejo"):
        from engine.cierre import construir_consejos, cerrar_consejos, informe_cierre
        fecha = date.fromisoformat(cfg["fecha_consejo"])
        consejos = construir_consejos(fugas, fecha=fecha)
        cierre = informe_cierre(cerrar_consejos(consejos, movs))

    return {
        "etiqueta": cfg["actividad"],
        "saldo": float(cfg["saldo"]),
        "renta": float(cfg["renta"]),
        "margen": float(cfg["margen"]),
        "actividad": cfg["actividad"],
        "n_movimientos": len(movs),
        "periodo": t["periodo"],
        "tesoreria": {
            "ingresos_totales": float(t["ingresos_totales"]),
            "gastos_totales": float(t["gastos_totales"]),
            "flujo_neto": float(t["flujo_neto"]),
            "ingresos_mes": float(t["ingresos_mes"]),
            "gastos_mes": float(t["gastos_mes"]),
            "por_categoria": {k: float(v) for k, v in t["por_categoria"].items()},
        },
        "fugas": jsonable(resumen_fugas(fugas)),
        "proyeccion": {
            "meses": jsonable(proy.meses),
            "mes_quiebre": proy.mes_quiebre,
            "deuda_en_quiebre": float(proy.deuda_maxima),
            "deuda_al_final": float(proy.deuda_final),
            "ultimo_saldo_positivo": float(proy.ultimo_saldo_positivo),
            "mes_ultimo_positivo": proy.mes_ultimo_positivo,
            "resumen": proy.resumen,
        },
        "cass": {
            "tramo": tr.nombre,
            "base_cotizacion": float(tr.base),
            "cuota_mensual": float(tr.cuota_mensual),
            "rama_general": float(tr.rama_general),
            "rama_jubilacion": float(tr.rama_jubilacion),
            "cuota_anual": float(cass_anual(tr)),
            "condicion": tr.condicion,
        },
        "irpf": {
            "base_tributable": float(ir.base_general),
            "cuota_total": float(ir.cuota_total),
            "bonificacion": float(ir.bonificacion_actividades),
            "tipo_efectivo": float(ir.tipo_efectivo),
        },
        "igi": {"cuota": float(g.cuota), "tipo": float(g.tipo)},
        "crossover": jsonable(asdict(cr)),
        "simular_contratacion": jsonable(sim),
        "punto_optimo": jsonable(po),
        "cierre": cierre,
    }


def main():
    os.makedirs(DESTINO, exist_ok=True)
    salida = {}
    for clave, cfg in PERFILES.items():
        data = construir(clave, cfg)
        salida[clave] = data
        print(f"  {clave}: {data['n_movimientos']} movimientos · "
              f"flujo {data['tesoreria']['flujo_neto']:,.2f} € · "
              f"{data['fugas']['n_fugas']} fugas · "
              f"quiebre mes {data['proyeccion']['mes_quiebre']}")

    # Copiamos los CSV al directorio del front
    import shutil
    for cfg in PERFILES.values():
        shutil.copy(os.path.join(RAIZ, "data", cfg["csv"]),
                    os.path.join(DESTINO, cfg["csv"]))

    ruta_json = os.path.join(DESTINO, "demo_data.json")
    with open(ruta_json, "w", encoding="utf-8") as f:
        json.dump(salida, f, ensure_ascii=False, separators=(",", ":"))

    print(f"\n  → {ruta_json} ({os.path.getsize(ruta_json)} bytes)")
    print("  → CSV copiados a", DESTINO)


if __name__ == "__main__":
    main()
