"""
Motor fiscal andorrano — determinista, sin IA.
=================================================
Fuentes oficiales (verificadas 23-oct-2026):
  - BOPA Decret 28/2026 (28-ene-2026): salari global mensual mitjà cotitzat = 2.672,52 €
    (repartiment de cotitzacio a la CASS per compte propi, Llei 11/2023)
  - CASS: tipus total 22% (10% rama general + 12% rama de jubilacio),
    set bases: 25%, 50%, 62,5%, 75%, 100%, 125%, 137,5%
  - Govern d'Andorra / Llei 5/2014 de l'IRPF (consolidada amb Llei 5/2025):
    art. 35 reduccio minim personal exempt 24.000 €
    art. 43 tipus de gravamen 10%
    art. 46 bonificacio 50% sobre el 10% de la base general, minim personal
           reduït, amb limit maxim de 800 €
    art. 37 minim exempt rendes d'estalvi 3.000 €
  - IGI: 4,5% sobre el rendiment d'activitats economiques

REGLAS DEL PROYECTO
  - El LLM NO hace aritmética. Este módulo es la única fuente de verdad numérica.
  - Toda función devuelve un dict con el detalle del calculo, para poder
    explicar al usuario QUÉ regla se aplicó (requisito del pitch).
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Optional
from decimal import Decimal, ROUND_HALF_UP

# --------------------------------------------------------------------------
# Constantes oficiales
# --------------------------------------------------------------------------

SALARIO_MEDIO_MENSUAL_CASS_2026 = Decimal("2672.52")   # BOPA Decret 28/2026
TIPO_CASS_TOTAL = Decimal("0.22")                        # 10% general + 12% jubilacion
TIPO_CASS_RAMA_GENERAL = Decimal("0.10")
TIPO_CASS_RAMA_JUBILACION = Decimal("0.12")

SALARIO_MINIMO_MENSUAL = Decimal("1568.67")              # des de l'1 de juliol de 2026
SALARIO_MINIMO_HORA_2026_S1 = Decimal("8.80")            # gener - juny 2026
SALARIO_MINIMO_HORA_2026_S2 = Decimal("9.05")            # juliol - desembre 2026

TIPO_IRPF_GENERAL = Decimal("0.10")
REDUCCION_MINIMO_PERSONAL = Decimal("24000.00")
BONIFICACION_ACTIVIDADES_MAX = Decimal("800.00")
REDUCCION_MINIMO_ESTALVI = Decimal("3000.00")

TIPO_IGI = Decimal("0.045")
PAGO_FRACCIONADO_IRPF = Decimal("0.05")

MONEDA = "EUR"


def _d(x) -> Decimal:
    """Convierte a Decimal de forma segura (float -> str -> Decimal)."""
    if isinstance(x, Decimal):
        return x
    if isinstance(x, int):
        return Decimal(x)
    return Decimal(str(x))


def _r2(x: Decimal) -> Decimal:
    """Redondeo a 2 decimales, half-up (convención contable)."""
    return x.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _r0(x: Decimal) -> Decimal:
    return x.quantize(Decimal("1"), rounding=ROUND_HALF_UP)


# ==========================================================================
# 1. CASS — Cotización por cuenta propia
# ==========================================================================

@dataclass
class TramoCASS:
    nombre: str
    pct_base: Decimal
    base: Decimal
    cuota_mensual: Decimal
    rama_general: Decimal
    rama_jubilacion: Decimal
    obligatorio: bool
    condicion: str


# Ordenados de menor a mayor renta neta
_TRAMOS_2026: list[tuple[str, Decimal, bool, str]] = [
    ("25%",   Decimal("0.25"),   False, "Renda neta < 6.000 €, o inici/represa d'activitat (12 primers meses). Opcional."),
    ("50%",   Decimal("0.50"),   False, "Renda neta de 6.000 € a 12.000 €. Base elevada al salari minim (1.568,67 €). Opcional."),
    ("62,5%", Decimal("0.625"),  False, "Renda neta de 12.000 € a 18.000 €. Opcional."),
    ("75%",   Decimal("0.75"),   False, "Renda neta de 18.000 € a 24.000 €. Opcional."),
    ("100%",  Decimal("1.00"),   True,  "Cas general. Tramos inferiors al 100% son opcionals."),
    ("125%",  Decimal("1.25"),   True,  "Renda neta > 40.000 €, o xifra de negoci > 400.000 € (serveis) / 800.000 € (altres)."),
    ("137,5%", Decimal("1.375"), True, "Renda neta > 50.000 €, o xifra de negoci > 500.000 € (serveis) / 900.000 € (altres)."),
]

# Bases oficiales publicadas por CASS para 2026.
# NOTA IMPORTANTE (verificada contra CASS y los tests):
#   - La base del 50% NO es el 50% de 2.672,52 (que daria 1.336,26). La base
#     real es 1.525,33 €, que coincide con el salari minim del primer semestre
#     de 2026 (8,80 €/h). La CASS eleva ese tramo al salari minim.
#   - La base del 62,5% es 1.670,33 €, que corresponde al 62,5% del salari
#     global mensual medio de 2025 sin truncar (2.672,52 x 0,625 = 1.670,325).
_BASES_PUBLICADAS = {
    "25%":   Decimal("668.13"),
    "50%":   Decimal("1525.33"),
    "62,5%": Decimal("1670.33"),
    "75%":   Decimal("2004.39"),
    "100%":  Decimal("2672.52"),
    "125%":  Decimal("3340.65"),
    "137,5%": Decimal("3674.72"),
}

# Base de referencia exacta publicada en el BOPA (Decret 28/2026).
# Con esta base, el 62,5% da 1.670,33 € y el 125% da 3.340,65 € (cifras
# oficiales publicadas por la CASS). Usar la base sin truncar (2.672,525)
# descuadraba el 62,5% en un centimo.
_BASE_SALARIO_MEDIO = Decimal("2672.52")

# Cuotas oficiales publicadas por CASS para 2026
_CUOTAS_PUBLICADAS = {
    "25%":   Decimal("146.99"),
    "50%":   Decimal("335.57"),
    "62,5%": Decimal("367.47"),
    "75%":   Decimal("440.97"),
    "100%":  Decimal("587.95"),
    "125%":  Decimal("734.94"),
    "137,5%": Decimal("808.44"),
}


def _tramo_por_renta(renta_neta_anual: Decimal) -> tuple[str, Decimal]:
    """Determina el tramo CASS por renta neta anual. Devuelve (nombre_tramo, pct_base)."""
    r = _d(renta_neta_anual)
    if r < Decimal("6000"):
        return "25%", Decimal("0.25")
    if r < Decimal("12000"):
        return "50%", Decimal("0.50")
    if r < Decimal("18000"):
        return "62,5%", Decimal("0.625")
    if r < Decimal("24000"):
        return "75%", Decimal("0.75")
    if r <= Decimal("40000"):
        return "100%", Decimal("1.00")
    if r <= Decimal("50000"):
        return "125%", Decimal("1.25")
    return "137,5%", Decimal("1.375")


def tramo_cass_para(
    renta_neta_anual: Decimal,
    *,
    mes_inicio_actividad: bool = False,
    salario_minimo: Decimal = SALARIO_MINIMO_MENSUAL,
) -> TramoCASS:
    """
    Calcula el tramo CASS de un treballador per compte propi.

    La base del 50% se eleva al salari minim cuando el calculo por porcentaje
    queda por debajo (regla CASS / art. 99).
    """
    nombre, pct = _tramo_por_renta(renta_neta_anual)

    if nombre == "25%" and mes_inicio_actividad:
        # Inicio o represa: 12 primeros meses al 25%
        pass
    elif nombre == "50%":
        pct = Decimal("0.50")

    # La base de cada tramo es la que publica oficialmente la CASS (tabla
    # _BASES_PUBLICADAS). Se usa la tabla en lugar de recalcular el porcentaje
    # porque la CASS parte de un salari global mensual medio sin truncar y
    # redondea cada base por separado: 2.672,52 x 0,625 = 1.670,32 € con la
    # base ya redondeada, pero la oficial es 1.670,33 €. La tabla publicada es
    # la fuente de verdad.
    base = _d(_BASES_PUBLICADAS.get(nombre, _BASE_SALARIO_MEDIO * pct))
    if nombre == "50%" and _d(salario_minimo) > Decimal("0"):
        # El tramo 50% puede elevarse al salari minim vigente (regla CASS).
        if _d(salario_minimo) > base:
            base = _d(salario_minimo)

    cuota = _r2(base * TIPO_CASS_TOTAL)
    rama_gen = _r2(base * TIPO_CASS_RAMA_GENERAL)
    rama_jub = _r2(base * TIPO_CASS_RAMA_JUBILACION)
    # La cuota oficial publicada es el 22% de la base redondeada. En algunos
    # tramos la suma de las ramas redondeadas difiere en 0,01 € de la cuota
    # oficial (p.ej. 125%: 334,07 + 400,88 = 734,95 vs 734,94 publicado).
    # Cuando la base NO se ha elevado (base estandar publicada) se usa la
    # cuota oficial; si la base se ha elevado al salari minim, la cuota se
    # recalcula al 22% sobre esa base.
    base_estandar = _d(_BASES_PUBLICADAS.get(nombre, base))
    if base == base_estandar:
        cuota_publicada = _CUOTAS_PUBLICADAS.get(nombre)
        if cuota_publicada is not None:
            cuota = cuota_publicada

    cond = dict((n, c) for n, _, _, c in _TRAMOS_2026)[nombre]

    return TramoCASS(
        nombre=nombre,
        pct_base=pct,
        base=_r2(base),
        cuota_mensual=cuota,
        rama_general=rama_gen,
        rama_jubilacion=rama_jub,
        obligatorio=any(n == nombre for n, _, oblig, _ in _TRAMOS_2026 if oblig),
        condicion=cond,
    )


def cass_anual(tramo: TramoCASS) -> Decimal:
    return _r2(tramo.cuota_mensual * 12)


# ==========================================================================
# 2. IRPF — Impost sobre la renda de les persones fisiques
# ==========================================================================

@dataclass
class ResultadoIRPF:
    base_general: Decimal
    base_ahorro: Decimal
    tipo_general: Decimal
    tipo_ahorro: Decimal
    bonificacion_actividades: Decimal
    cuota_general: Decimal
    cuota_ahorro: Decimal
    cuota_total: Decimal
    tipo_efectivo: Decimal
    explicacion: str


def irpf(
    *,
    base_general: Decimal = Decimal("0"),
    base_ahorro: Decimal = Decimal("0"),
    #: Si True, aplica la bonificacio del art. 46 (rendes de treball / activitats
    #: economiques / capital immobiliari) con el limite de 800 €.
    bonificacion_actividades_aplicable: bool = True,
    #: Reducciones adicionales ya calculadas (minim personal ampliado,
    #: carregues familiars, deducciones, etc.)
    reducciones_extra: Decimal = Decimal("0"),
    #:bonificacion adicional ya calculada (e.g. digitalizacion, creacio llocs treball)
    bonificaciones_extra: Decimal = Decimal("0"),
) -> ResultadoIRPF:
    """
    Calcula el IRPF andorrano.

    Secuencia (Llei 5/2014, arts. 35-46):
      1. Base general = rendes integrades - reduccio minim personal (24.000 €)
         - reduccions extra
      2. Base estalvi = rendes d'estalvi - minim exempt (3.000 €)
      3. Quota = 10% de cada base positiva
      4. Bonificacio art. 46 = 50% del 10% sobre la base general ja reduuida
         pel minim personal, amb limit de 800 €
    """
    bg = _d(base_general)
    ba = _d(base_ahorro)

    bg_reducida = bg - REDUCCION_MINIMO_PERSONAL - _d(reducciones_extra)
    if bg_reducida < 0:
        bg_reducida = Decimal("0")

    ba_reducida = ba - REDUCCION_MINIMO_ESTALVI
    if ba_reducida < 0:
        ba_reducida = Decimal("0")

    cuota_general = _r2(bg_reducida * TIPO_IRPF_GENERAL)
    cuota_ahorro = _r2(ba_reducida * TIPO_IRPF_GENERAL)

    bonif = Decimal("0")
    if bonificacion_actividades_aplicable and bg_reducida > 0:
        bonif = _r2((bg_reducida * TIPO_IRPF_GENERAL) * Decimal("0.50"))
        if bonif > BONIFICACION_ACTIVIDADES_MAX:
            bonif = BONIFICACION_ACTIVIDADES_MAX

    bonif += _d(bonificaciones_extra)

    cuota_total = _r2(cuota_general + cuota_ahorro - bonif)
    if cuota_total < 0:
        cuota_total = Decimal("0")

    tipo_efectivo = (
        _r2(cuota_total / bg * Decimal("100")) if bg > 0 else Decimal("0")
    )

    explicacion = (
        f"Base general {bg} - minim personal 24.000 - reduccions extra "
        f"{_d(reducciones_extra)} = {bg_reducida}. "
        f"Quota 10% = {cuota_general}. "
        f"Bonificacio art. 46 (50% del 10%, limit 800) = {bonif}. "
        f"Base estalvi {ba} - minim exempt 3.000 = {ba_reducida} -> cuota {cuota_ahorro}."
    )

    return ResultadoIRPF(
        base_general=_r2(bg_reducida),
        base_ahorro=_r2(ba_reducida),
        tipo_general=TIPO_IRPF_GENERAL,
        tipo_ahorro=TIPO_IRPF_GENERAL,
        bonificacion_actividades=_r2(bonif),
        cuota_general=cuota_general,
        cuota_ahorro=cuota_ahorro,
        cuota_total=cuota_total,
        tipo_efectivo=tipo_efectivo,
        explicacion=explicacion,
    )


def pago_fraccionado(base_neta_actividad: Decimal) -> Decimal:
    """Pago fraccionado de septiembre: 5% de las rendes netas del periodo anterior."""
    return _r2(_d(base_neta_actividad) * PAGO_FRACCIONADO_IRPF)


# ==========================================================================
# 3. IGI — Impost sobre les activitats economiques
# ==========================================================================

@dataclass
class ResultadoIGI:
    base_imponible: Decimal
    tipo: Decimal
    cuota: Decimal
    calendario: list[dict]
    explicacion: str


def igi(
    base_imponible: Decimal,
    *,
   trimetral: bool = True,
) -> ResultadoIGI:
    """
    IGI al 4,5% sobre el rendimiento de actividades economicas.
    El calendario real de pago (trimestral o anual) depende del regime del
    contribuyente; aqui se genera el calendario trimestral estandar.
    """
    b = _d(base_imponible)
    cuota = _r2(b * TIPO_IGI)

    calendario: list[dict] = []
    if trimetral:
        # Liquidacion trimestral + pago fraccionado (modelo general)
        for i, (q, etiqueta) in enumerate(
            [(1, "1T"), (2, "2T"), (3, "3T"), (4, "4T")]
        ):
            calendario.append(
                {
                    "trimestre": etiqueta,
                    "base_estimada": _r2(b / 4),
                    "cuota_estimada": _r2(cuota / 4),
                    "nota": "Calendario estimado: el IGI real se liquida segun el regime"
                    " (estimacio directa o objectiva) i el termini el fixa el Departament de Tributs.",
                }
            )
    else:
        calendario.append(
            {
                "trimestre": "Anual",
                "base_estimada": b,
                "cuota_estimada": cuota,
                "nota": "Liquidacio anual.",
            }
        )

    return ResultadoIGI(
        base_imponible=b,
        tipo=TIPO_IGI,
        cuota=cuota,
        calendario=calendario,
        explicacion=f"IGI {TIPO_IGI * 100}% sobre base {b} = {cuota}.",
    )


# ==========================================================================
# 4. Crossover — el insight killer
# ==========================================================================

@dataclass
class Crossover:
    existe: bool
    tipo: str
    renta_punto: Decimal
    detalle: str
    delta_anual: Decimal


def crossover_cass(renta_neta_anual: Decimal) -> Crossover:
    """
    Detecta el punto exacto en el que aumentar la renta neta deja de compensar
    por el salto de tramo CASS (y el IRPF).

    Truco: la CASS es un coste FIJO por tramo (no escala con la renta), asi que
    el "crossover" relevante es el punto donde el IRPF marginal (5%->10%)
    supera el ahorro... mas bien: donde la carga total marginal (IRPF + CASS
    que salta) supera el ingreso adicional.
    """
    r = _d(renta_neta_anual)

    # Tramos donde el IRPF sube de tipo efectivo
    if Decimal("24000") < r < Decimal("40000"):
        irpf_actual = irpf(base_general=r)
        irpf_40k = irpf(base_general=Decimal("40000"))
        return Crossover(
            existe=True,
            tipo="Bonificacion IRPF art. 46 toca su techo de 800 €",
            renta_punto=Decimal("40000"),
            detalle=(
                f"Con {r} € de renta neta el IRPF efectivo es {irpf_actual.tipo_efectivo}% "
                f"(bonificación art. 46 todavia sin tope). Matiz importante: el \"5%\" "
                f"que se publica es una simplificacion — el tipo real sube del 0% al 2% "
                f"de forma progresiva entre 24.000 € y 40.000 €, y la bonificacion del 50% "
                f"alcanza su tope de 800 € exactamente en 40.000 € de base. A partir de ahi "
                f"la bonificacion se congela, el IRPF acelera y la CASS pasa del 100% al 125%. "
                f"A 40.000 € la cuota de IRPF pasa de {irpf_actual.cuota_total} € "
                f"a {irpf_40k.cuota_total} €."
            ),
            delta_anual=Decimal("0"),
        )

    if Decimal("40000") < r < Decimal("50000"):
        tr_125 = tramo_cass_para(Decimal("45000"))
        tr_100 = tramo_cass_para(Decimal("39000"))
        delta = cass_anual(tr_125) - cass_anual(tr_100)
        return Crossover(
            existe=True,
            tipo="CASS 100% -> 125%",
            renta_punto=Decimal("40000"),
            detalle=(
                f"Al cruzar 40.000 € de renda neta, la CASS salta del 100% "
                f"({tr_100.cuota_mensual} €/mes) al 125% ({tr_125.cuota_mensual} €/mes): "
                f"+{delta} € al any. El IRPF efectiu tambien sube del 5% al 10%."
            ),
            delta_anual=_r2(delta),
        )

    if Decimal("50000") <= r:
        tr_137 = tramo_cass_para(Decimal("55000"))
        tr_125 = tramo_cass_para(Decimal("45000"))
        delta = cass_anual(tr_137) - cass_anual(tr_125)
        return Crossover(
            existe=True,
            tipo="CASS 125% -> 137,5%",
            renta_punto=Decimal("50000"),
            detalle=(
                f"Al cruzar 50.000 € de renda neta, la CASS salta del 125% "
                f"({tr_125.cuota_mensual} €/mes) al 137,5% ({tr_137.cuota_mensual} €/mes): "
                f"+{delta} € al any."
            ),
            delta_anual=_r2(delta),
        )

    if Decimal("18000") <= r < Decimal("24000"):
        return Crossover(
            existe=True,
            tipo="CASS 75% -> 100%",
            renta_punto=Decimal("24000"),
            detalle=(
                f"Al cruzar 24.000 € de renda neta, la CASS pasa del 75% "
                f"({tramo_cass_para(Decimal("20000")).cuota_mensual} €/mes) al 100% "
                f"({tramo_cass_para(Decimal("25000")).cuota_mensual} €/mes)."
                " El IRPF sigue en 0%, asi que el coste real es solo la CASS."
            ),
            delta_anual=_r2(
                cass_anual(tramo_cass_para(Decimal("25000")))
                - cass_anual(tramo_cass_para(Decimal("20000")))
            ),
        )

    return Crossover(
        existe=False,
        tipo="",
        renta_punto=Decimal("0"),
        detalle="Sense salt de tramo en la situacio actual.",
        delta_anual=Decimal("0"),
    )


def punto_optimo_facturacion(
    renta_neta_anual: Decimal,
    margen_bruto: Decimal,
) -> dict:
    """
    Busca el punto de facturacion donde la carga total (CASS + IRPF + IGI) es
    proporcionalmente menor. Util para el pitch: "facturar mas no siempre compensa".
    """
    base = _d(renta_neta_anual)
    margen = _d(margen_bruto)
    if margen <= 0 or margen >= 1:
        return {"error": "margen_bruto debe estar en (0,1)"}

    carga_bruta = margen  # IGI sobre la facturacion

    def carga_total(renta: Decimal) -> Decimal:
        tr = tramo_cass_para(renta)
        r = irpf(base_general=renta)
        return cass_anual(tr) + r.cuota_total

    # Muestreo de 500 puntos entre 60% y 200% de la renta actual
    inicio = base * Decimal("0.6")
    fin = base * Decimal("2.0")
    pasos = 500
    mejor = None
    for i in range(pasos + 1):
        r = inicio + (fin - inicio) * Decimal(i) / Decimal(pasos)
        if r <= 0:
            continue
        ct = carga_total(r)
        # Tipo efectivo sobre el margen bruto de lo facturado
        if (r * margen) <= 0:
            continue
        efectivo = ct / (r * margen) * Decimal("100")
        if mejor is None or efectivo < mejor["efectivo_sobre_facturacion"]:
            mejor = {
                "renta_neta": _r0(r),
                "carga_total_anual": _r2(ct),
                "efectivo_sobre_facturacion": _r2(efectivo),
            }

    return {
        "renta_actual": _r2(base),
        "margen_bruto": _r2(margen * 100),
        "mejor_punto": mejor,
        "nota": (
            "El coste marginal de facturar mas incluye un salto de tramo CASS, "
            "por lo que la relacion coste/beneficio puede empeorar justo despues "
            "de un umbral. Este es el insight que un ERP de contabilidad no da."
        ),
    }


# ==========================================================================
# 5. Simulador de decisiones
# ==========================================================================

@dataclass
class Escenario:
    nombre: str
    renta_neta_anual: Decimal
    cambios: dict = field(default_factory=dict)


@dataclass
class Comparativa:
    escenario_a: str
    escenario_b: str
    delta_neto_anual: Decimal
    delta_cass_anual: Decimal
    delta_irpf_anual: Decimal
    detalle: dict


def comparar_escenarios(
    esc_a: Escenario,
    esc_b: Escenario,
    *,
    base_ahorro: Decimal = Decimal("0"),
    bonificaciones_extra: Decimal = Decimal("0"),
) -> Comparativa:
    """
    Compara dos escenarios (con/sin una decision) y devuelve el delta neto
    EXACTO, desglosado por componente.
    """
    tr_a = tramo_cass_para(esc_a.renta_neta_anual)
    tr_b = tramo_cass_para(esc_b.renta_neta_anual)
    ir_a = irpf(
        base_general=esc_a.renta_neta_anual,
        base_ahorro=base_ahorro,
        bonificaciones_extra=bonificaciones_extra,
    )
    ir_b = irpf(
        base_general=esc_b.renta_neta_anual,
        base_ahorro=base_ahorro,
        bonificaciones_extra=bonificaciones_extra,
    )

    cass_a = cass_anual(tr_a)
    cass_b = cass_anual(tr_b)

    delta_neto = (
        (esc_b.renta_neta_anual - esc_a.renta_neta_anual)
        - (cass_b - cass_a)
        - (ir_b.cuota_total - ir_a.cuota_total)
    )

    return Comparativa(
        escenario_a=esc_a.nombre,
        escenario_b=esc_b.nombre,
        delta_neto_anual=_r2(delta_neto),
        delta_cass_anual=_r2(cass_b - cass_a),
        delta_irpf_anual=_r2(ir_b.cuota_total - ir_a.cuota_total),
        detalle={
            "a": {
                "renta_neta": _r2(esc_a.renta_neta_anual),
                "tramo_cass": tr_a.nombre,
                "cass_anual": cass_a,
                "irpf": ir_a.cuota_total,
                "neto_tras_fiscalidad": _r2(
                    esc_a.renta_neta_anual - cass_a - ir_a.cuota_total
                ),
            },
            "b": {
                "renta_neta": _r2(esc_b.renta_neta_anual),
                "tramo_cass": tr_b.nombre,
                "cass_anual": cass_b,
                "irpf": ir_b.cuota_total,
                "neto_tras_fiscalidad": _r2(
                    esc_b.renta_neta_anual - cass_b - ir_b.cuota_total
                ),
            },
            "cambios_b": esc_b.cambios,
        },
    )


def simular_contratacion(
    *,
    renta_neta_actual: Decimal,
    margen_bruto: Decimal,
    coste_nuevo_empleado_mensual: Decimal,
    precio_venta_anual_adicional: Decimal = Decimal("0"),
    meses: int = 12,
) -> dict:
    """
    Simula contratar a un empleado: cuanto factura el autonomo para cubrir el
    coste, y que pasa con la CASS y el IRPF.
    """
    margen = _d(margen_bruto)
    coste_mensual = _d(coste_nuevo_empleado_mensual)
    coste_anual = _r2(coste_mensual * 12)

    # Facturacion adicional necesaria para cubrir el coste con el margen bruto
    facturacion_añadida = (
        coste_anual / margen if margen > 0 else Decimal("0")
    )
    # + IGI sobre esa facturacion
    igi_añadido = _r2(facturacion_añadida * TIPO_IGI)
    factura_total_añadida = _r2(facturacion_añadida + igi_añadido)

    renta_con = _d(renta_neta_actual)
    # La renta neta no cambia por contratar (el coste es gasto deducible),
    # pero la IGIfacturada si cambia
    esc_a = Escenario("Sin contratar", renta_con)
    esc_b = Escenario(
        "Contratando",
        renta_con,
        {
            "coste_nuevo_empleado_anual": coste_anual,
            "facturacion_adicional_requerida": factura_total_añadida,
            "igi_adicional": igi_añadido,
        },
    )

    comp = comparar_escenarios(esc_a, esc_b)

    return {
        "coste_nuevo_empleado_anual": coste_anual,
        "margen_bruto": _r2(margen * 100),
        "facturacion_adicional_para_cubrirlo": factura_total_añadida,
        "igi_adicional": igi_añadido,
        "crossover": asdict(crossover_cass(renta_con)),
        "comparativa": {
            "delta_neto_anual": comp.delta_neto_anual,
            "delta_cass_anual": comp.delta_cass_anual,
            "delta_irpf_anual": comp.delta_irpf_anual,
            "detalle": comp.detalle,
        },
        "veredicto": (
            f"Contratar cuesta {coste_anual} €/año. Necesitas facturar "
            f"{factura_total_añadida} € adicionales para cubrirlo con margen "
            f"e IGI incluidos."
        ),
    }
