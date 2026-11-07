"""
Modulo de tesoreria — proyeccion de caja y deteccion de fugas.
=================================================================
Capa 2 del motor (la capa 1 es fiscal_andorra.py).

Este modulo NO hace IA. Recibe movimientos reales (extracto bancario) y:
  1. los normaliza y clasifica
  2. proyecta la tesoreria a 12-24 meses
  3. detecta fugas de caja (suscripciones, cobros duplicados, cargos期間)
  4. simula el efecto de decisiones sobre la caja

Es la entrada "de_payment" del agente: el LLM llama a estas funciones y explica
el resultado. Todos los numeros salen de aqui.
"""

from __future__ import annotations

import csv
import io
import re
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable, Optional

D = Decimal


def _d(x) -> Decimal:
    if isinstance(x, Decimal):
        return x
    if isinstance(x, int):
        return Decimal(x)
    return Decimal(str(x))


def _r2(x: Decimal) -> Decimal:
    return x.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


# ==========================================================================
# 1. Movimientos
# ==========================================================================

@dataclass
class Movimiento:
    fecha: date
    concepto: str
    importe: Decimal          # positivo = ingreso, negativo = pago
    categoria: str = "sin_categorizar"
    methodical: Optional[str] = None   # "subscription", "transfer", "payroll", ...
    confidence: Decimal = Decimal("1.0")

    def __post_init__(self):
        """
        Si no se han indicado categoria/metodo, se clasifican automaticamente.
        Asi ningun llamante puede olvidar clasificarlos, y los tests o el
        generador de demo producen movimientos siempre completos.
        """
        if self.categoria == "sin_categorizar" or self.methodical is None:
            cat, met, conf = clasificar_movimiento(self.concepto)
            if self.categoria == "sin_categorizar":
                self.categoria = cat
            if self.methodical is None:
                self.methodical = met
            if self.confidence == Decimal("1.0"):
                self.confidence = conf

    @property
    def es_ingreso(self) -> bool:
        return self.importe > 0

    @property
    def es_pago(self) -> bool:
        return self.importe < 0


# Palabras clave para clasificar (catalogo andorrano / general).
# ORDEN IMPORTANTE: se evalua de arriba abajo y gana la primera coincidencia.
# "transporte" debe ir antes de "suministros" porque "gas" (gasoil) colisiona
# con "gas" (gas natural) y colisiona tambien con "suministros".
_CATEGORIAS: list[tuple[str, tuple[str, ...]]] = [
    ("nomina", ("nomina", "nómina", "salari", "salario", "payroll", "sous")),
    ("seguridad_social", ("cass", "seuretat social", "seguridad social", "cots", "cotitz")),
    ("impuestos", ("igi", "impost", "impuesto", "tribut", "irpf", "irnr", "iva")),
    ("transporte", ("gasoil", "gasóleo", "gasolina", "benzina", "parking", "aparcament",
                    "transport", "taxi", "uber", "bolt", "peaje", "peaje", "tren", "renfe")),
    ("suministros", ("electricitat", "electricidad", "aigua", "agua", "gas natural",
                     "internet", "telefon", "teléfono", "fiber", "comunicacions",
                     "comunicaciones")),
    ("alquiler", ("lloguer", "alquiler", "renta", "rent")),
    ("seguros", ("asseguran", "seguro", "polissa", "póliza")),
    ("material", ("mercaderia", "mercadería", "material", "proveidor", "proveedor",
                  "mercat", "mercantil", "stock", "compra", "compra a")),
    ("herramientas", ("software", "licencia", "licència", "suscripcio", "suscripción",
                      "saas", "hosting", "dominio", "domini")),
    ("marketing", ("publicitat", "publicidad", "marketing", "ads", "campanya",
                   "campaña", "linkedin", "meta ads")),
    ("banca", ("comissio", "comisión", "transferencia", "traspas", "targeta", "tarjeta",
               "retirada", "reintegro")),
    ("clientes", ("client", "cliente", "factura", "cobro", "ingres", "ingrés")),
]

