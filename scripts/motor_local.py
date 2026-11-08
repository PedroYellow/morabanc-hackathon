"""
El motor de decisiones de MoraBanc, servido en local.

POR QUE EXISTE ESTE
-------------------
La Lambda en AWS es el destino de produccion: es el motor con la
normativa andorrana, ejecutandose en la infraestructura del
hackathon. Pero mientras no haya credenciales de AWS para redesplegar
la Lambda (las del workshop caducan), el VPS sirve el MISMO motor en
local: los mismos ficheros, el mismo Python, los mismos numeros.

No es una maqueta ni una reimplementacion: es el motor de verdad,
corriendo en otro sitio. Cuando la Lambda se redespliegue con el
codigo nuevo, este servidor deja de usarse (el nginx puede dejar de
enrutar a el).

Lo que responde es lo mismo que la Lambda:
    POST /preguntar  {"pregunta": "...", "empresa_id": "...",
                       "saldo_actual": 8500, "renta_neta_anual": 30000,
                       "margen_bruto": 0.7, "actividad": "..."}
    -> {"respuesta": "...", "herramientas": [...]}

Si el motor no puede responder (no hay Bedrock configurado aqui), se
usa el enrutador determinista: las reglas del motor en Python, sin
LLM. Los numeros salen del motor, igual que en AWS.
"""

from __future__ import annotations

import json
import re
import os
import sys
from decimal import Decimal

RAIZ = os.path.dirname(os.path.abspath(__file__))
if RAIZ not in sys.path:
    sys.path.insert(0, RAIZ)

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from agent.bedrock_agent import (
    AgenteFinanciero,
    ContextoEmpresa,
    _detectar_decision_compra,
    ejecutar_tool,
)


# ─────────────────────────────────────────────────────────────────────
# El agente: el mismo de la Lambda, pero en modo determinista (sin
# Bedrock). Los numeros salen del motor; el texto se compone con la
# plantilla que usa el mock del propio motor.
# ─────────────────────────────────────────────────────────────────────


def _respuesta_determinista(ctx: ContextoEmpresa, pregunta: str) -> dict:
    """
    Enruta la pregunta con las mismas reglas del router del motor y
    ejecuta la herramienta. Sin LLM: el texto se arma con el
    resultado de la herramienta, que es donde estan los numeros.
    """
    p = pregunta.lower()

    # 1) Las decisiones de compra (coche, casa, maquinaria, contrato).
    objetivo, importe = _detectar_decision_compra(p)
    if objetivo:
        params: dict = {"objetivo": objetivo, "texto": p}
        if importe is not None:
            params["importe"] = float(importe)
        out = ejecutar_tool("evaluar_compra", ctx, params)
        res = out.get("resultado") or {}
        if "error" not in res:
            partes = [res.get("veredicto", "")]
            for aviso in res.get("avisos", []):
                partes.append(aviso)
            if out.get("regla"):
                partes.append(f"Regla aplicada: {out['regla']}")
            return {
                "respuesta": "\n\n".join(p for p in partes if p),
                "herramientas": [
                    {
                        "tool": "evaluar_compra",
                        "input": params,
                        "resultado": res,
                        "regla": out.get("regla", ""),
                    }
                ],
            }

    # 2) Los pagos: "enviale dinero a mi madre".
    #
    # El ciclo x402 lo tiene el motor de pagos (engine/pagos_x402.py):
    # el 402 con la oferta, la confirmacion y la liquidacion.
    if _es_peticion_pago(p):
        from agent.bedrock_agent import _detectar_pago
        destinatario, importe_pago = _detectar_pago(p)
        params_pago: dict = {"destinatario": destinatario or None}
        if importe_pago is not None:
            params_pago["importe"] = float(importe_pago)
        out_pago = ejecutar_tool("preparar_pago", ctx, params_pago)
        res_pago = out_pago.get("resultado") or {}
        return {
            "respuesta": out_pago.get("regla", ""),
            "herramientas": [
                {
                    "tool": "preparar_pago",
                    "input": params_pago,
                    "resultado": res_pago,
                    "regla": out_pago.get("regla", ""),
                }
            ],
        }

    # 3) El resto: el router del propio motor.
    agente = AgenteFinanciero(ctx)
    herramientas, resultados = agente._herramienta_determinista(pregunta)
    if resultados:
        nombre, out = resultados[0]
        res = out.get("resultado") or {}
        texto = _texto_de_resultado(nombre, res)
        if out.get("regla"):
            # Para el cambio de dato y el pago, la regla ES la frase
            # del asesor: si se anade al final del volcado, el cliente
            # lee dos veces lo mismo, y la primera vez (el volcado)
            # no se entiende.
            if nombre in ("actualizar_dato", "preparar_pago"):
                texto = out["regla"]
            else:
                texto += f"\n\nRegla aplicada: {out['regla']}"
        return {
            "respuesta": texto,
            "herramientas": [
                {
                    "tool": nombre,
                    "input": {},
                    "resultado": res,
                    "regla": out.get("regla", ""),
                }
            ],
        }

    return {
        "respuesta": "",
        "herramientas": [],
    }


