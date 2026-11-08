"""
Agente de Bedrock — capa de IA sobre el motor determinista.
=======================================================
Usa la API Converse de Amazon Bedrock con tool-use (function calling).

REGLA DE ARQUITECTURA (la mas importante del proyecto):
    El LLM NO hace aritmetica. Solo:
      1. entiende la pregunta en lenguaje natural,
      2. elige que herramienta del motor llamar,
      3. redacta la explicacion con los numeros que devuelve el motor.
    Todas las herramientas devuelven objetos JSON con numeros exactos y la
    explicacion de la regla aplicada.

Este modulo tiene un MODO MOCK que permite probarlo y hacer la demo sin
cuenta AWS (simula la seleccion de herramienta). El mock usa un enrutador
determinista por palabras clave, NO un LLM, y por tanto NO altera los
resultados numericos: sirve para validar la integracion y el contrato.

Referencia API: AWS Bedrock Converse API (toolConfig / toolUse / toolResult).
"""

from __future__ import annotations

import json
import re
import os
import sys
from dataclasses import asdict
from datetime import date
from decimal import Decimal
from typing import Any, Optional

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from engine.fiscal_andorra import (  # noqa: E402
    tramo_cass_para,
    cass_anual,
    irpf,
    igi,
    crossover_cass,
    punto_optimo_facturacion,
    simular_contratacion,
    comparar_escenarios,
    eur,
    Escenario,
)
from engine.tesoreria import (  # noqa: E402
    Movimiento,
    analizar_tesoreria,
    proyectar_caja,
    detectar_fugas,
    resumen_fugas,
    parse_extracto_csv,
)
from engine.cierre import (  # noqa: E402
    construir_consejos,
    cerrar_consejos,
    informe_cierre,
)

# --------------------------------------------------------------------------
# Constantes
# --------------------------------------------------------------------------

MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "amazon.nova-pro-v1:0")
KB_ID = os.environ.get("BEDROCK_KB_ID", "")      # opcional
# La region se lee de BEDROCK_REGION (la que inyecta Terraform: AWS_REGION
# es una clave RESERVADA en Lambda y AWS rechaza la Creacion si se declara
# en `environment`). Como respaldo, AWS_REGION / AWS_DEFAULT_REGION (lo que
# usan las CLI y los entornos locales).
#
# El default es us-east-1, NO eu-west-1: la cuenta del workshop tiene una
# policy "DenyAllOutsideAllowedRegions" que solo permite crear recursos en
# us-east-1, y Bedrock solo esta disponible en la region de la clave.
REGION = (
    os.environ.get("BEDROCK_REGION")
    or os.environ.get("AWS_REGION")
    or os.environ.get("AWS_DEFAULT_REGION")
    or "us-east-1"
)

SYSTEM_PROMPT = """Eres el analista financiero de MoraBanc para autonomos y pymes de Andorra.

REGLAS INVIOLABLES:
1. NUNCA calcules nada por tu cuenta. Todo numero que des debe venir de una
   herramienta del motor o del RESULTADO DEL MOTOR que te dan. Si no tienes
   el dato, pide el dato que falta.
2. Cuando des un numero, cita la regla que lo origina (CASS, IRPF, IGI,
   bonificacion art. 46, etc.). La regla va en el campo "regla".
3. Si la pregunta es sobre fiscalidad andorrana, usa la normativa vigente:
   - CASS: base 2.672,52 EUR (Decret 28/2026), 22% total, tramos 25/50/62,5/75/100/125/137,5%
   - IRPF: 10% nominal, minimo personal 24.000 EUR, bonificacion 50% tope 800 EUR
   - IGI: 4,5%
4. Responde en catalan o castellano segun el idioma de la pregunta.
5. Tono: claro, concreto, sin jerga. Como un asesor que explica, no como un
   formulario. Maximo 200 palabras salvo que pidan detalle.
6. NUNCA prometas resultados fiscales. Si el caso depende de factores que
   no tienes, dilo y pide el dato.

FORMATO DE RESPUESTA (Markdown):
- Empieza por la respuesta directa en una frase.
- Despues, los numeros en viñetas o una tabla corta.
- Al final, "Regla aplicada:" con la cita legal.
"""


