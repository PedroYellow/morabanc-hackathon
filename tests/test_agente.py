"""
Tests del agente de Bedrock (modo mock).

Verifican tres cosas:
  1. El router elige la herramienta correcta para cada tipo de pregunta.
  2. Los numeros que devuelve el agente son EXACTAMENTE los del motor.
  3. INVARIANTE CRITICA: toda respuesta que contiene un numero debe
     haber pasado por una herramienta. (El LLM no calcula.)
"""

import sys, os, re, json
from decimal import Decimal as D

RAIZ = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, RAIZ)

from agent.bedrock_agent import (  # noqa: E402
    AgenteFinanciero, ContextoEmpresa, ejecutar_tool,
    TOOL_SCHEMAS, TOOL_IMPLS, SYSTEM_PROMPT,
)
from engine.fiscal_andorra import (  # noqa: E402
    tramo_cass_para, irpf, crossover_cass, simular_contratacion,
)
from engine.tesoreria import (  # noqa: E402
    analizar_tesoreria, detectar_fugas, resumen_fugas, parse_extracto_csv,
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
print("\n=== Contexto de empresa ===")
ruta_csv = os.path.join(RAIZ, "data", "demo_freelancer_contratar.csv")
with open(ruta_csv, encoding="utf-8") as f:
    contenido = f.read()

ctx = ContextoEmpresa.desde_csv(
    contenido,
    saldo_actual=D("8500"),
    renta_neta_anual=D("30000"),
    margen_bruto=D("0.70"),
    actividad="Freelance de servicios",
)
check("movimientos cargados", len(ctx.movimientos) > 100, True)
check("renta neta cargada", ctx.renta_neta_anual, D("30000"))

# ---------------------------------------------------------------------------
print("\n=== Esquemas de herramientas (contrato con Bedrock) ===")
nombres_esquemas = {t["toolSpec"]["name"] for t in TOOL_SCHEMAS}
check("mismo numero de tools que implementaciones", len(TOOL_SCHEMAS), len(TOOL_IMPLS))
check("todos los esquemas tienen implementacion", nombres_esquemas <= set(TOOL_IMPLS), True)
check("todas las implementaciones tienen esquema", set(TOOL_IMPLS) <= nombres_esquemas, True)
for t in TOOL_SCHEMAS:
    spec = t["toolSpec"]
    check(f"schema valido: {spec['name'][:28]}",
          all(k in spec for k in ("name", "description", "inputSchema")), True)

# ---------------------------------------------------------------------------
print("\n=== El router elige la herramienta correcta ===")
agente = AgenteFinanciero(ctx, mock=True)

casos_router = [
    ("¿Puedo contratar a alguien a 2400 euros al mes?", "simular_contratacion"),
    ("¿Cuánto me gasto y dónde se va el dinero?", "analizar_tesoreria"),
    ("¿Cuánto se me escapa cada mes?", "detectar_fugas"),
    ("¿Cuántos meses me aguanto en caja?", "proyectar_caja"),
    ("¿Cuándo salta mi tramo de cotización?", "detectar_crossover_fiscal"),
    ("¿Cuánto de IRPF pago?", "calcular_irpf"),
    ("¿Cuánto de impuestos pago?", "calcular_irpf"),
    ("¿Cuánto cotizo a la CASS?", "tramo_cass"),
    ("¿Cuánto de IGI pago?", "calcular_igi"),
    ("¿Cuánto me conviene facturar?", "punto_optimo_facturacion"),
    ("¿Cuánto se me está escapando cada mes?", "detectar_fugas"),
    ("¿Cuánto me queda de caja cada mes?", "proyectar_caja"),
    ("¿Y si el sueldo es de 2.900 en vez de 2.400?", "simular_contratacion"),
    ("¿Cuánto cotizo a la CASS?", "tramo_cass"),
    ("¿Cuándo salta mi tramo?", "detectar_crossover_fiscal"),
]
for pregunta, esperado in casos_router:
    r = agente.preguntar(pregunta)
    check(f"router: '{pregunta[:34]}'", r["herramientas"][0]["tool"], esperado)

# ---------------------------------------------------------------------------
print("\n=== Los numeros coinciden EXACTAMENTE con el motor ===")

# CASS
r = agente.preguntar("¿Cuánto cotizo a la CASS con 30000 euros de renta?")
t_real = tramo_cass_para(D("30000"))
check("cuota CASS del agente", r["herramientas"][0]["resultado"]["cuota_mensual"], float(t_real.cuota_mensual))
check("tramo CASS del agente", r["herramientas"][0]["resultado"]["tramo"], t_real.nombre)

# IRPF
r = agente.preguntar("¿Cuánto de IRPF pago con 30000 euros?")
i_real = irpf(base_general=D("30000"))
check("cuota IRPF del agente", r["herramientas"][0]["resultado"]["cuota_total"], float(i_real.cuota_total))
check("bonificacion del agente", r["herramientas"][0]["resultado"]["bonificacion_art46"],
      float(i_real.bonificacion_actividades))

# Contratacion
r = agente.preguntar("¿Puedo contratar a alguien a 2400 euros al mes?")
s_real = simular_contratacion(
    renta_neta_actual=D("30000"),
    margen_bruto=D("0.70"),
    coste_nuevo_empleado_mensual=D("2400"),
)
check("facturacion adicional del agente",
      r["herramientas"][0]["resultado"]["facturacion_adicional_para_cubrirlo"],
      float(s_real["facturacion_adicional_para_cubrirlo"]))
check("coste anual del agente",
      r["herramientas"][0]["resultado"]["coste_nuevo_empleado_anual"],
      float(s_real["coste_nuevo_empleado_anual"]))

# Crossover
r = agente.preguntar("¿Cuándo salta mi tramo? Con 45000 euros")
c_real = crossover_cass(D("45000"))
check("crossover del agente", r["herramientas"][0]["resultado"]["tipo"], c_real.tipo)
check("delta anual del agente", r["herramientas"][0]["resultado"]["delta_anual_cass"],
      float(c_real.delta_anual))

# ---------------------------------------------------------------------------
print("\n=== INVARIANTE: toda respuesta numerica viene de una herramienta ===")
preguntas = [
    "¿Puedo contratar a alguien a 2400 euros?",
    "¿Cuánto cotizo a la CASS?",
    "¿Cuánto de IRPF pago?",
    "¿Cuántos meses me aguanto?",
    "¿Cuánto me conviene facturar?",
    "¿Cuánto me gasto?",
]
for p in preguntas:
    r = agente.preguntar(p)
    tiene_tool = len(r["herramientas"]) > 0
    check(f"'{p[:38]}' usa herramienta", tiene_tool, True)
    # Cada llamada debe traer la regla aplicada
    reglas = all(h.get("regla") for h in r["herramientas"])
    check(f"'{p[:38]}' cita la regla", reglas, True)

# ---------------------------------------------------------------------------
print("\n=== Toda respuesta del agente cita la regla aplicada ===")
for p in preguntas:
    r = agente.preguntar(p)
    check(f"'{p[:38]}' menciona 'Regla aplicada'", "Regla aplicada" in r["respuesta"], True)

# ---------------------------------------------------------------------------
print("\n=== El system prompt prohibe calcular ===")
check("prohibe calcular", "NUNCA calcules" in SYSTEM_PROMPT, True)
check("exige citar la regla", "regla" in SYSTEM_PROMPT.lower(), True)
check ("exige la herramienta", "herramienta" in SYSTEM_PROMPT.lower(), True)

# ---------------------------------------------------------------------------
print("\n=== Herramientas con error devuelven error controlado ===")
ctx_sin = ContextoEmpresa(movimientos=[], renta_neta_anual=None)
out = ejecutar_tool("tramo_cass", ctx_sin, {})
check("error controlado si falta la renta", "error" in out["resultado"], True)
out2 = ejecutar_tool("herramienta_inexistente", ctx_sin, {})
check("error controlado si la tool no existe", "error" in out2["resultado"], True)

# ---------------------------------------------------------------------------
print("\n=== Traza: se registra cada llamada a herramienta ===")
ag2 = AgenteFinanciero(ctx, mock=True)
ag2.preguntar("¿Puedo contratar a alguien a 2400 euros?")
ag2.preguntar("¿Cuánto cotizo a la CASS?")
check("traza con 2 llamadas", len(ag2.trace), 2)
check("traza con herramienta y regla",
      all("tool" in t and "regla" in t for t in ag2.trace), True)

# ---------------------------------------------------------------------------
print("\n=== El JSON de salida es serializable (para la Lambda) ===")
r = agente.preguntar("¿Cuánto cotizo a la CASS con 30000 euros?")
try:
    s = json.dumps(r, ensure_ascii=False, default=str)
    check("respuesta serializable", len(s) > 50, True)
except Exception as e:
    check("respuesta serializable", f"ERROR {e}", True)

# ---------------------------------------------------------------------------
print("\n=== La falta de datos se pide, no revienta ===")
ctx_vacio = ContextoEmpresa(movimientos=[], renta_neta_anual=None)
ag_vacio = AgenteFinanciero(ctx_vacio, mock=True)
r = ag_vacio.preguntar("¿Puedo contratar a alguien a 2400 euros?")
check("no crashea sin renta neta", r["respuesta"] != "", True)
check("pide el dato que falta", "Necesito" in r["respuesta"], True)
check("no dice que sea un error 500", "Traceback" not in r["respuesta"], True)

r2 = ag_vacio.preguntar("¿Cuánto me gasta cada mes?")
check("pide el extracto si faltan movimientos", "Necesito" in r2["respuesta"], True)

print("\n" + "=" * 62)
if fallos:
    print(f"FALLOS: {len(fallos)}")
    for f in fallos:
        print("  -", f)
    sys.exit(1)
print("TODOS LOS TESTS PASAN")
print("=" * 62)