def _eur(v) -> str:
    """Un importe en formato europeo: 7.055,40 EUR."""
    try:
        return f"{float(v):,.2f}".replace(",", "\x00").replace(".", ",").replace("\x00", ".")
    except (TypeError, ValueError):
        return str(v)


def _pct(v) -> str:
    try:
        return f"{float(v):.2f}".replace(".", ",") + " %"
    except (TypeError, ValueError):
        return str(v)


#: Como se cuenta cada resultado: (que dice, como se formatea, que
#: unidad tiene). Sin esto, la respuesta al cliente era un volcado de
#: claves del motor ("tramo: 100%; base_cotizacion: 2.672,52"), que
#: no se lee como una respuesta.
_FORMATO_RESULTADOS: dict[str, list[tuple[str, str, str]]] = {
    "tramo_cass": [
        ("cuota_anual", "Tu CASS de 2026 es de", "eur"),
        ("tramo", "en el tramo", "texto"),
        ("cuota_mensual", "Son", "eur_mes"),
        ("base_cotizacion", "Tu base de cotizacion es de", "eur"),
    ],
    "calcular_irpf": [
        ("cuota_total", "Tu IRPF es de", "eur"),
        ("tipo_efectivo", "El tipo efectivo te queda en", "pct"),
    ],
    "calcular_igi": [
        ("cuota", "Tu IGI es de", "eur"),
        ("tipo", "El tipo aplicable es del", "pct"),
    ],
    "resumen_carga_fiscal": [
        ("cuota_anual_cass", "CASS", "eur_anual"),
        ("cuota_anual_irpf", "IRPF", "eur_anual"),
        ("total_carga_fiscal_anual", "El total", "eur_anual"),
    ],
    "detectar_fugas": [
        ("n_fugas", "Tienes", "fugas"),
        ("recuperable_mensual", "Recuperas", "eur_mes"),
        ("recuperable_anual", "Al año son", "eur"),
    ],
    "proyectar_caja": [
        ("meses", "Tu caja aguanta", "meses"),
        ("saldo_minimo", "El punto mas bajo es de", "eur"),
    ],
    "simular_contratacion": [
        ("coste_anual", "Contratar cuesta", "eur_anual"),
        ("facturacion_adicional", "Necesitas facturar", "eur_anual"),
    ],
    "analizar_tesoreria": [
        ("ingresos", "Ingresos", "eur_anual"),
        ("gastos", "Gastos", "eur_anual"),
        ("flujo_neto", "El flujo neto es de", "eur_anual"),
    ],
    # El cambio de un dato del perfil: la frase con las cifras nuevas
    # la pone el motor (la regla), pero el texto principal tambien
    # tiene que ser legible.
    "actualizar_dato": [
        ("valor_nuevo", "El valor nuevo es de", "eur"),
    ],
    # El pago: la oferta la lleva la tarjeta; el texto es la frase.
    "preparar_pago": [
        ("importe_formato", "El envio es de", "eur"),
    ],
}