def _jsonable(obj: Any) -> Any:
    """Convierte Decimals, Dates y dataclasses a algo JSON-serializable."""
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, date):
        return obj.isoformat()
    if hasattr(obj, "__dataclass_fields__"):
        return {k: _jsonable(v) for k, v in asdict(obj).items()}
    if isinstance(obj, dict):
        return {k: _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    return obj


def _eur(valor: Any, decimales: int = 2) -> str:
    """
    Formato europeo de euros: 34800.0 -> "34.800,00".

    En el pitch, "34800.00 €" se lee como un dato crudo de maquina; "34.800,00 €"
    se lee como una cuenta. Ademas el equipo habla catalan y castellano, donde
    el separador de millares es el punto.
    """
    try:
        v = float(valor)
    except (TypeError, ValueError):
        return str(valor)
    txt = f"{v:,.{decimales}f}"
    return txt.replace(",", " ").replace(".", ",").replace(" ", ".")


# ==========================================================================
# 1. Contexto de la empresa
# ==========================================================================

class ContextoEmpresa:
    """
    Estado de la empresa que se pasa al agente. En produccion vendria de
    DynamoDB / S3; en el hackathon, de la sesion del usuario.
    """

    def __init__(
        self,
        *,
        movimientos: Optional[list[Movimiento]] = None,
        saldo_actual: Decimal = Decimal("0"),
        renta_neta_anual: Optional[Decimal] = None,
        margen_bruto: Optional[Decimal] = None,
        actividad: str = "",
        fecha_consejo: Optional[date] = None,
        figura_fiscal: str = "",
        colchon_meses: Optional[Decimal] = None,
        gasto_fijo_mensual: Optional[Decimal] = None,
    ):
        self.movimientos = movimientos or []
        self.saldo_actual = Decimal(str(saldo_actual))
        self.renta_neta_anual = Decimal(str(renta_neta_anual)) if renta_neta_anual is not None else None
        self.margen_bruto = Decimal(str(margen_bruto)) if margen_bruto is not None else None
        self.actividad = actividad
        #: "persona_fisica" | "autonomo" | "sociedad". Lo sabe el banco:
        #: es su cliente, tiene su perfil fiscal. El agente no lo pregunta.
        self.figura_fiscal = figura_fiscal
        #: Colchon de caja en meses (lo calcula el motor de tesoreria).
        self.colchon_meses = Decimal(str(colchon_meses)) if colchon_meses is not None else None
        #: Gasto fijo mensual ya comprometido (alquiler, cuotas).
        self.gasto_fijo_mensual = Decimal(str(gasto_fijo_mensual)) if gasto_fijo_mensual is not None else None
        #: Fecha en la que el motor dio el consejo por ultima vez. Si es None,
        #: el cierre del bucle usa la fecha del primer movimiento.
        self.fecha_consejo = fecha_consejo

    @classmethod
    def desde_csv(cls, contenido_csv: str, **kwargs) -> "ContextoEmpresa":
        return cls(movimientos=parse_extracto_csv(contenido_csv), **kwargs)


# ==========================================================================
# 2. Herramientas (tools) — cada una llama al motor determinista
# ==========================================================================

def _tool_analizar_tesoreria(ctx: ContextoEmpresa, **_) -> dict:
    t = analizar_tesoreria(ctx.movimientos)
    return {
        "resultado": _jsonable(t),
        "regla": "Media aritmetica de ingresos y gastos sobre el periodo analizado, "
                 "normalizada a mensual.",
    }


def _tool_detectar_fugas(ctx: ContextoEmpresa, **_) -> dict:
    fugas = detectar_fugas(ctx.movimientos)
    r = resumen_fugas(fugas)
    return {
        "resultado": _jsonable(r),
        "regla": "Suscripciones: mismo concepto e importe con frecuencia mensual >= 0,8. "
                 "Duplicados: mismo importe y concepto en <= 5 dias. "
                 "Deriva: gasto de una categoria que crece > 15% en 3 meses.",
    }


def _tool_cerrar_ciclo(ctx: ContextoEmpresa, fecha_consejo: Optional[str] = None, **_) -> dict:
    """
    Cierra el bucle: comprueba los consejos dados contra los movimientos
    posteriores y dice cuanto se cumplio.

    Sin una fecha de consejo explicita, se usa la fecha del primer movimiento
    (el motor dio el consejo al ver el extracto). Si se pasa fecha_consejo
    (AAAA-MM-DD), esa es la fecha en que se dio el consejo y solo se evaluan
    los movimientos posteriores a ella.
    """
    if not ctx.movimientos:
        return {"resultado": {"error": "Sin movimientos"}, "regla": "n/a"}

    # Fecha del consejo: la explicita, o la del contexto, o el primer
    # movimiento del extracto.
    fecha = None
    if fecha_consejo:
        try:
            fecha = date.fromisoformat(str(fecha_consejo))
        except ValueError:
            fecha = None
    if fecha is None:
        fecha = ctx.fecha_consejo
    if fecha is None:
        fecha = min(m.fecha for m in ctx.movimientos)

    fugas = detectar_fugas(ctx.movimientos)
    consejos = construir_consejos(fugas, fecha=fecha)
    cierres = cerrar_consejos(consejos, ctx.movimientos)
    inf = informe_cierre(cierres)
    inf["fecha_consejo"] = fecha.isoformat()

    return {
        "resultado": _jsonable(inf),
        "regla": "El cierre compara los cargos posteriores a la fecha del consejo "
                 "con los que habia cuando se dio. Si el cargo desaparece, el "
                 "ahorro es el importe previsto; si sigue, no se aplico.",
    }


def _tool_proyectar_caja(ctx: ContextoEmpresa, meses: int = 12, **_) -> dict:
    if not ctx.movimientos:
        return {"resultado": {"error": "Sin movimientos"}, "regla": "n/a"}
    p = proyectar_caja(ctx.movimientos, saldo_inicial=ctx.saldo_actual, meses=int(meses))
    return {
        "resultado": _jsonable({
            "meses": p.meses,
            "mes_quiebre": p.mes_quiebre,
            "deuda_en_quiebre": p.deuda_maxima,
            "deuda_al_final": p.deuda_final,
            "ultimo_saldo_positivo": p.ultimo_saldo_positivo,
            "mes_ultimo_positivo": p.mes_ultimo_positivo,
            "resumen": p.resumen,
        }),
        "regla": "Proyeccion determinista mes a mes sobre el flujo medio real. "
                 "El quiebre se marca cuando el saldo pasa a negativo.",
    }


def _tool_tramo_cass(ctx: ContextoEmpresa, renta_neta: Optional[float] = None, **_) -> dict:
    r = Decimal(str(renta_neta)) if renta_neta is not None else ctx.renta_neta_anual
    if r is None:
        return {
            "resultado": {"error": "Falta la renta neta anual"},
            "regla": "n/a",
        }
    t = tramo_cass_para(r)
    return {
        "resultado": _jsonable({
            "tramo": t.nombre,
            "base_cotizacion": t.base,
            "cuota_mensual": t.cuota_mensual,
            "rama_general": t.rama_general,
            "rama_jubilacion": t.rama_jubilacion,
            "cuota_anual": cass_anual(t),
            "condicion": t.condicion,
        }),
        "regla": f"CASS {t.nombre}. Base global {eur(t.base)} EUR (Decret 28/2026), "
                 f"tipo total 22% (10% rama general + 12% jubilacion).",
    }


def _tool_irpf(ctx: ContextoEmpresa, base_general: Optional[float] = None, **_) -> dict:
    base = Decimal(str(base_general)) if base_general is not None else ctx.renta_neta_anual
    if base is None:
        return {"resultado": {"error": "Falta la base general"}, "regla": "n/a"}
    r = irpf(base_general=base)
    return {
        "resultado": _jsonable({
            "base_tributable": r.base_general,
            "cuota_10pct": r.cuota_general,
            "bonificacion_art46": r.bonificacion_actividades,
            "cuota_total": r.cuota_total,
            "tipo_efectivo": r.tipo_efectivo,
            "calculo": r.explicacion,
        }),
        "regla": "Llei 5/2014 de l'IRPF: art. 35 (minim personal 24.000 EUR), "
                 "art. 43 (tipus 10%), art. 46 (bonificacio 50% amb tope 800 EUR).",
    }


def _tool_igi(ctx: ContextoEmpresa, base_imponible: Optional[float] = None, **_) -> dict:
    base = Decimal(str(base_imponible)) if base_imponible is not None else ctx.renta_neta_anual
    if base is None:
        return {"resultado": {"error": "Falta la base imponible"}, "regla": "n/a"}
    g = igi(base)
    return {
        "resultado": _jsonable({
            "base": g.base_imponible,
            "tipo": g.tipo,
            "cuota": g.cuota,
            "calendario": g.calendario,
        }),
        "regla": "IGI 4,5% sobre el rendiment d'activitats economiques.",
    }


def _tool_resumen_carga_fiscal(ctx: ContextoEmpresa, renta_neta: Optional[float] = None, **_) -> dict:
    """Resumen de la carga fiscal anual: CASS + IRPF + el TOTAL.

    Existe porque el LLM no puede sumar: si le das la cuota anual de la
    CASS (7.055,40) y la del IRPF (300,00) y le preguntas "cuanto te
    queda", se inventa un total (3.955,40). El total lo calcula el motor.

    OJO: si no hay renta neta en el contexto, el motor NO puede calcular y
    esta herramienta devuelve un error, que el agente detecta y no inyecta.
    """
    r = Decimal(str(renta_neta)) if renta_neta is not None else ctx.renta_neta_anual
    if r is None:
        return {"resultado": {"error": "Falta la renta neta"}, "regla": "n/a"}

    t = tramo_cass_para(r)
    cuota_cass = cass_anual(t)
    i = irpf(base_general=r)
    cuota_irpf = i.cuota_total

    # El redondeo a 2 decimales lo hace el propio motor (Decimal.quantize),
    # no _r2 (que es privado del motor fiscal y no se importa aqui).
    total = (cuota_cass + cuota_irpf).quantize(Decimal("0.01"))
    return {
        "resultado": {
            "renta_neta_anual": eur(r),
            "cass_cuota_anual": eur(cuota_cass),
            "cass_cuota_mensual": eur(t.cuota_mensual),
            "cass_tramo": t.nombre,
            "irpf_cuota_anual": eur(cuota_irpf),
            "irpf_base_imponible": eur(i.base_general),
            "irpf_bonificacion_art_46": eur(i.bonificacion_actividades),
            "total_carga_fiscal_anual": eur(total),
            "neto_despues_de_impuestos": eur((r - total).quantize(Decimal("0.01"))),
        },
        "regla": (
            f"CASS {t.nombre} (Decret 28/2026, base {eur(t.base)}). "
            f"IRPF 10% con minimo personal 24.000 EUR y bonificacion art. 46 "
            f"del 50% con tope 800 EUR (Llei 5/2014)."
        ),
    }


def _tool_crossover(ctx: ContextoEmpresa, renta_neta: Optional[float] = None, **_) -> dict:
    r = Decimal(str(renta_neta)) if renta_neta is not None else ctx.renta_neta_anual
    if r is None:
        return {"resultado": {"error": "Falta la renta neta anual"}, "regla": "n/a"}
    c = crossover_cass(r)
    return {
        "resultado": _jsonable({
            "existe": c.existe,
            "tipo": c.tipo,
            "renta_punto": c.renta_punto,
            "delta_anual_cass": c.delta_anual,
            "detalle": c.detalle,
        }),
        "regla": "Salt de tramo CASS per renda neta (40.000 EUR -> 125%, "
                 "50.000 EUR -> 137,5%) i topament de la bonificacio IRPF art. 46 "
                 "en 40.000 EUR de base.",
    }


def _tool_simular_contratacion(
    ctx: ContextoEmpresa,
    coste_mensual_empleado: Optional[float] = None,
    margen_bruto: Optional[float] = None,
    **_,
) -> dict:
    if ctx.renta_neta_anual is None:
        return {"resultado": {"error": "Falta la renta neta actual"}, "regla": "n/a"}
    coste = Decimal(str(coste_mensual_empleado)) if coste_mensual_empleado is not None else Decimal("0")
    margen = Decimal(str(margen_bruto)) if margen_bruto is not None else (ctx.margen_bruto or Decimal("0.70"))
    sim = simular_contratacion(
        renta_neta_actual=ctx.renta_neta_anual,
        margen_bruto=margen,
        coste_nuevo_empleado_mensual=coste,
    )
    return {
        "resultado": _jsonable(sim),
        "regla": "El coste del empleat es despesa deduible: no cambia la renda neta, "
                 "asi que la CASS i l'IRPF se mantienen. Lo que cambia es la caja: "
                 "hay que facturar el coste con margen e IGI incluidos.",
    }


#: Los objetivo de compra y como se detectan en la pregunta.
#: El orden importa: "local comercial" es "vivienda", no "comercio".
_OBJETIVOS_COMPRA: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("vivienda", ("casa", "piso", "vivienda", "local", "apartamento", "adosado",
                  "un piso", "un local", "immobilier", "house", "home", "flat",
                  "appartement", "maison", "casa")),
    ("maquinaria", ("maquinaria", "maquina", "equipo", "herramienta", "utillaje",
                    "vehicle de reparto", "furgoneta", "camion", "camión",
                    "maquinaria", "machine", "equipment")),
    ("coche", ("coche", "carro", "vehiculo", "vehículo", "automovil", "automóvil",
               "4x4", "car", "voiture", "auto", "macchina")),
    ("contratar", ("contratar", "empleado", "empleada", "persona", "personal",
                   "ayudante", "trabajador")),
    ("ampliar", ("ampliar", "ampliacion", "ampliación", "nueva sede", "otra sede",
                 "sucursal", "expand")),
    ("invertir", ("invertir", "inversion", "inversión", "bolsa", "cripto",
                  "fondo", "invert")),
)