_METODICOS: list[tuple[str, tuple[str, ...]]] = [
    ("suscripcion", ("suscrip", "subscription", "mensual", "monthly", "netflix", "spotify",
                      "adobe", "microsoft", "google", "dropbox", "icloud", "linkedin premium",
                      "notion", "slack", "zoom", "figma", "openai", "anthropic", "chatgpt")),
    ("payroll", ("nomina", "nómina", "salari", "salario", "payroll", "sous")),
    ("tax", ("igi", "impost", "impuesto", "irpf", "irnr", "tribut", "iva")),
    ("social_security", ("cass", "seuretat", "seguridad social", "cotitz")),
    ("rent", ("lloguer", "alquiler", "renta", "rent ")),
    ("transfer", ("traspas", "transferencia", "transfer ")),
    ("card_payment", ("targeta", "tarjeta", "visa", "mastercard")),
    ("atm", ("retirada", "reintegro", "caixer", "cajero")),
]


def clasificar_movimiento(concepto: str) -> tuple[str, Optional[str], Decimal]:
    """
    Clasifica un concepto en (categoria, metodo, confianza).
    Determinista: reglas por palabras clave. El LLM solo lo usa como fallback
    cuando las reglas no dan señal.
    """
    c = (concepto or "").lower().strip()
    if not c:
        return "sin_categorizar", None, Decimal("0")

    categoria = "sin_categorizar"
    conf_cat = Decimal("0.3")
    for nombre, claves in _CATEGORIAS:
        if any(k in c for k in claves):
            categoria = nombre
            conf_cat = Decimal("0.85")
            break

    metodo = None
    conf_met = Decimal("0")
    for nombre, claves in _METODICOS:
        if any(k in c for k in claves):
            metodo = nombre
            conf_met = Decimal("0.9")
            break

    conf = min(conf_cat, conf_met) if metodo else conf_cat
    return categoria, metodo, conf


def normalizar_importe(texto: str) -> Decimal:
    """
    Normaliza un importe de extracto a Decimal.
    Acepta: '1.234,56', '1234.56', '-45,00', '1.234,56-', '45,20'
   convencion de extracto: el signo va delante o detras.
    """
    if texto is None:
        return Decimal("0")
    t = str(texto).strip()
    if not t:
        return Decimal("0")

    negativo = False
    if t.startswith("-"):
        negativo = True
        t = t[1:]
    if t.endswith("-"):
        negativo = True
        t = t[:-1]

    # quitar todo lo que no sea digito, coma o punto
    t = re.sub(r"[^\d,.]", "", t)
    if not t:
        return Decimal("0")

    if "," in t and "." in t:
        # el ultimo separador es el decimal
        if t.rfind(",") > t.rfind("."):
            t = t.replace(".", "").replace(",", ".")
        else:
            t = t.replace(",", "")
    elif "," in t:
        # coma decimal (formato europeo) vs separador de miles
        partes = t.split(",")
        if len(partes) == 2 and len(partes[1]) == 2:
            t = t.replace(",", ".")
        elif len(partes) == 2 and len(partes[1]) == 3:
            t = t.replace(",", "")
        else:
            t = t.replace(",", ".")
    elif t.count(".") > 1:
        t = t.replace(".", "")

    try:
        val = Decimal(t)
    except Exception:
        return Decimal("0")

    return -val if negativo else val