def _texto_de_resultado(nombre: str, res: dict) -> str:
    """Un texto de asesor, con los numeros en formato europeo."""
    if not isinstance(res, dict):
        return str(res)

    formato = _FORMATO_RESULTADOS.get(nombre)
    if not formato:
        # Sin formato conocido: se(listo los pares clave-valor, pero
        # con las etiquetas en espanol y los numeros en formato
        # europeo.
        return _texto_generico(res)

    frases = []
    for clave, antes, como in formato:
        if clave not in res or res[clave] in (None, ""):
            continue
        valor = res[clave]
        if como == "eur":
            frases.append(f"{antes} {_eur(valor)} EUR.")
        elif como == "eur_mes":
            frases.append(f"{antes} {_eur(valor)} EUR al mes.")
        elif como == "eur_anual":
            frases.append(f"{antes} {_eur(valor)} EUR al año.")
        elif como == "pct":
            v = str(valor)
            if "%" not in v:
                v = f"{v.rstrip('%')} %"
            if frases and not frases[-1].endswith("."):
                frases[-1] = frases[-1] + "."
            frases.append(f"{antes} {v}.")
        elif como == "meses":
            frases.append(f"{antes} {valor} meses.")
        elif como == "fugas":
            frases.append(f"{antes} {valor} fugas en la cuenta.")
        elif como == "texto":
            # La primera letra en mayuscula si empieza la frase, y
            # punto antes si la anterior no lo lleva.
            v = str(valor)
            if v.endswith("%"):
                v = v[:-1].rstrip() + " %"
            if frases and not frases[-1].endswith("."):
                frases[-1] = frases[-1] + "."
            frases.append(f"{antes} {v}.")
        else:
            frases.append(f"{antes} {valor}.")

    if not frases:
        return _texto_generico(res)

    # Cada frase empieza en mayuscula: el texto se lee como una
    # respuesta, no como un volcado de datos.
    capitalizadas = []
    for f in frases:
        f = f.strip()
        if f:
            f = f[0].upper() + f[1:]
        capitalizadas.append(f)
    return " ".join(capitalizadas)


def _texto_generico(res: dict) -> str:
    etiquetas = {
        "cuota_anual": "cuota anual",
        "cuota_mensual": "cuota mensual",
        "tramo": "tramo",
        "base_cotizacion": "base de cotizacion",
        "cuota_total": "cuota total",
        "base_imponible": "base imponible",
        "tipo_efectivo": "tipo efectivo",
        "cuota": "cuota",
        "tipo": "tipo",
        "ingresos": "ingresos",
        "gastos": "gastos",
        "flujo_neto": "flujo neto",
        "n_fugas": "fugas detectadas",
        "recuperable_mensual": "recuperable al mes",
        "recuperable_anual": "recuperable al año",
        "meses": "meses de caja",
        "saldo_minimo": "saldo minimo",
        "saldo_final": "saldo final",
    }
    partes = []
    for k, v in res.items():
        if isinstance(v, (dict, list)):
            continue
        if isinstance(v, (int, float, Decimal)) and not isinstance(v, bool):
            partes.append(f"{etiquetas.get(k, k)}: {_eur(v)} EUR")
        elif v not in (None, ""):
            partes.append(f"{etiquetas.get(k, k)}: {v}")
    return "; ".join(partes)


# ─────────────────────────────────────────────────────────────────────
# El servidor HTTP
# ─────────────────────────────────────────────────────────────────────