def _detectar_decision_compra(p: str) -> tuple[str, Optional[float]]:
    """
    De una pregunta en español, (a) que decision se esta tomando y
    (b) por cuanto dinero.

    "Quiero comprar un coche de 30.000 euros" -> ("coche", 30000.0)
    "Me quiero comprar una casa" -> ("vivienda", None)

    El importe se busca con las dos convenciones: 30.000 (europeo) y
    30,000 (anglosajon). Los millares se distinguen por el numero de
    decimales: "30.000" son treinta mil, "30,000" tambien (en una
    cuenta bancaria el separador de millares va antes).
    """
    objetivo = ""
    for nombre, claves in _OBJETIVOS_COMPRA:
        if any(k in p for k in claves):
            objetivo = nombre
            break

    # El importe: el numero mas grande de la frase, que es el de la
    # compra (los porcentajes y los plazos son mas pequenos).
    import re as _re2
    candidatos = []
    for m in _re2.finditer(r"([0-9][0-9.]*(?:,[0-9]{3})*(?:\.[0-9]+)?)", p):
        bruto = m.group(1)
        try:
            if "," in bruto and "." in bruto:
                # Formato europeo: 1.234.567,89 -> el punto es millar
                valor = float(bruto.replace(".", "").replace(",", "."))
            elif "," in bruto:
                partes = bruto.split(",")
                if len(partes[-1]) == 3 and len(partes[0]) <= 3:
                    # 30,000 -> treinta mil (separador de millares)
                    valor = float(bruto.replace(",", ""))
                else:
                    valor = float(bruto.replace(",", "."))
            elif "." in bruto:
                partes = bruto.split(".")
                # "30.000" son treinta mil (punto de millares, formato
                # europeo); "30.5" son treinta coma cinco. La regla: si
                # lo que va detras del separador tiene 3 digitos y lo de
                # antes es un numero de 1 a 3 cifras, el separador es de
                # millares. Si lo de antes tiene mas de 3 cifras
                # ("300.000"), es millares seguro.
                if len(partes[-1]) == 3 and (len(partes[0]) <= 3 or len(partes) > 2):
                    valor = float(bruto.replace(".", ""))
                else:
                    valor = float(bruto)
            else:
                valor = float(bruto)
        except (ValueError, TypeError):
            continue
        if valor >= 100:
            candidatos.append(valor)

    importe = max(candidatos) if candidatos else None
    return objetivo, importe


def _tool_evaluar_compra(
    ctx: ContextoEmpresa,
    objetivo: Optional[str] = None,
    importe: Optional[float] = None,
    meses_prestamo: Optional[int] = None,
    **_,
) -> dict:
    """
    "¿Puedo comprar esto?"

    Es la pregunta de un asesor de verdad: no "¿cuanto ganas?", sino
    "¿puedo permitirme este coche / esta casa / esta maquinaria?".
    El motor responde con el limite, el margen que queda y los avisos
    (efecto fiscal, colchon de caja, compromiso mensual).
    """
    from engine.perfil_cliente import (
        ProfileCliente,
        ProductoContratado,
        evaluar_compra as _evaluar,
        evaluar_contratacion as _evaluar_contratacion,
    )

    perfil = ProfileCliente(
        figura_fiscal=ctx.figura_fiscal or ("autonomo" if ctx.actividad else "persona_fisica"),
        actividad=ctx.actividad,
        renta_neta_anual=ctx.renta_neta_anual,
        margen_bruto=ctx.margen_bruto,
        saldo_actual=ctx.saldo_actual or Decimal("0"),
        colchon_meses=ctx.colchon_meses,
        gasto_fijo_mensual=ctx.gasto_fijo_mensual or Decimal("0"),
        objetivo=objetivo or "",
    )

    obj = (objetivo or "").strip().lower()
    kwargs = {}
    if meses_prestamo:
        kwargs["meses_prestamo"] = int(meses_prestamo)
    if importe is not None:
        kwargs["importe"] = Decimal(str(importe))

    if obj in ("contratar", "empleado", "personal"):
        # El objetivo de contratar necesita el bruto, que es un dato
        # NUEVO (no lo tiene el banco: es la decision que se esta
        # tomando).
        #
        # El usuario dice el bruto MENSUAL ("2.400 brutos al mes"), que
        # es como se habla. La herramienta necesita el ANUAL.
        bruto_mensual = kwargs.pop("importe", None)
        if bruto_mensual is None:
            return {
                "resultado": {
                    "error": "Falta el bruto del contrato",
                    "pregunta_necesaria": "¿De que bruto mensual es el contrato?",
                },
                "regla": "Para calcular el coste real de un contrato hay que "
                         "saber el bruto: las contribuciones sociales van "
                         "encima (21 %).",
            }
        # El usuario dice el bruto MENSUAL ("2.400 brutos al mes"), que
        # es como se habla. Si ha dicho "al año", el numero ya es anual.
        texto = kwargs.pop("texto", "") or ""
        if re.search(r"(bruto|coste|sueldo)[^.]{0,20}(anual|al a[nñ]o)", texto):
            bruto_anual = Decimal(str(bruto_mensual))
        else:
            bruto_anual = Decimal(str(bruto_mensual)) * Decimal(12)
        res = _evaluar_contratacion(perfil, bruto_anual=bruto_anual, **kwargs)
    else:
        res = _evaluar(perfil, objetivo=obj or "coche", **kwargs)

    return {
        "resultado": _jsonable({
            "cabe": res.cabe,
            "veredicto": res.veredicto(),
            "importe_maximo_eur": res.importe_maximo,
            "importe_pedido_eur": res.importe_pedido,
            "margen_mensual_tras_pago_eur": res.margen_mensual_tras_pago,
            "meses_colchon_tras_pago": res.meses_colchon_tras_pago,
            "avisos": res.avisos,
        }),
        "regla": res.regla,
    }


def _tool_punto_optimo(ctx: ContextoEmpresa, margen_bruto: Optional[float] = None, **_) -> dict:
    if ctx.renta_neta_anual is None:
        return {"resultado": {"error": "Falta la renta neta anual"}, "regla": "n/a"}
    margen = Decimal(str(margen_bruto)) if margen_bruto is not None else (ctx.margen_bruto or Decimal("0.70"))
    po = punto_optimo_facturacion(ctx.renta_neta_anual, margen)
    return {
        "resultado": _jsonable(po),
        "regla": "Minimiza el coste fiscal total (CASS + IRPF) sobre la facturacion, "
                 "teniendo en cuenta que la CASS es un coste fijo por tramo que salta.",
    }


def _tool_comparar_escenarios(
    ctx: ContextoEmpresa,
    renta_a: Optional[float] = None,
    renta_b: Optional[float] = None,
    **_,
) -> dict:
    if renta_a is None or renta_b is None:
        return {"resultado": {"error": "Faltan las dos rentas a comparar"}, "regla": "n/a"}
    comp = comparar_escenarios(
        Escenario("Escenario A", Decimal(str(renta_a))),
        Escenario("Escenario B", Decimal(str(renta_b))),
    )
    return {
        "resultado": _jsonable({
            "delta_neto_anual": comp.delta_neto_anual,
            "delta_cass_anual": comp.delta_cass_anual,
            "delta_irpf_anual": comp.delta_irpf_anual,
            "detalle": comp.detalle,
        }),
        "regla": "Diferencia neta entre escenarios = delta de renda - delta de CASS "
                 "- delta de IRPF.",
    }


# --------------------------------------------------------------------------
# Esquemas de las herramientas para el API de Bedrock (toolConfig)
# --------------------------------------------------------------------------

