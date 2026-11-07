"""
Bucle de cierre — el sistema se reporta sobre su propio consejo pasado.
========================================================================
Modulo de la CAPA 3 del motor: "cierre de la vuelta".

Que es
------
Cuando el motor da un consejo ("cancela esta suscripcion de 65 €/mes",
"factura 42.994 € para contratar"), ese consejo es una HIPOTESIS sobre el
futuro. Este modulo guarda la hipotesis y, cuando llegan movimientos
nuevos, la comprueba contra los hechos y dice cuanto se cumplio.

Por que importa
---------------
Es la diferencia entre un prototipo y un producto: un ERP te dice como fue
el año; un motor de decisiones te dice si te hizo caso a ti mismo. Y es lo
que el jurado no habra visto en ningun otro equipo.

Reglas del proyecto
-------------------
- Determinista: el LLM no calcula nada. Aqui tampoco.
- Todo numero sale de comparar movimientos REALES contra la prediccion.
- Si no hay movimientos suficientes, el modulo lo dice en vez de inventar.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import date, datetime
from decimal import Decimal
from typing import Iterable, Optional

from engine.tesoreria import (
    Fuga,
    Movimiento,
    _d,
    _r2,
    detectar_fugas,
    proyectar_caja,
    resumen_fugas,
)

# --------------------------------------------------------------------------
# Modelo
# --------------------------------------------------------------------------

#: Tipos de consejo que el motor sabe verificar despues.
TIPO_CONSEJO_SUSCRIPCION = "suscripcion"
TIPO_CONSEJO_CONTRATACION = "contratacion"
TIPO_CONSEJO_CAJA = "caja"

#: Umbral minimo de movimientos posteriores al consejo para darlo por
#: evaluable. Por debajo, el veredicto es "aun no hay datos" y NO "cumplido".
MIN_MOVIMIENTOS_EVALUABLES = 2

#: Margen de tolerancia al comparar lo esperado con lo real.
TOLERANCIA_RELATIVA = Decimal("0.10")


@dataclass
class Consejo:
    """
    Una recomendacion del motor, con fecha y con lo que se esperaba que pasara.

    `esperado_mensual` es el efecto economico mensual que el motorAttributes
    a este consejo (ahorro esperado). `clave` identifica el patron en el
    extracto para poder verificarlo despues sin guardar datos sensibles.
    """

    tipo: str
    clave: str
    descripcion: str
    fecha: date
    esperado_mensual: Decimal
    importe_anual: Decimal = Decimal("0")
    meses_previstos: int = 3
    regla: str = ""
    detalle: dict = field(default_factory=dict)

    def a_dict(self) -> dict:
        d = asdict(self)
        d["fecha"] = self.fecha.isoformat()
        d["esperado_mensual"] = str(self.esperado_mensual)
        d["importe_anual"] = str(self.importe_anual)
        return d


@dataclass
class Cierre:
    """
    Resultado de comprobar un consejo contra los movimientos posteriores.
    """

    consejo: Consejo
    evaluable: bool
    veredicto: str            # "cumplido" | "parcial" | "incumplido" | "sin_datos"
    ahorro_real_mensual: Decimal
    ahorro_esperado_mensual: Decimal
    desviacion_pct: Optional[Decimal]
    meses_observados: int
    detalle: dict = field(default_factory=dict)

    def a_dict(self) -> dict:
        return {
            "consejo": self.consejo.a_dict(),
            "evaluable": self.evaluable,
            "veredicto": self.veredicto,
            "ahorro_real_mensual": str(self.ahorro_real_mensual),
            "ahorro_esperado_mensual": str(self.ahorro_esperado_mensual),
            "desviacion_pct": str(self.desviacion_pct) if self.desviacion_pct is not None else None,
            "meses_observados": self.meses_observados,
            "detalle": self.detalle,
        }


# --------------------------------------------------------------------------
# 1. Crear consejos a partir de los hallazgos del motor
# --------------------------------------------------------------------------

def construir_consejos(
    fugas: list[Fuga],
    *,
    fecha: Optional[date] = None,
    meses_previstos: int = 3,
) -> list[Consejo]:
    """
    Convierte las fugas detectadas en consejos verificables.

    Cada fuga de tipo 'suscripcion' produce un consejo: "si cancelas esto,
    ahorras X €/mes". El motor guarda la HIPOTESIS y despues la comprueba.
    """
    fecha = fecha or date.today()
    consejos: list[Consejo] = []

    for f in fugas:
        if f.tipo != "suscripcion":
            continue
        # La clave identifica el patron: concepto normalizado + importe.
        # No guardamos nada mas sensible que eso.
        movs = f.movimientos_involucrados
        concepto = ""
        if movs:
            concepto = movs[0].get("concepto", "")
        clave = f"{_clave_normalizada(concepto)}|{_r2(f.importe_mensual)}"

        consejos.append(Consejo(
            tipo=TIPO_CONSEJO_SUSCRIPCION,
            clave=clave,
            descripcion=f.accion_sugerida,
            fecha=fecha,
            esperado_mensual=f.importe_mensual,
            importe_anual=f.importe_anual,
            meses_previstos=meses_previstos,
            regla="Motor de tesorería · detección de suscripciones (regla determinista)",
            detalle={
                "descripcion_fuga": f.descripcion,
                "confianza": str(f.confianza),
            },
        ))

    return consejos


def _clave_normalizada(concepto: str) -> str:
    import re
    return re.sub(r"\s+", " ", (concepto or "").lower()).strip()


# --------------------------------------------------------------------------
# 2. Verificar los consejos contra los movimientos posteriores
# --------------------------------------------------------------------------

def cerrar_consejos(
    consejos: Iterable[Consejo],
    movimientos: Iterable[Movimiento],
) -> list[Cierre]:
    """
    Comprueba cada consejo contra los movimientos que han ocurrido DESPUES
    de la fecha del consejo.

    - Para un consejo de suscripcion: se busca el mismo cargo en los meses
      posteriores. Si ha desaparecido, el consejo se cumplio y el ahorro
      real es el importe del cargo.
    - Si el cargo sigue apareciendo con el mismo importe, incumplido.
    - Si sigue apareciendo pero con otro importe (subida de precio), parcial.
    """
    movimientos = list(movimientos)
    cierres: list[Cierre] = []

    for c in consejos:
        cierres.append(_cerrar_consejo(c, movimientos))

    # Los cumplidos primero, luego los parciales, luego los incumplidos.
    orden = {"cumplido": 0, "parcial": 1, "incumplido": 2, "sin_datos": 3}
    cierres.sort(key=lambda x: (orden.get(x.veredicto, 9), -x.ahorro_real_mensual))
    return cierres


def _cerrar_consejo(consejo: Consejo, movimientos: list[Movimiento]) -> Cierre:
    posteriores = [m for m in movimientos if m.fecha > consejo.fecha]
    meses_obs = _meses_transcurridos(consejo.fecha, posteriores)

    if len(posteriores) < MIN_MOVIMIENTOS_EVALUABLES:
        return Cierre(
            consejo=consejo,
            evaluable=False,
            veredicto="sin_datos",
            ahorro_real_mensual=Decimal("0"),
            ahorro_esperado_mensual=consejo.esperado_mensual,
            desviacion_pct=None,
            meses_observados=meses_obs,
            detalle={
                "motivo": (
                    f"Solo hay {len(posteriores)} movimientos posteriores al "
                    f"consejo. No hay base suficiente para evaluarlo."
                ),
                "movimientos_posteriores": len(posteriores),
            },
        )

    if consejo.tipo == TIPO_CONSEJO_SUSCRIPCION:
        return _cerrar_suscripcion(consejo, posteriores, meses_obs)

    # Tipos no verificables todavia: se informa con honestidad.
    return Cierre(
        consejo=consejo,
        evaluable=False,
        veredicto="sin_datos",
        ahorro_real_mensual=Decimal("0"),
        ahorro_esperado_mensual=consejo.esperado_mensual,
        desviacion_pct=None,
        meses_observados=meses_obs,
        detalle={
            "motivo": (
                f"El tipo de consejo '{consejo.tipo}' todavia no tiene un metodo "
                "de verificacion implementado."
            )
        },
    )


def _cerrar_suscripcion(
    consejo: Consejo,
    posteriores: list[Movimiento],
    meses_obs: int,
) -> Cierre:
    """
    Busca el cargo original en los movimientos posteriores.

    - 0 apariciones del cargo con el MISMO importe  -> cumplido (se cancelo)
    - apariciones con el mismo importe               -> incumplido (sigue pagando)
    - apariciones con importe DISTINTO               -> parcial (subio de precio)
    """
    # Extraemos concepto e importe esperados de la clave.
    clave = consejo.clave
    if "|" in clave:
        concepto_esp, importe_esp_str = clave.rsplit("|", 1)
        try:
            importe_esp = Decimal(importe_esp_str)
        except Exception:
            importe_esp = consejo.esperado_mensual
    else:
        concepto_esp, importe_esp = "", consejo.esperado_mensual

    # Candidatos: pagos cuyo concepto coincide con el original.
    candidatos = [
        m for m in posteriores
        if m.es_pago and _coincide_concepto(m.concepto, concepto_esp)
    ]

    if not candidatos:
        # No vuelve a aparecer el cargo: el consejo se cumplio.
        # El ahorro es el importe esperado por mes.
        real = _r2(consejo.esperado_mensual)
        return Cierre(
            consejo=consejo,
            evaluable=True,
            veredicto="cumplido",
            ahorro_real_mensual=real,
            ahorro_esperado_mensual=consejo.esperado_mensual,
            desviacion_pct=Decimal("0"),
            meses_observados=meses_obs,
            detalle={
                "explicacion": (
                    f"El cargo '{concepto_esp}' no vuelve a aparecer en los "
                    f"{meses_obs} meses posteriores. Se ahorran {real} €/mes, "
                    f"exactamente lo previsto."
                ),
                "cargos_encontrados": 0,
            },
        )

    # Hay cargos:miramos los importes.
    importes = sorted({_r2(-m.importe) for m in candidatos})
    mismos = [m for m in candidatos if _r2(-m.importe) == importe_esp]

    if len(mismos) >= 2:
        # Sigue pagando lo mismo: incumplido.
        real = Decimal("0")
        return Cierre(
            consejo=consejo,
            evaluable=True,
            veredicto="incumplido",
            ahorro_real_mensual=real,
            ahorro_esperado_mensual=consejo.esperado_mensual,
            desviacion_pct=Decimal("-100"),
            meses_observados=meses_obs,
            detalle={
                "explicacion": (
                    f"El cargo '{concepto_esp}' sigue apareciendo {len(mismos)} veces "
                    f"a {importe_esp} € en los {meses_obs} meses posteriores. "
                    f"El consejo no se aplico."
                ),
                "cargos_encontrados": len(mismos),
                "importes_vistos": [str(i) for i in importes],
            },
        )

    # Importes distintos: el consejo se cumplio en parte (subio el precio
    # o se sustituyo por otro similar).
    mejor = min(importes)
    real = _r2(importe_esp - mejor) if importe_esp > mejor else Decimal("0")
    desvio = (
        _r2((real - consejo.esperado_mensual) / consejo.esperado_mensual * 100)
        if consejo.esperado_mensual > 0
        else Decimal("0")
    )
    veredicto = "cumplido" if abs(desvio) <= TOLERANCIA_RELATIVA * 100 else "parcial"
    if abs(desvio) > TOLERANCIA_RELATIVA * 100:
        veredicto = "parcial"

    return Cierre(
        consejo=consejo,
        evaluable=True,
        veredicto=veredicto,
        ahorro_real_mensual=real,
        ahorro_esperado_mensual=consejo.esperado_mensual,
        desviacion_pct=desvio,
        meses_observados=meses_obs,
        detalle={
            "explicacion": (
                f"El cargo '{concepto_esp}' sigue apareciendo pero a "
                f"{mejor} € en vez de {importe_esp} €. Ahorro real: {real} €/mes "
                f"frente a {consejo.esperado_mensual} €/mes previstos."
            ),
            "cargos_encontrados": len(candidatos),
            "importes_vistos": [str(i) for i in importes],
        },
    )


def _coincide_concepto(concepto_actual: str, concepto_esperado: str) -> bool:
    """
    Dos conceptos coinciden si uno contiene al otro, o si comparten la parte
    significativa (sin digitos ni espacios).
    """
    a = _clave_normalizada(concepto_actual)
    b = _clave_normalizada(concepto_esperado)
    if not a or not b:
        return False
    if a == b or b in a or a in b:
        return True
    # Comparacion por token significativo: "netflix 12,99" vs "NETFLIX"
    import re
    ta = {t for t in re.split(r"\W+", a) if t and not t.isdigit() and len(t) > 2}
    tb = {t for t in re.split(r"\W+", b) if t and not t.isdigit() and len(t) > 2}
    return bool(ta & tb)


def _meses_transcurridos(desde: date, posteriores: list[Movimiento]) -> int:
    if not posteriores:
        return 0
    ultimo = max(m.fecha for m in posteriores)
    return (ultimo.year - desde.year) * 12 + (ultimo.month - desde.month)


# --------------------------------------------------------------------------
# 3. Informe del cierre (el texto que se ensena en el pitch)
# --------------------------------------------------------------------------

def informe_cierre(cierres: list[Cierre]) -> dict:
    """
    Resume el bucle de cierre en numeros y en una frase.

    Es el momento del pitch: "Mes 3: hiciste caso. Ahorraste 780 € y 240 € de IRPF."
    """
    evaluables = [c for c in cierres if c.evaluable]
    cumplidos = [c for c in evaluables if c.veredicto == "cumplido"]
    parciales = [c for c in evaluables if c.veredicto == "parcial"]
    incumplidos = [c for c in evaluables if c.veredicto == "incumplido"]
    sin_datos = [c for c in cierres if not c.evaluable]

    ahorro_real = _r2(sum((c.ahorro_real_mensual for c in evaluables), Decimal("0")))
    ahorro_esperado = _r2(sum((c.ahorro_esperado_mensual for c in evaluables), Decimal("0")))
    desvio = (
        _r2((ahorro_real - ahorro_esperado) / ahorro_esperado * 100)
        if ahorro_esperado > 0
        else Decimal("0")
    )

    if not evaluables:
        resumen = (
            " todavia no hay movimientos suficientes despues del ultimo "
            "consejo para comprobarlo. En el proximo corte te dire si "
            "hiciste caso."
        )
    elif cumplidos and not incumplidos:
        resumen = (
            f"Has seguido {len(cumplidos)} de {len(evaluables)} recomendaciones. "
            f"Llevas ahorrados {ahorro_real} €/mes."
        )
    elif incumplidos and not cumplidos:
        resumen = (
            f"No has aplicado ninguno de los {len(evaluables)} consejos: "
            f"{ahorro_esperado} €/mes siguen escapando."
        )
    else:
        resumen = (
            f"Has seguido {len(cumplidos)} de {len(evaluables)} recomendaciones "
            f"({len(parciales)} a medias). Llevas ahorrados {ahorro_real} €/mes "
            f"de los {ahorro_esperado} €/mes previstos."
        )

    return {
        "n_consejos": len(cierres),
        "n_evaluables": len(evaluables),
        "cumplidos": len(cumplidos),
        "parciales": len(parciales),
        "incumplidos": len(incumplidos),
        "sin_datos": len(sin_datos),
        "ahorro_real_mensual": str(ahorro_real),
        "ahorro_esperado_mensual": str(ahorro_esperado),
        "desviacion_pct": str(desvio),
        "resumen": resumen,
        "cierres": [c.a_dict() for c in cierres],
    }


# --------------------------------------------------------------------------
# 4. Persistencia (JSON plano — DynamoDB en produccion)
# --------------------------------------------------------------------------

def guardar_consejos(consejos: list[Consejo], ruta: str) -> None:
    """Guarda los consejos en un JSON plano. En AWS va a DynamoDB (TTL 30d)."""
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump([c.a_dict() for c in consejos], f, ensure_ascii=False, indent=2)


def cargar_consejos(ruta: str) -> list[Consejo]:
    """Carga los consejos de un JSON plano."""
    with open(ruta, encoding="utf-8") as f:
        datos = json.load(f)
    consejos: list[Consejo] = []
    for d in datos:
        d = dict(d)
        d["fecha"] = date.fromisoformat(d["fecha"])
        d["esperado_mensual"] = Decimal(str(d.get("esperado_mensual", 0)))
        d["importe_anual"] = Decimal(str(d.get("importe_anual", 0)))
        consejos.append(Consejo(**d))
    return consejos