#: Como se dicen las partes del texto en cada idioma. Las cifras y
#: los nombres de impuestos NO se tocan: son como estan en la
#: normativa del banco y como el cliente los ve en sus declaraciones.
#: Los patrones del texto del motor, con su version en cada idioma.
#:
#: Se traducen FRASES COMPLETAS, no palabras sueltas: si se cambiaran
#: solo las palabras, quedarian restos en español ("Sí Oui, ça
#: passe"). Y las cifras y los nombres de impuestos (CASS, IRPF, IGI)
#: no se tocan: son como estan en la normativa del banco y como el
#: cliente los ve en sus declaraciones.
PATRONES_IDIOMA: list[tuple[str, dict[str, str]]] = [
    (
        "Sí cabe. Puedes gastar hasta {maximo} EUR. Después te quedarían {margen} EUR de margen al mes",
        {
            "ca": "Sí que hi cap. Pots gastar fins a {maximo} EUR. Et quedaries {margen} EUR de marge al mes",
            "fr": "Oui, ça passe. Vous pouvez dépenser jusqu'à {maximo} EUR. Il vous resterait {margen} EUR de marge par mois",
            "en": "Yes, it fits. You can spend up to {maximo} EUR. You would still have {margen} EUR of margin per month",
            "pt": "Sim, cabe. Pode gastar até {maximo} EUR. Ficaria com {margen} EUR de margem por mês",
        },
    ),
    (
        "No cabe de una vez. Tu límite son {maximo} EUR (un {pedido} EUR te deja el margen mensual en {margen} EUR)",
        {
            "ca": "No cap d'una sola vegada. El teu límit són {maximo} EUR (un {pedido} EUR et deixa el marge mensual en {margen} EUR)",
            "fr": "Non, ça ne passe pas d'un coup. Votre limite est de {maximo} EUR (un {pedido} EUR vous laisse une marge mensuelle de {margen} EUR)",
            "en": "No, it does not fit in one go. Your limit is {maximo} EUR (a {pedido} EUR purchase leaves you a monthly margin of {margen} EUR)",
            "pt": "Não cabe de uma só vez. O seu limite é {maximo} EUR (um {pedido} EUR deixa-lhe uma margem mensal de {margen} EUR)",
        },
    ),
    (
        "Ojo con el efecto fiscal: un bien como este no es gasto deducible, es inversion. No te baja el IRPF ni el IGI. Y si lo financias, solo los intereses del prestamo te los puedes descontar",
        {
            "ca": "Atenció amb l'efecte fiscal: un bé com aquest no és despesa deduïble, és inversió. No et baixa l'IRPF ni l'IGI. I si el finances, només els interessos del prèstet te'ls pots descomptar",
            "fr": "Attention à l'effet fiscal : un bien comme celui-ci n'est pas une charge déductible, c'est un investissement. Ça ne te réduit ni l'IRPF ni l'IGI. Et si tu le finances, seules les intérêts du prêt sont déductibles",
            "en": "Note the tax effect: an asset like this is not a deductible expense, it is an investment. It does not reduce your IRPF or IGI. And if you finance it, only the loan interest is deductible",
            "pt": "Atenção ao efeito fiscal: um bem assim não é uma despesa dedutível, é investimento. Não lhe baixa o IRPF nem o IGI. E se o financiar, só os juros do empréstimo pode descontar",
        },
    ),
    (
        "y {colchon} meses de colchón",
        {
            "ca": "i {colchon} mesos de collat",
            "fr": "et {colchon} mois de coussin",
            "en": "and {colchon} months of buffer",
            "pt": "e {colchon} meses de almofada",
        },
    ),
    (
        "Regla aplicada:",
        {
            "ca": "Regla aplicada:",
            "fr": "Règle appliquée :",
            "en": "Rule applied:",
            "pt": "Regra aplicada:",
        },
    ),
]


#: Las palabras que indican que el cliente quiere enviar dinero. La
#: regla esta en el router del agente, pero aqui se comprueba antes
#: para que el motor determinista no se lo mande a otra herramienta.
_PALABRAS_PAGO = (
    "envia", "enviar", "enviale", "mandar", "manda", "mandale",
    "transferencia", "paga a", "pagale", "pagar a", "que le mande",
    "que le envie", "le envie dinero",
)


def _es_peticion_pago(p: str) -> bool:
    return any(w in p for w in _PALABRAS_PAGO)


def _datos_pago(perfil: str) -> dict:
    """Los contactos y la wallet del cliente (los tiene el banco)."""
    try:
        from engine import pagos_x402
        return pagos_x402.datos_perfil(perfil)
    except Exception:  # noqa: BLE001
        return {"contactos": [], "wallet": {}}