TOOL_SCHEMAS: list[dict] = [
    {
        "toolSpec": {
            "name": "resumen_carga_fiscal",
            "description": (
                "Resumen de la carga fiscal anual de la empresa: cuota anual de "
                "CASS, cuota anual de IRPF y el TOTAL de las dos, con la regla "
                "aplicada. Usala cuando la pregunta pida el total, 'cuanto me "
                "queda' o 'cuanto pago en impuestos'. El total lo calcula el "
                "motor: no lo calcules tu."
            ),
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "renta_neta": {"type": "number", "description": "Renta neta anual en euros"}
                    },
                    "required": [],
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "evaluar_compra",
            "description": (
                "Responde a la pregunta de un asesor: '¿puedo permitirme esta "
                "compra?'. Devuelve el limite (cuanto puede gastar), el margen "
                "mensual que le queda, los meses de colchon de caja que le "
                "quedan y los avisos (efecto fiscal, compromiso mensual, "
                "colchon). Usala para decisiones de compra: un coche, una "
                "vivienda, maquinaria, un local, o contratar a alguien. Los "
                "datos del cliente (renta neta, saldo, margen, gasto fijo) ya "
                "estan en el contexto: NO los pidas."
            ),
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "objetivo": {
                            "type": "string",
                            "description": (
                                "La decision: 'coche', 'vivienda', 'maquinaria', "
                                "'contratar', 'ampliar' o 'invertir'"
                            ),
                        },
                        "importe": {
                            "type": "number",
                            "description": (
                                "El importe en euros. Para 'contratar', el bruto "
                                "MENSUAL (la herramienta lo pasa a anual)"
                            ),
                        },
                        "meses_prestamo": {
                            "type": "integer",
                            "description": "El plazo del prestamo en meses (por defecto 60)",
                        },
                    },
                    "required": [],
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "analizar_tesoreria",
            "description": "Resume ingresos, gastos, flujo neto y desglose por categoria del extracto. "
                           "Usar para entender de donde viene y adonde va el dinero.",
            "inputSchema": {"json": {"type": "object", "properties": {}}},
        }
    },
    {
        "toolSpec": {
            "name": "detectar_fugas",
            "description": "Detecta fugas de caja: suscripciones que no se usan, cobros duplicados "
                           "y gastos que crecen mes a mes. Devuelve el importe recuperable.",
            "inputSchema": {"json": {"type": "object", "properties": {}}},
        }
    },
    {
        "toolSpec": {
            "name": "proyectar_caja",
            "description": "Proyecta la tesoreria mes a mes y dice en que mes la caja se queda sin dinero.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "meses": {"type": "integer", "description": "Horizonte en meses (por defecto 12)"}
                    },
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "tramo_cass",
            "description": "Calcula el tramo de cotizacion CASS y la cuota mensual de un autonomo "
                           "a partir de su renta neta anual.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "renta_neta": {"type": "number", "description": "Renta neta anual en euros"}
                    },
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "calcular_irpf",
            "description": "Calcula el IRPF andorrano (cuota total, bonificacion y tipo efectivo) "
                           "sobre una base general.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "base_general": {"type": "number", "description": "Base general en euros"}
                    },
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "calcular_igi",
            "description": "Calcula el IGI (4,5%) y su calendario de pago.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "base_imponible": {"type": "number", "description": "Base imponible en euros"}
                    },
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "detectar_crossover_fiscal",
            "description": "Detecta el punto exacto en el que aumentar la renta deja de compensar "
                           "por un salto de tramo CASS o por el tope de la bonificacion del IRPF.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "renta_neta": {"type": "number", "description": "Renta neta anual en euros"}
                    },
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "simular_contratacion",
            "description": "Simula contratar a un empleado: cuanto cuesta al ano y cuanta facturacion "
                           "adicional hace falta para cubrirlo con margen e IGI.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "coste_mensual_empleado": {"type": "number", "description": "Coste mensual bruto"},
                        "margen_bruto": {"type": "number", "description": "Margen bruto en tanto por uno (0.70 = 70%)"},
                    },
                    "required": ["coste_mensual_empleado"],
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "punto_optimo_facturacion",
            "description": "Calcula la facturacion que minimiza la carga fiscal total, "
                           "por el efecto de los saltos de tramo CASS.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "margen_bruto": {"type": "number", "description": "Margen bruto en tanto por uno"}
                    },
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "cerrar_ciclo",
            "description": "Cierra el bucle de vuelta: comprueba los recomendaciones dadas "
                           "contra los movimientos posteriores y dice cuanto se cumplio. "
                           "Devuelve veredicto (cumplido / parcial / incumplido / sin_datos), "
                           "el ahorro real en euros por mes y el esperado.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "fecha_consejo": {
                            "type": "string",
                            "description": "Fecha (AAAA-MM-DD) en la que se dio el consejo. "
                                           "Si se omite, se usa la del primer movimiento.",
                        }
                    },
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "comparar_escenarios",
            "description": "Compara dos escenarios de renta neta y devuelve el delta neto, "
                           "el delta de CASS y el delta de IRPF.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "renta_a": {"type": "number"},
                        "renta_b": {"type": "number"},
                    },
                    "required": ["renta_a", "renta_b"],
                }
            },
        }
    },
]

# Registro de herramientas -> implementacion
TOOL_IMPLS = {
    "analizar_tesoreria": _tool_analizar_tesoreria,
    "detectar_fugas": _tool_detectar_fugas,
    "proyectar_caja": _tool_proyectar_caja,
    "tramo_cass": _tool_tramo_cass,
    "calcular_irpf": _tool_irpf,
    "calcular_igi": _tool_igi,
    "detectar_crossover_fiscal": _tool_crossover,
    "simular_contratacion": _tool_simular_contratacion,
    "evaluar_compra": _tool_evaluar_compra,
    "punto_optimo_facturacion": _tool_punto_optimo,
    "comparar_escenarios": _tool_comparar_escenarios,
    "cerrar_ciclo": _tool_cerrar_ciclo,
    "resumen_carga_fiscal": _tool_resumen_carga_fiscal,
}


def ejecutar_tool(nombre: str, ctx: ContextoEmpresa, argumentos: Optional[dict] = None) -> dict:
    """Ejecuta una herramienta del motor y devuelve el resultado serializable."""
    if nombre not in TOOL_IMPLS:
        return {"resultado": {"error": f"Herramienta desconocida: {nombre}"}, "regla": "n/a"}
    try:
        args = dict(argumentos or {})
        if nombre == "evaluar_compra":
            # La herramienta necesita el texto original para saber si
            # el bruto que ha dicho el usuario es mensual o anual.
            args.setdefault("texto", "")
        out = TOOL_IMPLS[nombre](ctx, **args)
    except Exception as e:  # noqa: BLE001
        return {"resultado": {"error": f"{type(e).__name__}: {e}"}, "regla": "n/a"}
    return {
        "resultado": out["resultado"],
        "regla": out["regla"],
    }


# ==========================================================================
# 3. Agente de Bedrock (Converse API con tool-use)
# ==========================================================================

RE_THINKING = re.compile(r"<thinking>.*?</thinking>", re.S | re.I)


def _resultado_legible(out: dict) -> str:
    """Formatea el resultado del motor para que el LLM lo cite bien.

    El motor devuelve floats crudos (7055.4). Si se pasan tal cual, el
    LLM los redondea como quiere (7055, 7.055) o los confunde con la
    cifra que el usuario ha dicho. Se formatean en euros con el formato
    europeo (7.055,40 EUR) y se rotulan, para que la respuesta cite
    exactamente los numeros del motor.
    """
    import json as _json

    res = out.get("resultado") or {}
    regla = out.get("regla") or ""

    def fmt(v):
        if isinstance(v, bool) or v is None:
            return v
        if isinstance(v, (int, float)):
            return f"{eur(v)} EUR"
        if isinstance(v, Decimal):
            return f"{eur(v)} EUR"
        return v

    legible = {k: fmt(v) for k, v in res.items()} if isinstance(res, dict) else res

    partes = [_json.dumps(legible, ensure_ascii=False, default=str)]
    if regla:
        partes.append(f"Regla aplicada: {regla}")
    return "\n".join(partes)


def _sin_thinking(texto: str) -> str:
    """Quita el bloque de razonamiento que Nova Pro antepone.

    Nova devuelve "<thinking>...</thinking>\n\nRespuesta final". El
    razonamiento no es la respuesta: si se muestra, el usuario ve al LLM
    pensandose a si mismo ("necesito la renta neta... no puedo calcular").
    """
    if not texto:
        return texto
    limpio = RE_THINKING.sub("", texto)
    # A veces el bloque va sin cerrar (lo corta el limite de tokens).
    if "<thinking>" in limpio.lower():
        limpio = re.sub(r"<thinking>.*", "", limpio, flags=re.S | re.I)
    return limpio.strip()