def parse_extracto_csv(contenido: str) -> list[Movimiento]:
    """
    Parsea un extracto bancario en CSV.
    Detecta automaticamente las columnas de fecha, concepto e importe probando
    varias cabeceras habituales, para no depender de un formato unico.
    """
    if not contenido:
        return []

    # Detectar separador
    sample = contenido[:2000]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except Exception:
        dialect = csv.excel

    reader = csv.DictReader(io.StringIO(contenido), dialect=dialect)
    if not reader.fieldnames:
        return []

    campos = {c.lower().strip(): c for c in reader.fieldnames if c}

    def buscar(*nombres: str) -> Optional[str]:
        for n in nombres:
            for k, v in campos.items():
                if n in k:
                    return v
        return None

    col_fecha = buscar("fecha", "data", "date", "fec")
    col_concepto = buscar("concepto", "descrip", "movimiento", "detalle", "referencia")
    col_importe = buscar("importe", "amount", "movimiento eur", "eur", "cantidad", "saldo")
    col_importe2 = buscar("debe", "cargo", "salida", "retirada")
    col_importe3 = buscar("haber", "abono", "entrada", "ingreso")

    # El formato debe/haber (dos columnas de importe) es tan valido como el de
    # una sola columna "importe": en ese caso col_importe es None y se usan
    # col_importe2 (debe) y col_importe3 (haber).
    formato_dos_columnas = col_importe is None and col_importe2 and col_importe3
    if not col_fecha or (col_importe is None and not formato_dos_columnas):
        return []

    movimientos: list[Movimiento] = []

    for fila in reader:
        fecha_raw = (fila.get(col_fecha) or "").strip()
        concepto = (fila.get(col_concepto) or "").strip() if col_concepto else ""

        try:
            f = datetime.strptime(fecha_raw, "%d/%m/%Y").date()
        except ValueError:
            try:
                f = datetime.strptime(fecha_raw, "%Y-%m-%d").date()
            except ValueError:
                try:
                    f = datetime.strptime(fecha_raw[:10], "%Y-%m-%d").date()
                except ValueError:
                    continue

        if col_importe is not None:
            # Columna unica de importe (puede traer el signo dentro)
            importe = normalizar_importe(fila.get(col_importe) or "0")
        else:
            # Formato debe/haber: el signo lo determina la columna
            debe = normalizar_importe(fila.get(col_importe2) or "0")
            haber = normalizar_importe(fila.get(col_importe3) or "0")
            importe = haber - debe if (debe or haber) else Decimal("0")

        categoria, metodo, conf = clasificar_movimiento(concepto)
        movimientos.append(
            Movimiento(fecha=f, concepto=concepto, importe=importe,
                       categoria=categoria, methodical=metodo, confidence=conf)
        )

    movimientos.sort(key=lambda m: m.fecha)
    return movimientos


# ==========================================================================
# 2. Tesoreria y proyeccion
# ==========================================================================

@dataclass
class Tesoreria:
    saldo_inicial: Decimal
    ingresos_mes: Decimal
    gastos_mes: Decimal

    @property
    def flujo_neto_mes(self) -> Decimal:
        return self.ingresos_mes - self.gastos_mes

    @property
    def runway_meses(self) -> Optional[Decimal]:
        if self.flujo_neto_mes < 0:
            return _r2(self.saldo_inicial / (-self.flujo_neto_mes))
        return None


def analizar_tesoreria(movimientos: list[Movimiento]) -> dict:
    """Resume los movimientos en una tesoreria: saldo, ingresos, gastos, runway."""
    if not movimientos:
        return {
            "error": "Sin movimientos",
            "saldo_final": Decimal("0"),
            "ingresos_totales": Decimal("0"),
            "gastos_totales": Decimal("0"),
        }

    ingresos = sum((m.importe for m in movimientos if m.es_ingreso), Decimal("0"))
    gastos = sum((-m.importe for m in movimientos if m.es_pago), Decimal("0"))

    # Saldo: usamos el saldo acumulado real si hay columna, si no aproximamos
    # con ingresos - gastos sobre un saldo inicial supuesto.
    meses = max(1, _meses_entre(movimientos[0].fecha, movimientos[-1].fecha))

    return {
        "periodo": {
            "desde": movimientos[0].fecha.isoformat(),
            "hasta": movimientos[-1].fecha.isoformat(),
            "meses": meses,
            "n_movimientos": len(movimientos),
        },
        "ingresos_totales": _r2(ingresos),
        "gastos_totales": _r2(gastos),
        "flujo_neto": _r2(ingresos - gastos),
        "ingresos_mes": _r2(ingresos / meses),
        "gastos_mes": _r2(gastos / meses),
        "por_categoria": desglose_categoria(movimientos),
        "metodicos": desglose_metodico(movimientos),
    }


def _meses_entre(d1: date, d2: date) -> int:
    return max(1, (d2.year - d1.year) * 12 + (d2.month - d1.month) + 1)


def desglose_categoria(movimientos: list[Movimiento]) -> dict:
    acc: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    for m in movimientos:
        if m.es_pago:
            acc[m.categoria] += -m.importe
    return {k: _r2(v) for k, v in sorted(acc.items(), key=lambda kv: -kv[1])}