def _traducir(out: dict, idioma: str) -> dict:
    """
    Pasa el texto del motor al idioma elegido por el cliente.

    Se cambian FRASES COMPLETAS (con los numeros dentro), no palabras
    sueltas: asi no quedan restos en español. Las cifras y los nombres
    de impuestos (CASS, IRPF, IGI) se quedan tal cual: son como
    aparecen en la normativa del banco y como el cliente los ve en sus
    declaraciones.

    Como funciona: el patron ("Sí cabe. Puedes gastar hasta {maximo}
    EUR...") se parte por sus marcadores en trozos fijos. Se busca en
    el texto una secuencia de esos trozos, con lo que haya entre
    ellos (los numeros) capturets. Si aparece, se sustituye por la
    frase traducida, con los mismos numeros.
    """
    if idioma not in ("ca", "fr", "en", "pt"):
        return out

    import re as _re

    texto = out.get("respuesta") or ""
    for patron, versiones in PATRONES_IDIOMA:
        version = versiones.get(idioma)
        if not version:
            continue

        # Los trozos fijos del patron y sus marcadores.
        trozos = _re.split(r"\{[a-z_]+\}", patron)
        marcadores = _re.findall(r"\{([a-z_]+)\}", patron)

        # Se busca la secuencia: trozo, numero, trozo, numero...
        patron_busqueda = ""
        for i, trozo in enumerate(trozos):
            patron_busqueda += _re.escape(trozo)
            if i < len(marcadores):
                patron_busqueda += r"([0-9][0-9.,]*)"
        m = _re.search(patron_busqueda, texto)
        if not m:
            continue

        # Los numeros capturados, y la frase traducida con ellos.
        numeros = m.groups()
        traducida = version
        for nombre, valor in zip(marcadores, numeros):
            traducida = traducida.replace("{" + nombre + "}", valor)

        texto = texto[:m.start()] + traducida + texto[m.end():]

    out = dict(out)
    out["respuesta"] = texto
    return out


#: Donde estan los CSV de prueba, uno por perfil.
RUTA_CSVS: dict[str, str] = {
    "freelance": "demo_ceramica.csv",
    "comercio": "demo_ceramica.csv",
    "crecimiento": "demo_ceramica.csv",
    "contratar": "demo_empleado.csv",
    "empleado": "demo_empleado.csv",
    "cierre": "demo_empleado.csv",
}


def _leer_extracto_demo(perfil: str) -> list[dict]:
    """
    Lee el CSV de prueba del perfil y devuelve sus movimientos, del
    mas reciente al mas antiguo.

    El formato del CSV es el mismo que el que sube el cliente: fecha,
    concepto, importe y categoria.
    """
    import csv
    from pathlib import Path

    nombre = RUTA_CSVS.get(perfil, "demo_ceramica.csv")

    # El CSV esta en el directorio de datos del front, que en el VPS
    # esta en /var/www/welcomeandorra/data.
    candidatas = [
        Path(__file__).resolve().parent.parent / "frontend" / "data" / nombre,
        Path("/var/www/welcomeandorra/data") / nombre,
        Path(__file__).resolve().parent / nombre,
    ]
    csv_path = next((p for p in candidatas if p.exists()), None)
    if csv_path is None:
        raise FileNotFoundError(f"No encuentro el CSV {nombre}")

    movimientos: list[dict] = []
    with csv_path.open(encoding="utf-8-sig", newline="") as fh:
        # El extracto del banco viene en formato español: separador
        # ";", fechas DD/MM/AAAA e importes con coma decimal.
        lector = csv.DictReader(fh, delimiter=";")
        for fila in lector:
            crudos = {k.lower().strip(): (v or "").strip() for k, v in fila.items() if k}
            fecha = crudos.get("fecha", "")
            concepto = crudos.get("concepto") or crudos.get("descripcion") or ""
            cat = crudos.get("categoria") or ""

            bruto = (crudos.get("importe") or crudos.get("cantidad") or "0").strip()
            # "1.234,56" o "-950,00": se quitan los puntos de miles y
            # la coma pasa a punto.
            try:
                importe = round(float(bruto.replace(".", "").replace(",", ".")), 2)
            except ValueError:
                continue

            # La fecha se pasa a ISO, para poder ordenarla.
            fecha_iso = fecha
            m = re.match(r"^(\d{2})/(\d{2})/(\d{4})$", fecha)
            if m:
                fecha_iso = f"{m.group(3)}-{m.group(2)}-{m.group(1)}"

            movimientos.append({
                "fecha": fecha_iso,
                "fecha_original": fecha,
                "concepto": concepto,
                "categoria": cat,
                "importe": importe,
            })

    # Del mas reciente al mas antiguo.
    movimientos.sort(key=lambda m: m["fecha"], reverse=True)
    return movimientos