class AgenteFinanciero:
    """
    Agente que usa Amazon Bedrock (Converse API) con tool-use.

    Uso:
        agente = AgenteFinanciero(contexto)
        respuesta = agente.preguntar("¿Puedo contratar a alguien a 2.400 brutos?")

    En modo mock (sin credenciales AWS) enruta las preguntas con reglas
    deterministas para poder validar el flujo sin cuenta.
    """

    MAX_ITERACIONES = 6

    def __init__(
        self,
        contexto: ContextoEmpresa,
        *,
        model_id: str = MODEL_ID,
        region: str = REGION,
        kb_id: str = KB_ID,
        mock: Optional[bool] = None,
    ):
        self.ctx = contexto
        self.model_id = model_id
        self.region = region
        self.kb_id = kb_id
        self._client = None
        self.trace: list[dict] = []      # registro de llamadas a herramientas

        # El id del Bedrock Guardrail. El guardrail se crea en el
        # terraform (enable_guardrails) pero, si no se pasa en la llamada
        # a converse, NO hace NADA: el filtro de prompt injection y de
        # PII se queda sin conectar. Por eso se lee del entorno y se
        # anade a la peticion.
        self.guardrail_id = os.environ.get("BEDROCK_GUARDRAIL_ID", "").strip()
        # OJO: Bedrock EXIGE que el identifier y la version vayan JUNTOS
        # ("guardrailIdentifier and guardrailVersion must be provided
        # together"). Si se manda solo el identifier, la llamada falla con
        # ValidationException y el chat entero se cae. Por eso la version
        # tiene un valor por defecto: "DRAFT" es la version que crea el
        # terraform (el guardrail se crea y se usa en DRAFT; las
        # desplegadas son para produccion estricta).
        self.guardrail_version = (
            os.environ.get("BEDROCK_GUARDRAIL_VERSION", "").strip() or "DRAFT"
        )

        if mock is None:
            # Modo mock si:
            #   - BEDROCK_MOCK esta a "1"/"true", o
            #   - no hay credenciales de AWS configuradas.
            flag = os.environ.get("BEDROCK_MOCK", "").strip().lower()
            if flag in ("1", "true", "yes", "on"):
                mock = True
            elif flag in ("0", "false", "no", "off"):
                mock = False
            else:
                mock = not os.environ.get("AWS_ACCESS_KEY_ID")
        self.mock = mock

    # -- cliente Bedrock (lazy) ------------------------------------------
    def _bedrock(self):
        if self._client is None:
            import boto3
            self._client = boto3.client("bedrock-runtime", region_name=self.region)
        return self._client

    # -- RAG opcional ----------------------------------------------------
    def _recuperar_contexto(self, pregunta: str) -> str:
        """Busca en la Knowledge Base de Bedrock (normativa andorrana, productos)."""
        if not self.kb_id:
            return ""
        try:
            import boto3
            kb = boto3.client("bedrock-agent-runtime", region_name=self.region)
            resp = kb.retrieve(
                knowledgeBaseId=self.kb_id,
                retrievalQuery={"text": pregunta},
                retrievalConfiguration={
                    "vectorSearchConfiguration": {"numberOfResults": 4}
                },
            )
            partes = []
            for r in resp.get("retrievalResults", []):
                contenido = r.get("content", {}).get("text", "")
                fuente = r.get("content", {}).get("metadata", {}).get("x-amz-bedrock-kb-source-uri", "")
                if contenido:
                    partes.append(f"[{fuente}]\n{contenido}")
            return "\n\n".join(partes)
        except Exception:
            return ""

    # -- API principal ---------------------------------------------------
    def preguntar(self, pregunta: str, *, historial: Optional[list[dict]] = None) -> dict:
        """
        Hace una pregunta al agente.

        Devuelve:
          {"respuesta": str, "herramientas": [...], "mock": bool}
        """
        if self.mock:
            return self._preguntar_mock(pregunta)
        return self._preguntar_bedrock(pregunta, historial or [])

    # -- Implementacion real (Bedrock) ------------------------------------
    def _herramienta_determinista(self, pregunta: str):
        """Decide la herramienta y calcula con el MOTOR, sin LLM.

        Devuelve (nombre_herramienta, resultado) o (None, None) si la
        pregunta no es de calculo (y entonces deja que el LLM elija).

        El motor ya sabe ejecutar cada herramienta con el contexto de la
        empresa (ejecutar_tool). Aqui solo se decide CUAL, con las mismas
        reglas que usa el router del mock, y se ejecuta.
        """
        p = pregunta.lower()

        # "renta" sola cae en el resumen de la regla del mock; pero si la
        # pregunta es sobre IRPF/CASS, la herramienta fiscal manda.
        # Todas las herramientas que apliquen, no solo la primera.
        #
        # OJO: si la pregunta es "Cuanto me queda de IRPF y CASS?" y solo se
        # calcula el tramo de CASS, el LLM se inventa el IRPF (calculando
        # 30.000 x 10% a mano). Eso es justo lo que el proyecto promete que
        # no pasa: "la IA es el interfaz, la norma es el producto".
        #
        # Con varias herramientas, se calculan TODAS y se le pasan al LLM.
        herramientas = []
        for claves, nombre, _params in self._REGLAS_ROUTER:
            if any(k in p for k in claves):
                if nombre not in herramientas:
                    herramientas.append(nombre)

        # "IRPF y CASS" es la combinacion clasica: si el router solo ha
        # cogido una de las dos, se anade la otra (si la menciona la
        # pregunta).
        if len(herramientas) == 1:
            if herramientas[0] == "tramo_cass" and ("irpf" in p or "impuesto" in p):
                herramientas.append("calcular_irpf")
            elif herramientas[0] == "calcular_irpf" and ("cass" in p or "cotizacion" in p):
                herramientas.append("tramo_cass")

        # El resumen de carga fiscal ya trae CASS + IRPF + total: si esta
        # en la lista, las cuotas sueltas sobran (y hacen que el LLM los
        # mezcle).
        if "resumen_carga_fiscal" in herramientas:
            herramientas = ["resumen_carga_fiscal"]

        if not herramientas:
            return None, None

        # Se calculan TODAS las herramientas que apliquen: si la pregunta
        # es "Cuanto me queda de IRPF y CASS?" y solo se calcula el tramo de
        # CASS, el LLM se inventa el IRPF (30.000 x 10% a mano). Eso es
        # justo lo que el proyecto promete que no pasa.
        resultados = []
        for nombre in herramientas:
            try:
                out = ejecutar_tool(nombre, self.ctx, self._params_para(nombre, p))
            except Exception:  # noqa: BLE001
                # Si el motor falla con una, mejor que lo intente el LLM
                # que devolver un 500.
                continue

            if not isinstance(out, dict) or "resultado" not in out:
                continue

            # Si el motor no pudo calcular (le faltaba un dato), NO se
            # inyecta un {"error": ...} como si fuera un resultado.
            res = out.get("resultado")
            if isinstance(res, dict) and "error" in res:
                continue

            resultados.append((nombre, out))

        if not resultados:
            return None, None

        return [n for n, _ in resultados], resultados

    def _params_para(self, herramienta: str, p: str) -> dict:
        """Parametros de la herramienta: del CONTEXTO primero, de la pregunta si hace falta.

        Regla: si la empresa ya tiene el dato en el contexto, ese vale. Solo
        se lee de la pregunta lo que NO esta en el contexto.

        Esto importa: el usuario puede decir "voy a facturar 60000" (ingreso
        bruto) mientras que la empresa tiene su renta neta real en el
        contexto. Si la pregunta gana, el motor calcula sobre 60000 cuando
        la cifra correcta es otra: el numero sale bien formado pero
        WRONG, y eso es peor que un error.
        """
        import re as _re

        params: dict = {}
        ctx = self.ctx

        # --- renta neta / base general ---
        # 1) la del contexto (fuente de verdad)
        # 2) la que el usuario diga EXPLICITAMENTE que es renta neta
        if ctx.renta_neta_anual is not None:
            params["renta_neta"] = float(ctx.renta_neta_anual)
            params["base_general"] = float(ctx.renta_neta_anual)
        else:
            m = _re.search(r"renta neta[^0-9]{0,25}([0-9][0-9.]*)", p)
            if m:
                v = m.group(1)
                n = float(v.replace(".", "").replace(",", ".")) if "," in v else float(v)
                params["renta_neta"] = n
                params["base_general"] = n

        # --- coste del empleado (simulacion de contratacion) ---
        # Este SI sale de la pregunta: es lo que se esta simulando.
        m = _re.search(r"(?:sueldo|coste|coste_mensual_empleado)[^0-9]{0,25}([0-9][0-9.]*)", p)
        if m:
            v = m.group(1)
            params["coste_mensual_empleado"] = float(v.replace(".", "").replace(",", ".")) \
                if "," in v else float(v)

        # --- horizonte de proyeccion ---
        m = _re.search(r"([0-9]{1,2})\s*meses", p)
        if m:
            params["meses"] = int(m.group(1))

        # --- la decision de compra: que quiere y por cuanto ---
        #
        # "Quiero comprar un coche de 30.000 euros" -> objetivo=coche,
        # importe=30000. Sin esto, el motor no sabe que decision se
        # esta evaluando y devuelve el importe por defecto.
        if herramienta == "evaluar_compra":
            objetivo, importe = _detectar_decision_compra(p)
            if objetivo:
                params["objetivo"] = objetivo
            if importe is not None:
                params["importe"] = float(importe)
            params["texto"] = p

        return params

    def _preguntar_bedrock(self, pregunta: str, historial: list[dict]) -> dict:
        brt = self._bedrock()
        mensajes: list[dict] = list(historial)
        contexto_normativa = self._recuperar_contexto(pregunta)

        system = SYSTEM_PROMPT

        # ── El idioma del cliente ──
        #
        # El cliente puede hablar cualquier idioma (Andorra es
        # trilingue y hay clientes de fuera). El motor y las cifras van
        # siempre en espanol (es el idioma de la normativa del banco),
        # pero la respuesta va en el idioma del cliente.
        from engine.idiomas import (
            detectar_en_conversacion,
            detectar_idioma,
            instruction_de_idioma,
        )

        codigo_idioma, confianza = detectar_idioma(pregunta)
        if historial:
            codigo_idioma = detectar_en_conversacion(
                [{"source": "user", "message": h.get("content", "")} for h in historial]
            )
        system += "\n\n" + instruction_de_idioma(codigo_idioma, confianza)

        # ------------------------------------------------------------------
        # HERRAMIENTA DETERMINISTA: el motor calcula, el LLM redacta.
        # ------------------------------------------------------------------
        # Confiar en que el LLM elija la herramienta es frágil: con
        # toolChoice=auto, Nova a veces decide que no necesita el motor y
        # responde "dame la renta neta" aunque la empresa ya la tiene en el
        # contexto. En un pitch, eso es un 500.
        #
        # Aqui el motor decide SIEMPRE que herramienta corresponde (es
        # codigo, no una prediccion) y su resultado se le pasa al LLM como
        # contexto. El LLM solo redacta y explica la regla. Los numeros
        # NUNCA salen del LLM.
        herramientas_fijas, resultados_motor = self._herramienta_determinista(pregunta)
        # Compatibilidad: el resto del codigo usa estos dos nombres.
        herramienta_fija = herramientas_fijas[0] if herramientas_fijas else None
        resultado_motor = resultados_motor[0][1] if resultados_motor else None
        # Todos los resultados del motor, para inyectarlos en el prompt.
        todos_los_resultados = {n: o for n, o in (resultados_motor or [])}


        # El modelo tiene que saber QUE DATOS hay disponibles. Sin esto, si
        # la empresa ya tiene la renta neta cargada, el LLM pregunta por los
        # gastos ("necesito informacion sobre sus gastos deducibles") en
        # vez de llamar a la herramienta. Es un fallo grave: el motor sabe
        # calcularlo, pero el chat se hace el tonto.
        datos = []
        if self.ctx.renta_neta_anual is not None:
            datos.append(f"- renta neta anual: {eur(self.ctx.renta_neta_anual)}")
        if self.ctx.actividad:
            datos.append(f"- actividad: {self.ctx.actividad}")
        if self.ctx.margen_bruto is not None:
            datos.append(f"- margen bruto: {eur(self.ctx.margen_bruto)}")
        if self.ctx.saldo_actual is not None:
            datos.append(f"- saldo actual en cuenta: {eur(self.ctx.saldo_actual)}")
        if datos:
            # OJO: esta instruccion cambia segun el caso. Si el motor ya
            # ha calculado, decir "llama a la herramienta" METE CONTRADICCION
            # con el prompt base y Nova pide los datos que ya tiene.
            if resultado_motor is not None:
                instruccion = (
                    "\n\nREGLAS:"
                    "\n- El calculo YA ESTA HECHO (ver RESULTADO DEL MOTOR). "
                    "Redacta con esos numeros."
                    "\n- NO pidas datos que ya estan aqui."
                    "\n- NO tienes herramientas disponibles: el calculo ya "
                    "esta hecho, no busques ninguna."
                    "\n- Si el usuario menciona una cifra que NO es la renta "
                    "neta (por ejemplo 'facturo 60000'), esa cifra es INGRESO "
                    "BRUTO. El motor ha calculado sobre la RENTA NETA del "
                    "contexto. Si la cifra que da el usuario es la que "
                    "pregunta, explica la diferencia en una linea: 'sobre una "
                    "renta neta de X, que es lo que el motor ha usado'."
                    "\n- No calcules nada tu mismo."
                )
            else:
                instruccion = (
                    "\n\nREGLAS:"
                    "\n- Si la pregunta se puede responder con estos datos, "
                    "LLAMA A LA HERRAMIENTA que corresponda. No respondas de "
                    "memoria."
                    "\n- NO pidas datos que ya estan aqui (gastos, renta neta, "
                    "actividad). Si faltan, dimelo, pero despues de haber "
                    "usado lo que tienes."
                    "\n- Si el usuario menciona una cifra que NO es la renta "
                    "neta (por ejemplo 'facturo 60000'), esa cifra es INGRESO "
                    "BRUTO: pasa a la herramienta como parametro solo si la "
                    "herramienta lo pide, y usa el contexto (renta neta) para "
                    "lo demas."
                    "\n- No calcules nada tu mismo: los numeros salen de las "
                    "herramientas."
                )
            system += (
                "\n\nDATOS YA DISPONIBLES DE LA EMPRESA (usalos, NO los pidas):\n"
                + "\n".join(datos)
                + instruccion
            )

        if contexto_normativa:
            system += (
                "\n\nNORMATIVA Y PRODUCTOS RELEVANTES (recuperados de la base de "
                "conocimiento, cita la fuente):\n" + contexto_normativa
            )

        params_deterministas = self._params_para("", pregunta.lower())
        if resultado_motor is not None:
            _bloques = []
            for _n, _o in (resultados_motor or []):
                _bloques.append(_resultado_legible(_o))
            # OJO: el LLM no puede hacer aritmetica con los numeros. Si el
            # motor da la cuota ANUAL y la MENSUAL de la CASS, el modelo se
            # liaba y se inventa un descuento ("7.055,40 - 587,95 - 587,95
            # - 587,95 - 587,95 = 4.603,60"): un total que NO sale del
            # motor y que el jurado puede sumar en dos segundos.
            #
            # Se le pasan solo las cifras del motor y se le prohibe
            # sumar o restar: si hace falta un total, que lo pida al motor.
            system += (
                "\n\nRESULTADO DEL MOTOR (ya calculado, no lo recalcules):\n"
                + "\n".join(_bloques)[:6000]
                + "\n\nRedacta la respuesta usando EXACTAMENTE estos numeros y la "
                "regla aplicada."
                "\n- NO hagas aritmetica: no sumes, no restes, no multiplyes "
                "ni calcules totales que no esten en el resultado. Si te "
                "piden un total y no lo tienes, di el importe que te han "
                "dado y el periodo."
                "\n- Cita las cifras tal cual te las han dado, con su "
                "etiqueta (anual, mensual, base...)."
                "\n- Si la pregunta es sobre IRPF, CASS, impuestos o "
                "'cuanto me queda', la respuesta DEBE incluir las tres "
                "cifras del motor: total_carga_fiscal_anual (el total), "
                "neto_despues_de_impuestos (lo que queda) y las cuotas "
                "anuales. Son las cifras que te ha dado el motor: no las "
                "calcules tu."
                "\n- No inventes cifras. No llames a ninguna herramienta: el "
                "calculo ya esta hecho."
                "\n- Los importes van en FORMATO EUROPEO: 7.055,40 EUR "
                "(punto de millares, coma decimal). Si el resultado del "
                "motor te da un numero en otro formato, reescribelo con "
                "punto de millares y coma decimal antes de decirlo. Nunca "
                "digas 7055.4 ni 108000.0."
                "\n- Las cifras van con su etiqueta (anual, mensual, base, "
                "tramo...) y con su unidad en EUR."
            )
            # El motor ya ha calculado: el LLM solo redacta. Forzar la
            # herramienta hacia que el modelo la llamara con parametros
            # inventados en iteraciones siguientes, asi que se desactiva.
            tool_choice = {"none": {}}
        else:
            tool_choice = {"auto": {}}

        mensajes.append({"role": "user", "content": [{"text": pregunta}]})

        llamadas: list[dict] = []

        for iteracion in range(self.MAX_ITERACIONES):
            # La herramienta forzada solo en la PRIMERA iteracion. Si se
            # forzara siempre, el modelo la llamaria en bucle (cada
            # respuesta vuelve a pedirla) y se agotarian las iteraciones
            # con un "se ha alcanzado el limite de iteraciones".
            # Despues, el LLM redacta con el resultado que ya tiene.
            if herramienta_fija and resultado_motor is not None:
                # El motor YA ha calculado. El LLM solo redacta y NO
                # recibe herramientas: si las recibe, puede pedir otra
                # con parametros inventados (por ejemplo, tomar la
                # facturacion como si fuera la renta neta) y la respuesta
                # lleva un numero que no sale del motor.
                #
                # OJO: toolChoice={"none": {}} NO existe en la API de
                # Bedrock (solo auto, any y tool). Para impedir que el
                # modelo use herramientas hay que QUITAR el toolConfig
                # entero del request.
                usar_herramientas = False
            else:
                usar_herramientas = True

            request = {
                "modelId": self.model_id,
                "messages": mensajes,
                "system": [{"text": system}],
                "inferenceConfig": {
                    "temperature": 0.1,     # baja: queremos precision, no creatividad
                    "maxTokens": 1200,
                },
            }
            # El guardrail filtra la inyeccion de prompts y la PII. Sin
            # esto, el guardrail del terraform existe pero no hace nada.
            # OJO: identifier y version tienen que ir juntos (Bedrock
            # exige los dos), por eso la version siempre se manda.
            if self.guardrail_id:
                request["guardrailConfig"] = {
                    "guardrailIdentifier": self.guardrail_id,
                    "guardrailVersion": self.guardrail_version,
                    "trace": "enabled",
                }
            # El toolConfig solo va si el LLM puede (debe) usar
            # herramientas. Si el motor ya ha calculado, se omite: asi el
            # modelo redacta y no puede inventarse otra llamada con
            # parametros erroneos.
            if usar_herramientas:
                request["toolConfig"] = {
                    "tools": TOOL_SCHEMAS,
                    "toolChoice": {"auto": {}},
                }

            try:
                resp = brt.converse(**request)
            except Exception as e:  # noqa: BLE001
                # El guardrail bloquea la peticion lanzando una excepcion
                # (GuardrailIntervenedException). No es un fallo del
                # servicio: es el filtro haciendo su trabajo. Se devuelve
                # un mensaje util en vez de un 500 con el traceback.
                texto_error = str(e)
                if "GuardrailIntervened" in texto_error:
                    print("GUARDRAIL: peticion bloqueada ->", texto_error[:200], file=sys.stderr)
                    return {
                        "respuesta": (
                            "No puedo procesar esa solicitud: el filtro de "
                            "seguridad la ha bloqueado. Prueba a reformular la "
                            "pregunta sin datos personales."
                        ),
                        "herramientas": [],
                        "mock": self.mock,
                    }
                # OJO: una excepcion de CONFIGURACION (por ejemplo
                # "guardrailIdentifier and guardrailVersion must be
                # provided together") NO es un bloqueo del filtro: es un
                # despliegue roto. Se relanza para que se vea en el log
                # como error de verdad y no se disfraca de "contenido
                # bloqueado", que dejaria al usuario sin explicacion.
                raise
            stop = resp["stopReason"]

            if stop == "tool_use" and usar_herramientas:
                msg = resp["output"]["message"]
                mensajes.append(msg)

                resultados = []
                for bloque in msg["content"]:
                    if "toolUse" in bloque:
                        tu = bloque["toolUse"]
                        # Si esta es la herramienta que EL MOTOR eligio, sus
                        # parametros los pone el motor, no el LLM: el modelo
                        # puede inventarse una cifra (por ejemplo, tomar la
                        # facturacion como si fuera la renta neta).
                        if herramienta_fija and tu["name"] == herramienta_fija:
                            out = ejecutar_tool(tu["name"], self.ctx,
                                                params_deterministas)
                        else:
                            out = ejecutar_tool(tu["name"], self.ctx,
                                                tu.get("input", {}))
                        llamadas.append({
                            "tool": tu["name"],
                            "input": tu.get("input", {}),
                            "resultado": out["resultado"],
                            "regla": out["regla"],
                        })
                        self.trace.append(llamadas[-1])
                        # OJO: la API de Bedrock exige el bloque "toolResult".
                        # {"toolUseId":..., "content":[...]} a pelo se rechaza con
                        # "Invalid number of parameters set for tagged union
                        # structure messages[N].content[0]" y TODO el chat con
                        # IA falla. El resultado de la herramienta SIEMPRE va
                        # envuelto en toolResult.
                        resultados.append({
                            "toolResult": {
                                "toolUseId": tu["toolUseId"],
                                "content": [{
                                    "text": json.dumps(out, ensure_ascii=False, default=str)
                                }],
                            }
                        })

                mensajes.append({"role": "user", "content": resultados})
                continue

            # Respuesta final en texto
            #
            # OJO: Nova Pro devuelve un bloque <thinking>...</thinking> con su
            # razonamiento antes del texto final. Si se muestra en crudo, el
            # usuario lee "Para calcular la retencion de IRPF... Debo pedir al
            # usuario..." como si fuera la respuesta final: el LLM se ve
            # pensando en voz alta y, peor, parece que no sabe calcular.
            # Se quita el bloque de razonamiento: al usuario le interesa la
            # respuesta, no el borrador.
            texto = "".join(
                b["text"] for b in resp["output"]["message"]["content"] if "text" in b
            )
            texto = _sin_thinking(texto)

            # Si el motor calculo por su cuenta, la traza debe decirlo:
            # el usuario ve QUE se ha usado y la regla aplicada.
            if herramientas_fijas and not llamadas:
                llamadas = [{
                    "tool": _n,
                    "input": params_deterministas,
                    "resultado": _o["resultado"],
                    "regla": _o.get("regla", ""),
                } for _n, _o in (resultados_motor or [])]

            return {"respuesta": texto, "herramientas": llamadas, "mock": False}

        return {
            "respuesta": "Se ha alcanzado el limite de iteraciones del agente.",
            "herramientas": llamadas,
            "mock": False,
        }

    # -- Implementacion mock (para demo y tests) -------------------------
    # ORDEN CRITICO: las reglas se evaluan de arriba abajo y gana la primera.
    # "cotizo"/"cotizacion" (CASS) debe ir antes que "renta"/"impuesto" (IRPF),
    # porque una pregunta de cotizacion suele mencionar tambien la renta.
    _REGLAS_ROUTER: list[tuple[tuple[str, ...], str, list[str]]] = [
        # ── LAS DECISIONES DE COMPRA ──
        #
        # "Quiero comprar un coche de 30.000 euros" NO es una pregunta
        # de CASS ni de IRPF: es la pregunta de un asesor. Y va la
        # PRIMERA, porque si no, cae en "cuanto me queda" (que es
        # "cuanto me queda" con el CASS) y el motor responde con la
        # cuota de la CASS en vez de con si la compra cabe.
        (("puedo comprar", "puedo permitirme", "me puedo permitir",
          "me puedo permitir", "me允许", "queria comprar", "quiero comprar",
          "querria comprar", "queria comprarme", "quiero comprarme",
          "comprar un coche", "comprar un carro", "comprar un vehiculo",
          "comprar coche", "comprar carro", "comprar vehiculo",
          "comprar una casa", "comprar casa", "comprar vivienda",
          "comprar un piso", "comprar piso", "comprar el local",
          "comprar maquinaria", "comprar una maquina", "comprar equipo",
          "comprar una nave", "comprar nave", "comprarMaterial",
          "me sale comprar", "me conviene comprar", "meVendría", "me vendria",
          "afford", "can i buy", "can i afford", "should i buy",
          "je peux acheter", "posso comprar", "puedo comprar",
          "meur", "kann ich kaufen"),
         "evaluar_compra", ["objetivo", "importe"]),
        # "y si" / "en vez de" / "que pasaria" son preguntas de RECALCULO sobre
        # una decision. Si la pregunta menciona un coste de empleado o un
        # sueldo, es una simulacion de contratacion aunque no diga
        # "contratar" (p.ej. "¿y si el sueldo es de 2.900?"). Sin esto, la
        # pregunta cae en "analizar_tesoreria" y el pitch se rompe en la
        # segunda vuelta, que es justo el momento en que el jurado ve que
        # no es una calculadora.
        (("y si", "y si el", "en vez de", "en lugar de", "que pasaria",
          "que pasaría", "qué pasaría", "subo el sueldo", "subir el sueldo",
          "pago mas", "cobro mas", "cambio el sueldo", "cambiar el sueldo"),
         "simular_contratacion", ["coste_mensual_empleado"]),
        (("contratar", "contratar", "emplead", "empleado", "nómina", "nomina",
          "contratacion", "sueldo", "brutos"),
         "simular_contratacion", ["coste_mensual_empleado"]),
        # "salta"/"umbral" antes que "tramo": una pregunta sobre el SALTO de
        # tramo es de crossover, no de cuota.
        (("salta", "salto", "umbral", "crossover", "a partir de cuando", "punto"),
         "detectar_crossover_fiscal", []),
        # El TOTAL de la carga fiscal va antes que las cuotas sueltas: si
        # la pregunta pide "cuanto me queda" o "cuanto pago en total", el
        # motor tiene que devolver el total. Si solo se calcula el tramo
        # de CASS, el LLM suma (o resta) por su cuenta y se inventa un
        # total que NO sale del motor.
        (("cuanto me queda", "cuanto queda", "cuanto pago", "cuanto pago en total",
          "total de impuestos", "total de impuestos", "cuanto me cuesta",
          "carga fiscal", "cuanto se va", "cuanto me llevo"),
         "resumen_carga_fiscal", []),
        (("cotizo", "cotizacion", "cotización", "cass", "seguridad social", "cuota mensual"),
         "tramo_cass", []),
        # El cierre del bucle va ANTES de "fuga"/"suscripcion": si la pregunta
        # es "hiciste caso" o "cumpliste", el veredicto manda sobre el
        # hallazgo de fugas.
        (("hiciste caso", "hizo caso", "cumpliste", "cumplido",
          "mis consejos", "mi consejo", "cerrar el bucle", "cierre", "cierra el ciclo",
          "reporta sobre", "te reportas", "me reportas"),
         "cerrar_ciclo", []),
        (("fuga", "suscrip", "duplicad", "sobra", "ahorrar", "gastar",
          "no uso", "escapa", "escapando"),
         "detectar_fugas", []),
        (("caja", "quiebre", "aguanto", "runway", "liquidar", "morir",
          "queda de caja", "tengo en caja", "durante cuantos meses"),
         "proyectar_caja", ["meses"]),
        (("irpf", "impuesto", "tribut"),
         "calcular_irpf", []),
        (("igi",),
         "calcular_igi", []),
        (("facturar", "facturacion", "cuanto facturo", "optimizar"),
         "punto_optimo_facturacion", []),
        (("categoria", "donde se va", "resumen", "renta"),
         "analizar_tesoreria", []),
    ]

    def _preguntar_mock(self, pregunta: str) -> dict:
        """
        Mock sin LLM. Enruta por palabras clave y ejecuta la herramienta real.
        Sirve para validar el contrato de herramientas y ensayar la demo
        offline. Los numeros son identicos a los de produccion.
        """
        p = pregunta.lower()
        herramienta = "analizar_tesoreria"
        args: dict = {}

        for claves, nombre, params in self._REGLAS_ROUTER:
            if any(k in p for k in claves):
                herramienta = nombre
                break

        # Extraer numeros de la pregunta para las herramientas que los necesitan
        import re
        numeros = re.findall(r"(\d[\d.,]*)\s*(?:€|euros|eur|/mes|al mes|al año|anual)?", p)
        def _num(idx=0):
            if len(numeros) <= idx:
                return None
            try:
                return float(numeros[idx].replace(".", "").replace(",", "."))
            except ValueError:
                return None

        if herramienta == "simular_contratacion":
            args["coste_mensual_empleado"] = _num(0) or 2400.0
            args["margen_bruto"] = 0.70
        elif herramienta == "proyectar_caja":
            args["meses"] = 12
        elif herramienta in ("detectar_crossover_fiscal", "tramo_cass", "calcular_irpf", "calcular_igi"):
            # Si la pregunta trae un numero, ese manda. Si NO trae ninguno,
            # se usa la renta neta del contexto (el perfil de demo) en vez de
            # pasar None: pasar None explicitamente hacia que la herramienta
            # no pueda aplicar su fallback y devuelva "falta la renta neta".
            n = _num(0)
            if n is not None:
                args["renta_neta"] = n
                if self.ctx.renta_neta_anual is None:
                    self.ctx.renta_neta_anual = Decimal(str(n))
            elif herramienta == "calcular_irpf":
                args["base_general"] = self.ctx.renta_neta_anual
            elif herramienta == "calcular_igi":
                args["base_imponible"] = self.ctx.renta_neta_anual
            elif herramienta == "tramo_cass":
                args["renta_neta"] = self.ctx.renta_neta_anual

        out = ejecutar_tool(herramienta, self.ctx, args)
        llamada = {
            "tool": herramienta,
            "input": args,
            "resultado": out["resultado"],
            "regla": out["regla"],
        }
        self.trace.append(llamada)

        return {
            "respuesta": self._redactar_mock(pregunta, llamada),
            "herramientas": [llamada],
            "mock": True,
        }

    def _redactar_mock(self, pregunta: str, llamada: dict) -> str:
        """Redaccion de ejemplo (en produccion la hace el LLM)."""
        r = llamada["resultado"]
        t = llamada["tool"]

        # Si la herramienta ha devuelto un error (datos que faltan), lo
        # decimos con claridad en vez de reventar. El LLM en produccion
        # haria exactamente esto: pedir el dato que falta.
        if isinstance(r, dict) and r.get("error"):
            faltan = {
                "tramo_cass": "la renta neta anual",
                "calcular_irpf": "la base general (renta neta anual)",
                "calcular_igi": "la base imponible",
                "detectar_crossover_fiscal": "la renta neta anual",
                "simular_contratacion": "la renta neta anual actual",
                "punto_optimo_facturacion": "la renta neta anual",
                "comparar_escenarios": "las dos rentas a comparar",
                "proyectar_caja": "el extracto de movimientos",
                "analizar_tesoreria": "el extracto de movimientos",
                "detectar_fugas": "el extracto de movimientos",
                "cerrar_ciclo": "el extracto de movimientos",
            }.get(t, "los datos necesarios")
            return (
                f"Necesito {faltan} para poder responderte. "
                f"¿Me los puedes dar?\n\n"
                f"(La herramienta `{t}` necesita ese dato: {r['error']})"
            )

        if t == "detectar_fugas":
            if r.get("n_fugas", 0) == 0:
                return ("No he encontrado fugas claras en el periodo analizado.\n\n"
                        "Regla aplicada: " + llamada["regla"])
            lineas = [f"**He encontrado {r['n_fugas']} fugas.** "
                      f"Recuperando lo que no uses: **{_eur(r['recuperable_mensual'])} €/mes** "
                      f"({_eur(r['recuperable_anual'])} €/año).", ""]
            for f in r.get("fugas", [])[:5]:
                lineas.append(f"- **{f['descripcion']}** → {f['accion_sugerida']}")
            lineas += ["", "Regla aplicada: " + llamada["regla"]]
            return "\n".join(lineas)

        if t == "cerrar_ciclo":
            resumen = r.get("resumen", "").strip()
            lineas = [f"**Cierre del ciclo:** {resumen}"]
            if r.get("n_evaluables", 0) > 0:
                def _num(v):
                    try:
                        return float(v)
                    except (TypeError, ValueError):
                        return 0.0
                lineas.append("")
                # "0 a medias" suena raro: solo se mentiona si hay parciales.
                detalle = f"{r.get('cumplidos', 0)} cumplidos"
                if r.get("parciales", 0):
                    detalle += f", {r['parciales']} a medias"
                if r.get("incumplidos", 0):
                    detalle += f", {r['incumplidos']} sin aplicar"
                lineas.append(f"- Consejos evaluados: {r['n_evaluables']} ({detalle})")
                lineas.append(
                    f"- Ahorro real: **{_eur(_num(r.get('ahorro_real_mensual', 0)))} €/mes** "
                    f"frente a {_eur(_num(r.get('ahorro_esperado_mensual', 0)))} €/mes previstos"
                )
            for c in r.get("cierres", [])[:5]:
                exp = c.get("detalle", {}).get("explicacion", "")
                if exp:
                    lineas.append(f"- {exp}")
            lineas += ["", "Regla aplicada: " + llamada["regla"]]
            return "\n".join(lineas)

        if t == "simular_contratacion":
            return (
                f"**Contratar cuesta {_eur(r['coste_nuevo_empleado_anual'])} €/año.**\n\n"
                f"Necesitas facturar **{_eur(r['facturacion_adicional_para_cubrirlo'])} € "
                f"adicionales** para cubrirlo con margen e IGI incluidos "
                f"(de los cuales {_eur(r['igi_adicional'])} € son IGI).\n\n"
                f"Tu tramo CASS actual es el {r['crossover'].get('tipo', 'n/a')}.\n\n"
                f"Regla aplicada: {llamada['regla']}"
            )

        if t == "proyectar_caja":
            return (
                f"**{r['resumen']}**\n\n"
                f"Horizonte: {len(r['meses'])} meses.\n\n"
                f"Regla aplicada: {llamada['regla']}"
            )

        if t == "detectar_crossover_fiscal":
            if not r.get("existe"):
                return f"{r['detalle']}\n\nRegla aplicada: {llamada['regla']}"
            return (
                f"**{r['tipo']}**\n\n{r['detalle']}\n\n"
                f"Regla aplicada: {llamada['regla']}"
            )

        if t == "tramo_cass":
            return (
                f"**Tramo {r['tramo']}** — cuota {_eur(r['cuota_mensual'])} €/mes "
                f"({_eur(r['cuota_anual'])} €/año).\n"
                f"Base: {_eur(r['base_cotizacion'])} €.\n\n"
                f"Regla aplicada: {llamada['regla']}"
            )

        if t == "calcular_irpf":
            return (
                f"**IRPF: {r['cuota_total']:.2f} €** "
                f"(tipo efectivo {r['tipo_efectivo']:.2f}%).\n\n"
                f"{r['calculo']}\n\n"
                f"Regla aplicada: {llamada['regla']}"
            )

        if t == "calcular_igi":
            return (
                f"**IGI: {r['cuota']:.2f} €** sobre base {r['base']:.2f} € "
                f"(tipo {float(r['tipo']) * 100:.1f}%).\n\n"
                f"Regla aplicada: {llamada['regla']}"
            )

        if t == "punto_optimo_facturacion":
            bp = r.get("mejor_punto") or {}
            return (
                f"**El punto optimo de facturacion esta alrededor de "
                f"{bp.get('renta_neta', 0):,.0f} € de renta neta.**\n"
                f"Carga fiscal total: {bp.get('carga_total_anual', 0):,.2f} €/año "
                f"({bp.get('efectivo_sobre_facturacion', 0):.2f}% de lo facturado).\n\n"
                f"{r.get('nota', '')}\n\n"
                f"Regla aplicada: {llamada['regla']}"
            )

        # Analisis de tesoreria (por defecto)
        if "flujo_neto" in r:
            return (
                f"**Flujo neto: {r['flujo_neto']:.2f} €** en el periodo analizado "
                f"({r['periodo']['desde']} a {r['periodo']['hasta']}).\n"
                f"Ingresos: {r['ingresos_totales']:.2f} € | Gastos: {r['gastos_totales']:.2f} €\n"
                f"Media mensual: {r['ingresos_mes']:.2f} € de ingresos, "
                f"{r['gastos_mes']:.2f} € de gastos.\n\n"
                f"Regla aplicada: {llamada['regla']}"
            )

        return json.dumps(r, ensure_ascii=False, indent=2, default=str)