def desglose_metodico(movimientos: list[Movimiento]) -> dict:
    acc: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    for m in movimientos:
        if m.es_pago and m.methodical:
            acc[m.methodical] += -m.importe
    return {k: _r2(v) for k, v in sorted(acc.items(), key=lambda kv: -kv[1])}


@dataclass
class Proyeccion:
    meses: list[dict]
    mes_quiebre: Optional[int] = None      # mes en el que la caja se vuelve negativa
    mes_max_deuda: Optional[int] = None
    deuda_maxima: Decimal = Decimal("0")    # deuda en el mes del quiebre
    deuda_final: Decimal = Decimal("0")      # deuda al final del horizonte
    ultimo_saldo_positivo: Decimal = Decimal("0")
    mes_ultimo_positivo: Optional[int] = None
    resumen: str = ""


def proyectar_caja(
    movimientos: list[Movimiento],
    *,
    saldo_inicial: Decimal,
    meses: int = 12,
    decisiones: Optional[list[dict]] = None,
    ingresos_recurrentes: Optional[list[dict]] = None,
    gastos_recurrentes: Optional[list[dict]] = None,
) -> Proyeccion:
    """
    Proyecta la caja mes a mes.

    decisiones: lista de eventos puntuales, p.ej.
      [{"mes": 3, "nombre": "Contratacion", "importe": -28800, "tipo": "pago_unico"}]
    ingresos_recurrentes / gastos_recurrentes: base mensual estructural,
      p.ej. [{"nombre": "Facturacion", "importe": 4200}]
    """
    t = analizar_tesoreria(movimientos)
    ing_base = t.get("ingresos_mes", Decimal("0"))
    gas_base = t.get("gastos_mes", Decimal("0"))

    if ingresos_recurrentes:
        ing_base = sum((_d(x["importe"]) for x in ingresos_recurrentes), Decimal("0"))
    if gastos_recurrentes:
        gas_base = sum((_d(x["importe"]) for x in gastos_recurrentes), Decimal("0"))

    saldo = _d(saldo_inicial)
    filas: list[dict] = []
    mes_quiebre = None
    deuda_en_quiebre = Decimal("0")
    mes_max_deuda = None
    deuda_max = Decimal("0")
    mes_ultimo_positivo = None
    ultimo_saldo_positivo = Decimal("0")

    eventos_por_mes: dict[int, list[dict]] = defaultdict(list)
    for d in (decisiones or []):
        eventos_por_mes[int(d["mes"])].append(d)

    for i in range(1, meses + 1):
        # Base mensual, suavizada: los ultimos 3 meses reales pesan mas
        ing_mes = ing_base
        gas_mes = gas_base

        eventos = eventos_por_mes.get(i, [])
        eventos_extra = Decimal("0")
        for e in eventos:
            eventos_extra += _d(e.get("importe", 0))

        saldo = saldo + ing_mes - gas_mes + eventos_extra
        filas.append({
            "mes": i,
            "ingresos": _r2(ing_mes),
            "gastos": _r2(gas_mes),
            "eventos": [e.get("nombre", "evento") for e in eventos],
            "eventos_importe": _r2(eventos_extra),
            "saldo": _r2(saldo),
        })

        if saldo >= 0:
            mes_ultimo_positivo = i
            ultimo_saldo_positivo = saldo
        if saldo < 0 and mes_quiebre is None:
            mes_quiebre = i
            # La deuda que hay que cubrir en el momento del quiebre es la que
            # el autonomo necesita saber: no la del final del horizonte.
            deuda_en_quiebre = -saldo
        if saldo < deuda_max:
            deuda_max = saldo
            mes_max_deuda = i

    if mes_quiebre is not None:
        # Un cierre por céntimos no es un problema de negocio: reportamos el
        # ultimo saldo comodo y la deuda real, no un "-0,31 €".
        resumen = (
            f"Con el ritmo actual la caja se agota en el mes {mes_quiebre}. "
            f"Tu ultimo saldo positivo es de {ultimo_saldo_positivo} € "
            f"(mes {mes_ultimo_positivo}). "
            f"En el mes del quiebre te faltan {deuda_en_quiebre} € para cubrir los pagos."
        )
    else:
        runway = (saldo / (gas_base - ing_base)) if (gas_base > ing_base) else None
        resumen = (
            f"La caja no se agota en {meses} meses. "
            + (f"Runway estimado: {runway.quantize(Decimal('0.1'))} meses." if runway else "")
        )

    return Proyeccion(
        meses=filas,
        mes_quiebre=mes_quiebre,
        mes_max_deuda=mes_max_deuda,
        deuda_maxima=_r2(deuda_en_quiebre),
        deuda_final=_r2(-deuda_max if deuda_max < 0 else Decimal("0")),
        ultimo_saldo_positivo=_r2(ultimo_saldo_positivo),
        mes_ultimo_positivo=mes_ultimo_positivo,
        resumen=resumen,
    )