class Handler(BaseHTTPRequestHandler):
    server_version = "MoraBancMotor/1.0"

    def log_message(self, format, *args):
        pass  # silencio: el access log lo pone nginx

    def _json(self, status: int, body: dict):
        crudo = json.dumps(body, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(crudo)))
        self.end_headers()
        self.wfile.write(crudo)

    def do_GET(self):
        ruta = self.path.split("?")[0].rstrip("/")
        if ruta in ("/salud", "/health"):
            self._json(200, {"ok": True, "servicio": "motor-morabanc"})
            return
        if ruta == "/extracto":
            self._servir_extracto()
            return
        if ruta == "/pago":
            self._servir_pago()
            return
        self._json(404, {"error": "no encontrado"})

    def _servir_pago(self):
        """
        El ciclo x402 de un envio de dinero.

        El protocolo funciona asi, y esto lo hace de verdad:

          1. El cliente pide enviar ("enviale 200 a mi madre").
          2. El servidor responde con un 402 Payment Required y la
             oferta: precio, token, red y direccion de destino.
          3. El cliente paga (firma la autorizacion) y reenvia la
             peticion con la cabecera X-PAYMENT.
          4. El facilitator verifica y liquida; el servidor responde
             con el recurso y la cabecera X-PAYMENT-RESPONSE.

        En el hackathon, el facilitator es local (engine/pagos_x402.py):
        el protocolo es real, la cadena no. El pago queda registrado
        con su hash de transaccion, como en una cadena de verdad.

        El envio NUNCA se hace sin que el cliente lo confirme: el
        primer POST (preparar) devuelve la oferta y el estado
        "preparado"; hace falta un segundo POST con
        {"confirmar": true, "reto": ...} para ejecutarlo.
        """
        from urllib.parse import urlparse, parse_qs

        try:
            longitud = int(self.headers.get("Content-Length") or 0)
            cuerpo = json.loads(self.rfile.read(longitud) or b"{}")
        except (ValueError, json.JSONDecodeError):
            self._json(400, {"error": "cuerpo JSON invalido"})
            return

        q = parse_qs(urlparse(self.path).query)
        perfil = (q.get("perfil") or ["freelance"])[0]

        # La cabecera X-PAYMENT es la del protocolo: el cliente paga y
        # reenvia la peticion con ella. Si no viene, se mira el body
        # (util para las pruebas y para los clientes que no pueden
        # mandar cabeceras).
        cabecera_pago = self.headers.get("X-PAYMENT") or self.headers.get("x-payment")
        if cabecera_pago and not cuerpo.get("x_payment"):
            cuerpo["x_payment"] = cabecera_pago

        try:
            from engine import pagos_x402
        except ImportError:
            # El motor puede ejecutarse con el directorio engine/ en el
            # path (en el VPS, el motor esta en su propio directorio).
            import sys as _sys
            _sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            from engine import pagos_x402
        try:
            resultado = pagos_x402.procesar_pago(cuerpo, perfil=perfil)
        except Exception as e:  # noqa: BLE001
            self._json(500, {"error": f"Error en el pago: {e}"})
            return

        codigo = resultado.get("codigo_http", 200)
        self._json(codigo, resultado)

    def _servir_extracto(self):
        """
        Los movimientos del extracto del cliente, para pintar la vista
        "Extracto" de la app.

        En produccion, estos movimientos vienen de la cuenta del
        cliente (OpenSearch / DynamoDB / el core del banco). En el
        hackathon, del CSV de prueba que hay junto al motor.

        Los movimientos se paginan: el extracto de un año puede tener
        cientos de lineas y no tiene sentido mandarlas todas de golpe.
        """
        from urllib.parse import urlparse, parse_qs

        q = parse_qs(urlparse(self.path).query)
        perfil = (q.get("perfil") or ["freelance"])[0]
        pagina = int((q.get("pagina") or ["1"])[0])
        por_pagina = min(int((q.get("por_pagina") or ["50"])[0]), 200)

        try:
            movimientos = _leer_extracto_demo(perfil)
        except Exception as e:  # noqa: BLE001
            self._json(500, {"error": f"No se pudo leer el extracto: {e}"})
            return

        total = len(movimientos)
        inicio = (pagina - 1) * por_pagina
        trozo = movimientos[inicio:inicio + por_pagina]

        ingresos = sum(m["importe"] for m in movimientos if m["importe"] > 0)
        gastos = -sum(m["importe"] for m in movimientos if m["importe"] < 0)

        self._json(200, {
            "perfil": perfil,
            "total": total,
            "pagina": pagina,
            "por_pagina": por_pagina,
            "hay_mas": inicio + por_pagina < total,
            "ingresos": round(ingresos, 2),
            "gastos": round(gastos, 2),
            "resultado": round(ingresos - gastos, 2),
            "periodo": {
                "desde": movimientos[-1]["fecha"] if movimientos else None,
                "hasta": movimientos[0]["fecha"] if movimientos else None,
            },
            "movimientos": trozo,
        })

    def do_POST(self):
        ruta = self.path.split("?")[0].rstrip("/")
        if ruta == "/pago":
            self._servir_pago()
            return
        if ruta != "/preguntar":
            self._json(404, {"error": "no encontrado"})
            return

        try:
            largo = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            largo = 0

        # Tope: el extracto del cliente puede ser grande, pero no
        # infinito (la Lambda tiene el mismo limite).
        if largo > 6 * 1024 * 1024:
            self._json(413, {"error": "El fichero es demasiado grande (max 6 MB)"})
            return

        try:
            cuerpo = json.loads(self.rfile.read(largo).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            self._json(400, {"error": "El cuerpo no es JSON valido"})
            return

        pregunta = (cuerpo.get("pregunta") or "").strip()
        if not pregunta:
            self._json(400, {"error": "Falta la pregunta"})
            return

        ctx = ContextoEmpresa(
            saldo_actual=Decimal(str(cuerpo.get("saldo_actual") or 0)),
            renta_neta_anual=(
                Decimal(str(cuerpo["renta_neta_anual"]))
                if cuerpo.get("renta_neta_anual") is not None
                else None
            ),
            margen_bruto=(
                Decimal(str(cuerpo["margen_bruto"]))
                if cuerpo.get("margen_bruto") is not None
                else None
            ),
            actividad=cuerpo.get("actividad") or "",
            figura_fiscal=cuerpo.get("figura_fiscal") or "",
            # Los contactos y la wallet del cliente. El banco los tiene:
            # es su cliente y sus contactos. El agente no los pregunta.
            contactos=_datos_pago(cuerpo.get("perfil") or "freelance")["contactos"],
            wallet=_datos_pago(cuerpo.get("perfil") or "freelance")["wallet"],
            empresa_id=cuerpo.get("perfil") or "freelance",
        )

        try:
            out = _respuesta_determinista(ctx, pregunta)
        except Exception as e:  # noqa: BLE001
            self._json(500, {"error": f"{type(e).__name__}: {e}"})
            return

        # El idioma forzado (lo elige el cliente en el menu del boton
        # del globo). Las cifras y los nombres de impuestos (CASS, IRPF,
        # IGI) se quedan como estan: son como aparecen en la normativa
        # del banco y en sus declaraciones.
        idioma = (cuerpo.get("idioma") or "").strip().lower()
        if idioma and idioma != "es":
            out = _traducir(out, idioma)

        self._json(200, out)


if __name__ == "__main__":
    puerto = int(os.environ.get("PUERTO", "8811"))
    ThreadingHTTPServer(("127.0.0.1", puerto), Handler).serve_forever()
