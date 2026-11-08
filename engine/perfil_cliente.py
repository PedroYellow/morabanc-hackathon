"""
Perfil del cliente: lo que MoraBanc YA sabe de su cliente.

La idea
-------
Un asesor financiero de verdad, cuando te llama, NO te pregunta:

    - "¿Cuánto ganas al año?"         -> lo sabe: leen tus nominas y tu IGI
    - "¿Cuánto tienes en la cuenta?"  -> lo sabe: lo tiene en tiempo real
    - "¿Tributas como sociedad?"       -> lo sabe: eres su cliente, tiene tu
                                           perfil fiscal (autonomo, sociedad,
                                           sociedad andorrana o no...)
    - "¿Qué margen te queda?"          -> lo sabe: lo tiene de tus extractos

Esas preguntas hacen que el producto parezca un formulario. Lo que hace
un buen asesor es lo contrario: llega con el dossier preparado y te
pregunta por la decision que quieres tomar:

    - "Quiero comprar un coche de 30.000 euros"
    - "Voy a comprar el local de mi negocio"
    - "Necesito una maquinaria de 80.000 euros para la nave"
    - "Voy a contratar a dos personas"

Este modulo construye ese dossier a partir de lo que el banco ya tiene
(extractos, nominas, productos contratados, perfil fiscal) y responde
preguntas de capacidad de gasto: "puedo permitirme esto?" en funcion de
la caja, la fiscalidad y el margen.

La regla de oro
---------------
El agente NUNCA pregunta un dato que este en el perfil. Si falta algo,
solo pregunta ESO, y solo si hace falta para la decision concreta que
el usuario quiere tomar.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation


# ─────────────────────────────────────────────────────────────────────
# 1. El perfil: lo que el banco sabe
# ─────────────────────────────────────────────────────────────────────


@dataclass
class ProductoContratado:
    """Un producto que el cliente ya tiene con el banco.

    No hace falta que el usuario lo diga: el banco lo tiene. El agente
    lo usa para no sugerir algo que ya tiene.
    """

    tipo: str  # "prestamo_coche", "hipoteca", "prestamo_maquinaria", "tarjeta"
    saldo_pendiente: Decimal = Decimal("0")
    cuota_mensual: Decimal = Decimal("0")
    tipo_interes: Decimal = Decimal("0")  # 0.05 = 5 %
    fecha_inicio: str = ""


@dataclass
class ProfileCliente:
    """Lo que MoraBanc sabe de su cliente antes de hablar con el.

    Todos los campos son opcionales porque no todos los clientes tienen
    todo: un autonomo recien constituido no tiene nominas, un particular
    no tiene IGI. Lo que no se sabe, no se inventa.
    """

    # ── Identidad y fiscalidad ──
    nombre: str = ""
    #: "persona_fisica" | "autonomo" | "sociedad"
    figura_fiscal: str = ""
    actividad: str = ""
    #: Si es sociedad: la sociedad es andorrana? (el agente lo necesita
    #: para el IGI y para el regimen de precios de transferencia)
    sociedad_andorrana: bool | None = None
    antiguedad: int | None = None

    # ── Economia (lo que sale de nominas y extractos) ──
    renta_neta_anual: Decimal | None = None
    ingresos_brutos_anuales: Decimal | None = None
    margen_bruto: Decimal | None = None
    saldo_actual: Decimal = Decimal("0")
    #: Gasto fijo mensual ya comprometido (alquiler, hipotecas, deudas)
    gasto_fijo_mensual: Decimal = Decimal("0")
    #: Colchon de caja en meses (lo calcula el motor de tesoreria)
    colchon_meses: Decimal | None = None

    # ── Productos que ya tiene ──
    productos: list[ProductoContratado] = field(default_factory=list)

    # ── Objetivos que el propio cliente ha declarado ──
    #: "coche", "vivienda", "maquinaria", "contratar", "ampliar", "invertir"
    objetivo: str = ""
    #: Importe del objetivo, si ya lo sabe
    importe_objetivo: Decimal | None = None

    #: El cliente tiene derecho a las bonificaciones de IRPF (art. 46)
    beneficiario_bonificaciones: bool = True

    #: Idioma en el que habla el cliente. El dossier y las cifras van
    #: siempre en espanol (es el idioma del banco y de la normativa),
    #: pero las RESPUESTAS van en el idioma del cliente.
    idioma: str = "es"

    # ── Lo que NO se sabe (el agente solo pregunta esto) ──
    #: Campos que el banco no tiene y que hacen falta para la decision
    datos_pendientes: list[str] = field(default_factory=list)

    # ─────────────────────────────────────────────────────────────
    # Metodos
    # ─────────────────────────────────────────────────────────────

    def tiene(self, campo: str) -> bool:
        """El banco tiene este dato? (no es None ni esta vacio)"""
        valor = getattr(self, campo, None)
        if valor is None:
            return False
        if isinstance(valor, str) and not valor.strip():
            return False
        if isinstance(valor, (list, dict)) and not valor:
            return False
        return True

    def resumen_para_el_agente(self) -> str:
        """El dossier que se le pasa al agente.

        Se construye como texto porque el agente (Bedrock o ElevenLabs)
        lo lee como contexto. Solo incluye lo que se sabe: si algo no
        se sabe, no aparece, y el agente lo deduce de la lista de
        datos_pendientes.
        """
        lineas: list[str] = []

        if self.tiene("nombre"):
            lineas.append(f"- Cliente: {self.nombre}")
        if self.tiene("figura_fiscal"):
            etiquetas = {
                "persona_fisica": "persona fisica (sin actividad economica)",
                "autonomo": "autonomo (persona fisica con actividad economica)",
                "sociedad": "sociedad",
            }
            etiqueta = etiquetas.get(self.figura_fiscal, self.figura_fiscal)
            linea = f"- Figura fiscal: {etiqueta}"
            if self.figura_fiscal == "sociedad":
                if self.sociedad_andorrana is True:
                    linea += " (sociedad ANDORRANA, sujeta al IGI)"
                elif self.sociedad_andorrana is False:
                    linea += " (sociedad EXTRANJERA: revisar precios de transferencia)"
                else:
                    linea += " (no consta si la sociedad es andorrana)"
            lineas.append(linea)
        if self.tiene("actividad"):
            lineas.append(f"- Actividad: {self.actividad}")
        if self.antiguedad:
            lineas.append(f"- Antiguedad: {self.antiguedad} anos de actividad")

        if self.tiene("renta_neta_anual"):
            lineas.append(f"- Renta neta anual: {self.renta_neta_anual} EUR")
        if self.tiene("ingresos_brutos_anuales"):
            lineas.append(f"- Ingresos brutos anuales: {self.ingresos_brutos_anuales} EUR")
        if self.tiene("margen_bruto"):
            lineas.append(
                f"- Margen bruto: {self.margen_bruto * 100:.0f} % "
                "(lo que se queda de lo facturado tras costes directos)"
            )
        lineas.append(f"- Saldo actual en cuenta: {self.saldo_actual} EUR")
        if self.gasto_fijo_mensual > 0:
            lineas.append(
                f"- Gasto fijo mensual ya comprometido: {self.gasto_fijo_mensual} EUR "
                "(alquiler, prestamos, cuotas)"
            )
        if self.tiene("colchon_meses"):
            lineas.append(
                f"- Colchon de caja: {self.colchon_meses} meses de gastos "
                "cubiertos sin ingresos nuevos"
            )

        if self.productos:
            lineas.append("- Productos que ya tiene con el banco:")
            for p in self.productos:
                detalle = f"  * {p.tipo}: saldo pendiente {p.saldo_pendiente} EUR"
                if p.cuota_mensual > 0:
                    detalle += f", cuota mensual {p.cuota_mensual} EUR"
                if p.tipo_interes > 0:
                    detalle += f", tipo {p.tipo_interes * 100:.2f} %"
                lineas.append(detalle)

        if self.tiene("objetivo"):
            linea = f"- Decision que quiere tomar: {self.objetivo}"
            if self.tiene("importe_objetivo"):
                linea += f" por {self.importe_objetivo} EUR"
            lineas.append(linea)

        if self.datos_pendientes:
            lineas.append(
                "- Datos que el banco NO tiene (preguntalos SOLO si hacen "
                "falta para la decision): " + ", ".join(self.datos_pendientes)
            )

        return "\n".join(lineas)


# ─────────────────────────────────────────────────────────────────────
# 2. La capacidad de gasto
# ─────────────────────────────────────────────────────────────────────


@dataclass
class CapacidadGasto:
    """Si el cliente puede permitirse esa compra, y hasta cuanto.

    No es "puede o no puede": es "puede X, con Y margen, y te aviso
    de Z". Un buen asesor no dice no; dice "si, pero asi".
    """

    cabe: bool
    importe_maximo: Decimal
    importe_pedido: Decimal = Decimal("0")
    margen_mensual_tras_pago: Decimal = Decimal("0")
    meses_colchon_tras_pago: Decimal | None = None
    carga_fiscal_adicional: Decimal = Decimal("0")
    avisos: list[str] = field(default_factory=list)
    regla: str = ""

    def veredicto(self) -> str:
        colchon = (
            f" y {_meses(self.meses_colchon_tras_pago)} meses de colchón"
            if self.meses_colchon_tras_pago is not None
            else ""
        )
        if self.cabe:
            return (
                f"Sí cabe. Puedes gastar hasta {_eur(self.importe_maximo)} EUR. "
                f"Después te quedarían {_eur(self.margen_mensual_tras_pago)} EUR "
                f"de margen al mes{colchon}."
            )
        return (
            f"No cabe de una vez. Tu límite son {_eur(self.importe_maximo)} EUR "
            f"(un {_eur(self.importe_pedido)} EUR te deja el margen mensual en "
            f"{_eur(self.margen_mensual_tras_pago)} EUR)."
        )


# ─────────────────────────────────────────────────────────────────────
# 3. Las decisiones: coche, casa, maquinaria, contratar...
# ─────────────────────────────────────────────────────────────────────

#: Gasto fijo mensual que se considera "prudente" para un autonomo:
#: el 30 % de la renta neta. Es el mismo criterio que usa el motor de
#: tesoreria para marcar una fuga de caja.
RATIO_GASTO_FIJO_PRUDENTE = Decimal("0.30")

#: Colchon minimo de caja que un asesor recomienda antes de una compra
#: grande. Menos de esto y cualquier imprevisto te rompe.
COLCHON_MINIMO_MESES = Decimal("3")

#: Plazo por defecto para un prestamo de compra (meses).
PLAZO_MAXIMO_MESES = 60

#: Tipo de interes por defecto de un prestamo.
TIPO_INTERES_DEFECTO = Decimal("0.05")

#: Coste social aproximado sobre el bruto de un empleado (Andorra).
COSTE_SOCIAL_PORCENTAJE = Decimal("0.21")


def _eur(valor) -> str:
    """Un importe en formato europeo: 7.055,40 EUR.

    El formato por defecto de Python (108000.0) no vale para un
    cliente: en un pitch, un numero asi se lee como anglosajon y
    parece un dato crudo.
    """
    try:
        return f"{float(valor):,.2f}".replace(",", "\x00").replace(".", ",").replace("\x00", ".")
    except (TypeError, ValueError):
        return str(valor)


def _meses(valor) -> str:
    """Un numero de meses con una coma decimal si hace falta."""
    try:
        v = float(valor)
        return (f"{v:.1f}".replace(".", ",") if v != int(v) else str(int(v)))
    except (TypeError, ValueError):
        return str(valor)


def _cuota_mensual(capital: Decimal, tipo_anual: Decimal, meses: int) -> Decimal:
    """Cuota de un prestamo (sistema amortizante, sin comision)."""
    if meses <= 0:
        return Decimal("0")
    if tipo_anual <= 0:
        return (capital / Decimal(meses)).quantize(Decimal("0.01"))
    i = tipo_anual / Decimal(12)
    n = Decimal(meses)
    try:
        cuota = capital * i / (Decimal(1) - (Decimal(1) + i) ** (-n))
    except (ZeroDivisionError, OverflowError, InvalidOperation):
        cuota = capital / n
    return cuota.quantize(Decimal("0.01"))


def _capital_maximo_para_cuota(cuota: Decimal, tipo_anual: Decimal, meses: int) -> Decimal:
    """Cuanto capital puedes pedir pagando como mucho esa cuota."""
    if meses <= 0:
        return Decimal("0")
    i = tipo_anual / Decimal(12)
    n = Decimal(meses)
    if i <= 0:
        return (cuota * Decimal(meses)).quantize(Decimal("0.01"))
    factor = (Decimal(1) - (Decimal(1) + i) ** (-n)) / i
    return (cuota * factor).quantize(Decimal("0.01"))


#: Importe tipico de cada decision, para cuando el usuario no dice el
#: importe. Son los valores de referencia del mercado andorrano.
IMPORTES_TIPICOS: dict[str, Decimal] = {
    "coche": Decimal("30000"),
    "vivienda": Decimal("300000"),
    "maquinaria": Decimal("80000"),
    "contratar": Decimal("28000"),
    "ampliar": Decimal("50000"),
    "invertir": Decimal("20000"),
}


def _importe_por_defecto(objetivo: str) -> Decimal:
    return IMPORTES_TIPICOS.get(objetivo, Decimal("30000"))


def evaluar_compra(
    perfil: ProfileCliente,
    *,
    objetivo: str,
    importe: Decimal | None = None,
    meses_prestamo: int = PLAZO_MAXIMO_MESES,
    tipo_interes: Decimal = TIPO_INTERES_DEFECTO,
    es_activo: bool = True,
    ingreso_mensual_nuevo: Decimal | None = None,
) -> CapacidadGasto:
    """
    La pregunta que de verdad hace un asesor: "¿puedo comprar esto?"

    La respuesta no es si/no: es "si, hasta X, y te aviso de Y".

    El criterio, en una frase: no se puede comprometer mas margen del
    que sobra, ni comerse el colchon de caja.

    - Al contado: manda la caja. No puedes gastar lo que no tienes, y
      tiene que quedar el colchon minimo.
    - Con prestamo: manda la cuota. Lo que se compromete cada mes tiene
      que caber en el margen sostenible (el 30 % de la renta neta menos
      lo ya comprometido). Y el capital total tiene que ser algo que
      puedas pagar sin quedarte sin colchon al final.
    """
    avisos: list[str] = []

    if importe is not None:
        importe = Decimal(str(importe))
    else:
        importe = _importe_por_defecto(objetivo)

    if importe <= 0:
        return CapacidadGasto(
            cabe=False,
            importe_maximo=Decimal("0"),
            avisos=["No me has dicho el importe."],
            regla="Sin importe no hay capacidad de gasto que calcular.",
        )

    renta = perfil.renta_neta_anual if perfil.tiene("renta_neta_anual") else Decimal("0")
    if renta <= 0:
        return CapacidadGasto(
            cabe=False,
            importe_maximo=Decimal("0"),
            importe_pedido=importe,
            avisos=[
                "No tengo tu renta neta anual. La tienes en tu declaracion "
                "de IRPF, o en la que te hacemos con los extractos: me la "
                "dices y te digo cuanto puedes permitirte."
            ],
            regla="La capacidad de gasto sale de la renta neta: el 30 % se "
                   "considera el tope de gasto fijo sostenible.",
        )

    # ── El margen ──
    #
    # El 30 % de la renta neta es el tope de GASTO RECURRENTE (alquiler,
    # cuotas). Menos lo que ya esta comprometido, queda el margen libre.
    tope_sostenible = renta * RATIO_GASTO_FIJO_PRUDENTE
    ya_comprometido = perfil.gasto_fijo_mensual
    margen_disponible = tope_sostenible - ya_comprometido

    if margen_disponible <= 0:
        return CapacidadGasto(
            cabe=False,
            importe_maximo=Decimal("0"),
            importe_pedido=importe,
            margen_mensual_tras_pago=margen_disponible,
            avisos=[
                "Ya tienes todo tu margen fijo comprometido: gastas "
                f"{_eur(ya_comprometido)} EUR al mes y tu tope sostenible es "
                f"{_eur(tope_sostenible)} EUR. Cualquier compra nueva te obliga a "
                "reestructurar lo que ya tienes, no a anadir."
            ],
            regla="Gasto fijo sostenible = 30 % de la renta neta anual.",
        )

    # ── La caja ──
    #
    # Lo que puedes poner de tu bolsillo sin quedarte sin colchon.
    consumo_mensual = max(Decimal("0"), (renta / Decimal(12)) - ya_comprometido)
    maximo_por_caja = Decimal("0")
    if perfil.tiene("colchon_meses") and perfil.saldo_actual > 0 and consumo_mensual > 0:
        maximo_por_caja = max(
            Decimal("0"),
            perfil.saldo_actual - (consumo_mensual * COLCHON_MINIMO_MESES),
        )

    # ── Las dos formas de pagarlo ──
    cuota_prestamo = _cuota_mensual(importe, tipo_interes, meses_prestamo)
    cabe_por_prestamo = cuota_prestamo <= margen_disponible
    cabe_al_contado = maximo_por_caja > 0 and importe <= maximo_por_caja

    if cabe_por_prestamo:
        via = f"con prestamo a {meses_prestamo} meses"
        cuota = cuota_prestamo
    elif cabe_al_contado:
        via = "al contado"
        cuota = Decimal("0")
    else:
        # No cabe de ninguna manera: se informa de la via mas favorable
        # (el prestamo) para que el limite que se da sea el util.
        via = f"con prestamo a {meses_prestamo} meses"
        cuota = cuota_prestamo

    # ── Cuanto puede gastar ──
    #
    # El maximo NO es el capital que se puede pedir prestado: eso no es
    # "lo que puedes gastar", es "lo que puedes pedir prestado". Un
    # asesor nunca dice "puedes gastar 486.000 euros".
    #
    # Al contado: lo que hay en la cuenta sin comerse el colchon.
    # Con prestamo: tu margen anual libre (lo que puedes comprometer al
    # ano sin ahogar la caja), mas lo que puedas adelantar de entrada.
    maximo_por_cuota = _capital_maximo_para_cuota(margen_disponible, tipo_interes, meses_prestamo)
    if via == "al contado":
        maximo = maximo_por_caja
        cabe = importe <= maximo
    else:
        # Con prestamo hay tres topes y mandan los mas bajos:
        #
        # 1. El margen anual libre: lo que puedes comprometer al año
        #    sin ahogar la caja.
        # 2. La carga financiera total: la cuota no puede pasar del
        #    40 % de la renta neta. Un autonomo con una renta de
        #    30.000 no puede meterse un prestamo de 300.000 aunque la
        #    cuota quepa en el margen: se comprometeria toda su renta
        #    con un solo pago.
        # 3. La entrada que puedes adelantar sin comerte el colchon.
        maximo = (margen_disponible * Decimal(12)).quantize(Decimal("0.01"))

        tope_carga_financiera = renta * Decimal("0.40")
        carga_actual = ya_comprometido
        if carga_actual < tope_carga_financiera:
            # El capital que cabe con la cuota maxima que aguanta el
            # tope de carga financiera.
            maximo_por_carga = _capital_maximo_para_cuota(
                tope_carga_financiera - carga_actual, tipo_interes, meses_prestamo
            )
            maximo = min(maximo, maximo_por_carga)

        if maximo_por_caja > 0:
            # La entrada que puedes adelantar no puede comerse el colchon.
            maximo = min(maximo, maximo_por_caja + maximo_por_cuota)

        # Y "cabe" es con TODOS los topes, no solo con la cuota: el
        # importe tiene que estar por debajo del maximo Y la cuota
        # tiene que caber en el margen y en la carga financiera.
        cabe = (
            importe <= maximo
            and cuota <= margen_disponible
            and cuota <= (tope_carga_financiera - carga_actual)
        )

    # ── El colchon de caja despues ──
    meses_colchon: Decimal | None = None
    if perfil.tiene("colchon_meses"):
        consumo_tras = max(
            Decimal("0"),
            (renta / Decimal(12)) - ya_comprometido - cuota,
        )
        if consumo_tras > 0:
            meses_colchon = (perfil.saldo_actual / consumo_tras).quantize(Decimal("0.1"))

    # ── Un objetivo que no es del negocio ──
    #
    # Una vivienda (o cualquier compra personal) no se mide con el
    # margen operativo del negocio: es patrimonio, no gasto. Su limite
    # es el compromiso total: la cuota mas lo que ya debe, y la
    # capacidad de caja para la entrada.
    if objetivo in ("vivienda",) and perfil.figura_fiscal == "autonomo":
        cuota_vivienda = _cuota_mensual(importe, tipo_interes, meses_prestamo)
        # El compromiso total no puede pasar del 40 % de la renta neta.
        tope_compromiso = renta * Decimal("0.40")
        comprometido = ya_comprometido + cuota_vivienda
        cabe_vivienda = comprometido <= tope_compromiso
        entrada_necesaria = (importe - maximo_por_cuota).quantize(Decimal("0.01"))
        if entrada_necesaria > perfil.saldo_actual:
            avisos.append(
                f"Ojo: te faltan {entrada_necesaria - perfil.saldo_actual} EUR "
                "de entrada para la vivienda. Con el saldo que tienes no "
                "llegas, ni aunque te lo presten todo."
            )
            cabe_vivienda = False
        return CapacidadGasto(
            cabe=cabe_vivienda,
            importe_maximo=tope_compromiso.quantize(Decimal("0.01")),
            importe_pedido=importe,
            margen_mensual_tras_pago=(tope_compromiso - comprometido).quantize(Decimal("0.01")),
            meses_colchon_tras_pago=meses_colchon,
            avisos=avisos
            + [
                "Una vivienda no es una compra de negocio: si la usas como "
                "casa habitual no deduces nada, y tu IRPF y tu CASS no bajan. "
                "Y en cuanto a la cuota, cuenta como gasto fijo: te "
                "comprometes con ella los proximos "
                f"{meses_prestamo} meses.",
                "Para que te encaje, mira estas tres vias: (1) entrada mayor "
                "y plazo mas largo, (2) una hipoteca mixta "
                "(parte a tipo fijo, parte variable), o (3) APLAZAR: "
                "esperar dos anos a tener mas colchon te deja pagarla con "
                "la mitad de ingresos ajenos.",
            ],
            regla=(
                f"Compra de vivienda: se mide con el compromiso total, no con "
                f"el margen operativo. El 40 % de la renta neta ({_eur(renta)} EUR) "
                f"es el tope de compromiso mensual: ya tienes "
                f"{_eur(ya_comprometido)} EUR/mes, y la vivienda sumaria "
                f"{_eur(cuota_vivienda)} EUR/mes."
            ),
        )

    # ── Avisos ──
    if meses_colchon is not None and meses_colchon < COLCHON_MINIMO_MESES:
        avisos.append(
            f"Cuidado con la caja: despues de esta compra te quedan "
            f"{_meses(meses_colchon)} meses de colchon. Con menos de "
            f"{_meses(COLCHON_MINIMO_MESES)} meses, un imprevisto te obliga a "
            "vender o a pedir un prestamo en el peor momento."
        )

    if es_activo and perfil.figura_fiscal in ("autonomo", "sociedad"):
        avisos.append(
            "Ojo con el efecto fiscal: un bien como este no es gasto "
            "deducible, es inversion. No te baja el IRPF ni el IGI. Y si lo "
            "financias, solo los intereses del prestamo te los puedes descontar."
        )

    if es_activo and perfil.figura_fiscal == "sociedad":
        avisos.append(
            "Como lo compra la sociedad, mira tambien el IVA y el IGI de "
            "la compra (que se recuperan) y que la inversion no te genera "
            "ingreso hasta que la pongas a producir."
        )

    if objetivo == "contratar":
        avisos.append(
            "Contratar es lo que mas caja se come: el sueldo va con las "
            "contribuciones sociales encima. Y en Andorra, si creces por "
            "encima de cierto umbral, la masa salarial puede cambiar tu "
            "tramo de CASS. Te lo calculo con el motor si me dices el "
            "bruto anual."
        )

    if objetivo == "vivienda" and perfil.figura_fiscal == "autonomo":
        avisos.append(
            "Una vivienda no es una compra de negocio: si la usas como casa "
            "habitual no deduces, y si la alquileres tienes que declarar el "
            "renta y el IGI del alquiler."
        )

    if not perfil.beneficiario_bonificaciones:
        avisos.append(
            "No consta que te apliquen las bonificaciones de IRPF de "
            "autonomos: eso te sube el tipo efectivo. Lo reviso con la "
            "declaracion."
        )

    regla = (
        f"Capacidad de gasto: el 30 % de la renta neta ({_eur(renta)} EUR) es el "
        f"tope de gasto fijo sostenible ({_eur(tope_sostenible)} EUR/mes); ya "
        f"tienes comprometidos {_eur(ya_comprometido)} EUR/mes, asi que te "
        f"quedan {_eur(margen_disponible)} EUR/mes de margen. "
        f"Compra {via}: cuota {_eur(cuota)} EUR/mes."
    )

    return CapacidadGasto(
        cabe=cabe,
        importe_maximo=maximo,
        importe_pedido=importe,
        margen_mensual_tras_pago=(margen_disponible - cuota).quantize(Decimal("0.01")),
        meses_colchon_tras_pago=meses_colchon,
        avisos=avisos,
        regla=regla,
    )


def evaluar_contratacion(
    perfil: ProfileCliente,
    *,
    bruto_anual: Decimal,
    personas: int = 1,
    meses_prestamo: int = PLAZO_MAXIMO_MESES,
    tipo_interes: Decimal = TIPO_INTERES_DEFECTO,
) -> CapacidadGasto:
    """
    Contratar a alguien: la decision que mas caja consume.

    El coste real de un contrato no es el bruto: es el bruto mas las
    contribuciones sociales. En un autonomo, el coste social puede
    llegar al 21 % del bruto. Ese es el numero que hay que mirar.
    """
    avisos: list[str] = []

    bruto_anual = Decimal(str(bruto_anual))
    n = max(1, personas)

    coste_social = (bruto_anual * COSTE_SOCIAL_PORCENTAJE).quantize(Decimal("0.01"))
    coste_total_anual = bruto_anual + coste_social
    coste_mensual_unitario = (coste_total_anual / Decimal(12)).quantize(Decimal("0.01"))

    total_anual = (coste_total_anual * n).quantize(Decimal("0.01"))
    total_mensual = (coste_mensual_unitario * n).quantize(Decimal("0.01"))

    renta = perfil.renta_neta_anual if perfil.tiene("renta_neta_anual") else Decimal("0")
    if renta <= 0:
        return CapacidadGasto(
            cabe=False,
            importe_maximo=Decimal("0"),
            importe_pedido=total_anual,
            avisos=["Necesito tu renta neta anual para decirte si puedes permitirtelo."],
            regla="El 30 % de la renta neta es el tope de gasto fijo sostenible.",
        )

    tope_sostenible = renta * RATIO_GASTO_FIJO_PRUDENTE
    margen_disponible = tope_sostenible - perfil.gasto_fijo_mensual
    maximo_personas = (
        int(margen_disponible / coste_mensual_unitario) if coste_mensual_unitario > 0 else 0
    )
    cabe = total_mensual <= margen_disponible

    if margen_disponible <= 0:
        avisos.append(
            "Ya tienes comprometido todo tu margen fijo: contratar ahora "
            "obligaria a subir precios o a recortar gasto."
        )
    elif not cabe:
        avisos.append(
            f"Contratar a {n} persona(s) cuesta {_eur(total_mensual)} EUR/mes "
            f"(bruto {_eur(bruto_anual)} EUR + {_eur(coste_social)} EUR de seguridad social) "
            f"y te quedan {_eur(margen_disponible)} EUR/mes de margen. "
            f"Solo te entran {maximo_personas} persona(s) hoy."
        )

    avisos.append(
        "Ojo con el CASS: la masa salarial entra en la base de cotizacion. "
        "Si creces, tu base sube y puede saltar de tramo (el salto grande "
        "esta en 40.000 EUR de renta neta). Te lo compruebo con el motor."
    )

    cuota_prestamo = _cuota_mensual(total_anual, tipo_interes, meses_prestamo)

    regla = (
        f"Coste de contratar: bruto {_eur(bruto_anual)} EUR/ano por persona mas un "
        f"{COSTE_SOCIAL_PORCENTAJE * 100:.0f} % de contribuciones sociales = "
        f"{_eur(coste_total_anual)} EUR/ano ({_eur(coste_mensual_unitario)} EUR/mes). "
        f"Tope de gasto fijo sostenible: 30 % de {_eur(renta)} EUR = "
        f"{_eur(tope_sostenible)} EUR/mes; ya comprometido "
        f"{_eur(perfil.gasto_fijo_mensual)} EUR/mes."
    )

    return CapacidadGasto(
        cabe=cabe,
        importe_maximo=(margen_disponible * Decimal(meses_prestamo)).quantize(Decimal("0.01")),
        importe_pedido=total_anual,
        margen_mensual_tras_pago=(margen_disponible - total_mensual).quantize(Decimal("0.01")),
        carga_fiscal_adicional=coste_social * n,
        avisos=avisos,
        regla=regla,
    )


def sugerir_siguiente_pregunta(perfil: ProfileCliente, objetivo: str = "") -> str:
    """
    La UNICA pregunta que el agente deberia hacer, en su defecto.

    Devuelve "" si no falta nada: en ese caso el agente no pregunta,
    propone. Es lo que hace que el producto parezca un asesor y no un
    formulario.
    """
    if objetivo == "contratar":
        if not perfil.tiene("renta_neta_anual"):
            return (
                "Para decirte si puedes contratar a alguien necesito tu renta "
                "neta anual (la de tu declaracion de IRPF)."
            )
        return "De que bruto anual es el contrato?"

    if not perfil.tiene("renta_neta_anual"):
        return (
            "Para decirte si te puedes permitir esto necesito tu renta neta "
            "anual: la que te sale en la declaracion de IRPF."
        )
    if objetivo and not perfil.tiene("importe_objetivo"):
        return f"¿De que importe es la compra?"
    return ""