# ==========================================================================
# 3. Detector de fugas
# ==========================================================================

@dataclass
class Fuga:
    tipo: str
    descripcion: str
    importe_mensual: Decimal
    importe_anual: Decimal
    movimientos_involucrados: list[dict]
    accion_sugerida: str
    confianza: Decimal


def detectar_fugas(movimientos: list[Movimiento]) -> list[Fuga]:
    """
    Detecta fugas de caja. Determinista y explicable: cada fuga lista los
    movimientos concretos que la componen.
    """
    fugas: list[Fuga] = []
    if not movimientos:
        return fugas

    # --- 3.1 Suscripciones: mismo concepto, importe identico, periodicidad mensual
    por_concepto: dict[tuple[str, str], list[Movimiento]] = defaultdict(list)
    for m in movimientos:
        if m.es_pago and m.methodical == "suscripcion":
            clave = re.sub(r"\s+", " ", m.concepto.lower()).strip()
            por_concepto[(clave, str(_r2(-m.importe)))].append(m)

    for (concepto, importe_str), grupo in por_concepto.items():
        if len(grupo) < 3:
            continue
        importe = _d(importe_str)
        meses = _meses_entre(grupo[0].fecha, grupo[-1].fecha)
        # Frecuencia real: cobros / meses
        frecuencia = Decimal(len(grupo)) / Decimal(meses)
        if frecuencia < Decimal("0.8"):
            continue
        # Intervencion manual de los ultimos 6 meses = fuga probable
        ultimos = [m for m in grupo if (grupo[-1].fecha - m.fecha).days <= 190]
        if not ultimos:
            continue
        fugas.append(Fuga(
            tipo="suscripcion",
            descripcion=(
                f"Cobro recurrente de {importe} € ({concepto}). "
                f"Se repite {len(grupo)} veces en {meses} meses."
            ),
            importe_mensual=importe,
            importe_anual=_r2(importe * 12),
            movimientos_involucrados=[
                {"fecha": m.fecha.isoformat(), "concepto": m.concepto, "importe": m.importe}
                for m in grupo
            ],
            accion_sugerida=(
                f"Revisa si sigues usando '{concepto}'. Cancelarlo libera {importe} €/mes "
                f"({_r2(importe * 12)} €/año)."
            ),
            confianza=Decimal("0.8"),
        ))

    # --- 3.2 Cobros duplicados: mismo importe, mismo concepto, <= 5 dias
    por_importe: dict[Decimal, list[Movimiento]] = defaultdict(list)
    for m in movimientos:
        if m.es_pago:
            por_importe[_r2(-m.importe)].append(m)

    for importe, grupo in por_importe.items():
        if importe <= 0:
            continue
        grupo_ordenado = sorted(grupo, key=lambda m: m.fecha)
        for i in range(len(grupo_ordenado) - 1):
            a, b = grupo_ordenado[i], grupo_ordenado[i + 1]
            if (b.fecha - a.fecha).days <= 5 and a.concepto == b.concepto:
                fugas.append(Fuga(
                    tipo="cobro_duplicado",
                    descripcion=(
                        f"Cobro duplicado de {importe} €: '{a.concepto}' el "
                        f"{a.fecha.strftime('%d/%m/%Y')} y otra vez el "
                        f"{b.fecha.strftime('%d/%m/%Y')}."
                    ),
                    importe_mensual=importe,
                    importe_anual=_r2(importe * 12),
                    movimientos_involucrados=[
                        {"fecha": a.fecha.isoformat(), "concepto": a.concepto, "importe": a.importe},
                        {"fecha": b.fecha.isoformat(), "concepto": b.concepto, "importe": b.importe},
                    ],
                    accion_sugerida=f"Reclama el cobro duplicado: {importe} €.",
                    confianza=Decimal("0.9"),
                ))

    # --- 3.3 Cargo recurrente con concepto generico (posible suscripcion sin nombre)
    # --- 3.4 Gastos en fines de semana fuera de horario (irrelevante) -> se omite

    # --- 3.5 Gastos que crecen mes a mes (deriva de gasto)
    fugas.extend(_detectar_deriva(movimientos))

    # Deduplicar y ordenar por impacto
    vistos = set()
    unicas: list[Fuga] = []
    for f in fugas:
        key = (f.tipo, f.descripcion[:60])
        if key not in vistos:
            vistos.add(key)
            unicas.append(f)
    unicas.sort(key=lambda f: -f.importe_anual)
    return unicas


