#!/usr/bin/env python3
"""
Prueba del agente contra Bedrock REAL (no mock).
=================================================
Este es el script que se ejecuta el dia 7 con las credenciales de la cuenta
del equipo. Hasta ahora el agente solo se habia probado en modo mock.

Uso:
    export AWS_ACCESS_KEY_ID=...
    export AWS_SECRET_ACCESS_KEY=...
    export AWS_SESSION_TOKEN=...
    export AWS_DEFAULT_REGION=us-east-1
    python3 scripts/test_bedrock_live.py

Devuelve 0 si el agente funciona contra Bedrock, 1 si no.

Que comprueba:
  1. Que las credenciales son validas (sts get-caller-identity)
  2. Que la region por defecto existe y tiene Bedrock
  3. Que el modelo configurado existe y esta ACTIVE
  4. Que el agente ELIGE LA HERRAMIENTA correcta (tool-use de verdad)
  5. Que el numero de la respuesta coincide con el del motor (el LLM no
     calcula: si difiere, algo esta mal)
  6. Que las 11 herramientas del motor responden sin errores
"""

import os
import sys
from decimal import Decimal as D

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

fallos = []
n = 0


def check(nombre, ok, extra=""):
    global n
    n += 1
    print(f"  {'PASS' if ok else 'FAIL'}  {nombre}{(' -> ' + str(extra)) if extra else ''}")
    if not ok:
        fallos.append(nombre)


def banner(t):
    print()
    print("=" * 70)
    print(f"  {t}")
    print("=" * 70)


# --------------------------------------------------------------------------
banner("1. Credenciales")
# --------------------------------------------------------------------------

import boto3  # noqa: E402
from botocore.exceptions import ClientError  # noqa: E402

region = (
    os.environ.get("AWS_REGION")
    or os.environ.get("AWS_DEFAULT_REGION")
    or "us-east-1"
)
print(f"  region: {region}")

try:
    sts = boto3.client("sts", region_name=region)
    ident = sts.get_caller_identity()
    print(f"  cuenta: {ident['Account']}")
    print(f"  rol:    {ident['Arn'].split('/')[-2] if '/' in ident['Arn'] else ident['Arn']}")
    check("credenciales validas", True)
except ClientError as e:
    check("credenciales validas", False, e.response["Error"]["Message"])
    print("\n  Las credenciales no son validas o la sesion ha expirado.")
    print("  Las claves de AWS SSO (ASIA*) expiran: pide credenciales nuevas")
    print("  a MoraBanc (+376 884 884) o renueva la sesion del workshop.")
    sys.exit(1)


# --------------------------------------------------------------------------
banner("2. Modelos disponibles")
# --------------------------------------------------------------------------

from agent.bedrock_agent import MODEL_ID, TOOL_SCHEMAS, TOOL_IMPLS  # noqa: E402

try:
    br_control = boto3.client("bedrock", region_name=region)
    modelos = br_control.list_foundation_models()
    ids = [m["modelId"] for m in modelos.get("modelSummaries", [])]
    check("Bedrock accesible", True, f"{len(ids)} modelos")

    if MODEL_ID in ids:
        est = next(m for m in modelos["modelSummaries"] if m["modelId"] == MODEL_ID)
        check(f"el modelo {MODEL_ID} existe", True)
        check(f"el modelo {MODEL_ID} esta ACTIVE",
              est.get("modelLifecycle", {}).get("status") == "ACTIVE",
              est.get("modelLifecycle", {}).get("status"))
    else:
        check(f"el modelo {MODEL_ID} existe", False, "no esta en la lista")
        print("     Modelos de texto disponibles:")
        for m in modelos.get("modelSummaries", [])[:12]:
            if "TEXT" in m.get("inputModalities", []):
                print(f"       - {m['modelId']} ({m.get('modelLifecycle',{}).get('status')})")
except ClientError as e:
    check("Bedrock accesible", False, e.response["Error"]["Message"])
    sys.exit(1)


# --------------------------------------------------------------------------
banner("3. Tool-use real (el agente elige la herramienta)")
# --------------------------------------------------------------------------

from agent.bedrock_agent import AgenteFinanciero, ContextoEmpresa  # noqa: E402
from engine.fiscal_andorra import tramo_cass_para, cass_anual  # noqa: E402

ctx = ContextoEmpresa(
    movimientos=[],
    saldo_actual=D("8500"),
    renta_neta_anual=D("30000"),
    margen_bruto=D("0.70"),
)
agente = AgenteFinanciero(ctx, mock=False)
check("el agente esta en modo real (no mock)", agente.mock is False)

try:
    r = agente.preguntar(
        "¿Cuánto cotizo a la CASS con una renta neta de 30.000 euros?"
    )
    herramientas = [h["tool"] for h in r["herramientas"]]
    check("Bedrock responde", True)
    check("el agente invoca una herramienta del motor", len(herramientas) > 0,
          ", ".join(herramientas))
    check("el agente elige la herramienta correcta para CASS",
          "tramo_cass" in herramientas, ", ".join(herramientas))
    check("la respuesta no esta vacia", len(r["respuesta"]) > 40)

    # El numero viene del motor, no del LLM. Comparamos.
    esperado = cass_anual(tramo_cass_para(D("30000")))
    print(f"     cuota anual del motor: {esperado} €")
    print(f"     respuesta: {r['respuesta'][:220]}")

    # El LLM no puede inventar: el numero debe aparecer en la respuesta.
    #
    # OJO: el front y el agente escriben los importes en formato EUROPEO
    # (punto de millares, coma decimal): "7.055,40". Comparar solo con
    # f"{esperado:.2f}" ("7055.40") daria un falso negativo: el numero
    # esta bien, lo que cambia es la notacion.
    def variantes(n: float) -> list[str]:
        """Todas las formas en las que puede aparecer un importe."""
        return [
            f"{n:.2f}",                       # 7055.40  (anglosajon)
            f"{n:,.2f}",                     # 7,055.40  (anglosajon)
            f"{n:.2f}".replace(".", ","),     # 7055,40   (europeo sin millares)
            f"{n:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
            # 7.055,40 (europeo con punto de millares)
            f"{n:.2f}".replace(".", ","),
            f"{n:,.0f}",                     # 7,055
            f"{n:.0f}",                      # 7055
        ]

    numero_ok = any(v in r["respuesta"] for v in variantes(float(esperado)))
    check("el numero de la respuesta coincide con el del motor", numero_ok,
          f"esperado {esperado} € | variantes: {variantes(float(esperado))[:4]}")

except Exception as e:  # noqa: BLE001
    check("Bedrock responde", False, f"{type(e).__name__}: {str(e)[:200]}")
    print()
    print("  Diagnostico:")
    print("    - AccessDeniedException  -> el modelo no esta habilitado en la cuenta")
    print("    - ValidationException    -> el modelo no soporta tool-use")
    print("    - ResourceNotFound       -> BEDROCK_MODEL_ID mal escrito")
    print("    - UnrecognizedClient     -> credenciales expiradas o region incorrecta")
    sys.exit(1)


# --------------------------------------------------------------------------
banner("4. Las 11 herramientas del motor")
# --------------------------------------------------------------------------

from engine.tesoreria import parse_extracto_csv  # noqa: E402

csv = open(os.path.join(RAIZ, "data", "demo_freelancer_contratar.csv"),
           encoding="utf-8").read()
ctx2 = ContextoEmpresa(
    movimientos=parse_extracto_csv(csv),
    saldo_actual=D("3200"),
    renta_neta_anual=D("28000"),
    margen_bruto=D("0.70"),
    fecha_consejo=__import__("datetime").date(2026, 7, 1),
)

from engine.cierre import construir_consejos, cerrar_consejos, informe_cierre  # noqa: E402
from engine.tesoreria import detectar_fugas  # noqa: E402

casos = {
    "analizar_tesoreria": {},
    "detectar_fugas": {},
    "proyectar_caja": {"meses": 12},
    "tramo_cass": {"renta_neta": 30000},
    "calcular_irpf": {"base_general": 30000},
    "calcular_igi": {"base_imponible": 30000},
    "detectar_crossover_fiscal": {"renta_neta": 45000},
    "simular_contratacion": {"coste_mensual_empleado": 2400, "margen_bruto": 0.70},
    "punto_optimo_facturacion": {},
    "comparar_escenarios": {"renta_a": 30000, "renta_b": 45000},
    "cerrar_ciclo": {},
}

from agent.bedrock_agent import ejecutar_tool  # noqa: E402

for nombre, args in casos.items():
    out = ejecutar_tool(nombre, ctx2, args)
    res = out.get("resultado", {})
    tiene_error = isinstance(res, dict) and res.get("error")
    check(f"herramienta {nombre}", not tiene_error,
          res.get("error") if tiene_error else "ok")

check("las 11 herramientas estan en el esquema de Bedrock",
      len(TOOL_SCHEMAS) == len(casos), f"{len(TOOL_SCHEMAS)} esquemas")
check("las 11 herramientas tienen implementacion",
      len(TOOL_IMPLS) == len(casos), f"{len(TOOL_IMPLS)} implementaciones")


# --------------------------------------------------------------------------
banner("5. El bucle de cierre con el motor")
# --------------------------------------------------------------------------

fugas = detectar_fugas(ctx2.movimientos)
consejos = construir_consejos(fugas, fecha=__import__("datetime").date(2026, 7, 1))
inf = informe_cierre(cerrar_consejos(consejos, ctx2.movimientos))
check("el bucle de cierre produce un veredicto", inf["n_consejos"] > 0,
      f"{inf['cumplidos']} cumplidos / {inf['incumplidos']} incumplidos")
print(f"     {inf['resumen']}")


# --------------------------------------------------------------------------
print()
if fallos:
    print(f"FALLOS: {len(fallos)} -> {fallos}")
    sys.exit(1)
print(f"BEDROCK EN VIVO FUNCIONA ({n} comprobaciones)")