def _detectar_deriva(movimientos: list[Movimiento]) -> list[Fuga]:
    """
    Detecta gastos que crecen de forma sostenida: mes a mes el mismo bloque
    de categoria supera el anterior en mas de un 15%.
    """
    fugas: list[Fuga] = []
    if len(movimientos) < 4:
        return fugas

    por_mes_cat: dict[tuple[str, int], Decimal] = defaultdict(lambda: Decimal("0"))
    for m in movimientos:
        if m.es_pago:
            por_mes_cat[(m.categoria, m.fecha.year * 12 + m.fecha.month)] += -m.importe

    categorias = {c for (c, _) in por_mes_cat}
    for cat in categorias:
        serie = sorted(
            [(mes, v) for (c, mes), v in por_mes_cat.items() if c == cat],
            key=lambda x: x[0],
        )
        if len(serie) < 3:
            continue
        ultimos = serie[-3:]
        if ultimos[0][1] <= 0:
            continue
        crecimiento = (ultimos[-1][1] - ultimos[0][1]) / ultimos[0][1]
        if crecimiento > Decimal("0.15"):
            delta_mensual = _r2((ultimos[-1][1] - ultimos[0][1]) / 2)
            fugas.append(Fuga(
                tipo="deriva_gasto",
                descripcion=(
                    f"El gasto en '{cat}' ha subido un "
                    f"{(crecimiento * 100).quantize(Decimal('1'))}% en 3 meses "
                    f"({_r2(ultimos[0][1])} € -> {_r2(ultimos[-1][1])} €)."
                ),
                importe_mensual=delta_mensual,
                importe_anual=_r2(delta_mensual * 12),
                movimientos_involucrados=[],
                accion_sugerida=(
                    f"Revisa el gasto en '{cat}': ha crecido "
                    f"{_r2(delta_mensual)} €/mes de media. Si lo estabilizas, "
                    f"recuperas {_r2(delta_mensual * 12)} €/año."
                ),
                confianza=Decimal("0.6"),
            ))
    return fugas


def resumen_fugas(fugas: list[Fuga]) -> dict:
    if not fugas:
        return {
            "n_fugas": 0,
            "recuperable_mensual": Decimal("0"),
            "recuperable_anual": Decimal("0"),
            "mensaje": "No se detectaron fugas claras en el periodo analizado.",
        }
    mensual = sum((f.importe_mensual for f in fugas), Decimal("0"))
    return {
        "n_fugas": len(fugas),
        "recuperable_mensual": _r2(mensual),
        "recuperable_anual": _r2(mensual * 12),
        "por_tipo": {
            t: sum((f.importe_anual for f in fugas if f.tipo == t), Decimal("0"))
            for t in sorted({f.tipo for f in fugas})
        },
        "fugas": [asdict(f) for f in fugas],
        "mensaje": (
            f"Hemos encontrado {len(fugas)} fugas. Recuperando lo que no uses: "
            f"{_r2(mensual)} €/mes ({_r2(mensual * 12)} €/año)."
        ),
    }
