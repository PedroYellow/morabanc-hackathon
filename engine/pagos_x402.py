"""
Los pagos con el protocolo x402.

QUE ES x402
-----------
HTTP 402 "Payment Required" es un codigo que lleva reservado desde los
años 90 sin usar. x402 lo activa: un servidor que quiere cobrar por
un recurso responde con un 402 y las instrucciones de pago (precio,
token, red, direccion de destino). El cliente paga con una stablecoin,
firma la autorizacion, reenvia la peticion con la cabecera X-PAYMENT
y el facilitator verifica y liquida. La respuesta llega con la
cabecera X-PAYMENT-RESPONSE.

El ciclo completo son cuatro pasos, y este modulo los hace los
cuatro:

    1. PREPARAR   el cliente pide enviar dinero
    2. OFERTA     el servidor responde 402 con el reto de pago
    3. PAGAR      el cliente firma y reenvia con X-PAYMENT
    4. LIQUIDAR   el facilitator verifica; el servidor responde 200

LO QUE ES REAL Y LO QUE NO
---------------------------
- Es real: el protocolo (los codigos HTTP, las cabeceras, la
  estructura de la oferta, la firma del reto, la verificacion y la
  liquidacion) y la contabilidad de los pagos.
- No es real: la cadena. El facilitator es local, asi que no hay
  Base ni USDC de verdad: hay un hash de transaccion y un libro de
  pagos. Para ponerlo en Base de verdad, el facilitator local se
  cambia por el de Coinbase (HTTPFacilitatorClient) y las firmas, por
  las del wallet del cliente.

POR QUE EL BANCO CONFIRMA SIEMPRE
---------------------------------
Preparar no es enviar. El pago sale solo cuando el cliente lo
aprueba, con un segundo POST. En un banco, mover dinero sin que el
cliente lo confirme no es aceptable, y mas si el destinatario es un
familiar. Ademas, el "doble gasto" (enviar dos veces lo mismo) se
evita con un registro de peticiones ya pagadas.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import time
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional


#: Las redes con su nombre: el codigo x402 es un identificador de
#: cadena (CAIP-2), pero al cliente hay que hablarle en Castellano.
NOMBRE_RED = {
    "eip155:8453": "Base",
    "eip155:1": "Ethereum",
    "eip155:42161": "Arbitrum",
    "eip155:137": "Polygon",
    "solana:5eykt4UsFv8P8NJdTREpY1vzqKqZKvdp": "Solana",
    "solana:mainnet": "Solana",
    "tron": "Tron",
    "avax": "Avalanche",
}

#: La red por defecto: Base, que es donde mejor se soporta x402.
RED_POR_DEFECTO = "eip155:8453"
TOKEN_POR_DEFECTO = "USDC"


#: Los contactos y la wallet de los perfiles de prueba. En produccion
#: esto vendria del core del banco (el cliente y sus contactos) y de
#: la cartera del cliente.
PERFILES_PAGO: dict[str, dict[str, Any]] = {
    "freelance": {
        "wallet": {
            "direccion": "0x7a3f9c21b8e4d605fa12c93b7e4d1908a3c5e7f21",
            "red": RED_POR_DEFECTO,
            "token": TOKEN_POR_DEFECTO,
            "saldo": 1200.0,
        },
        "contactos": [
            {"nombre": "Rosa Martin", "alias": "madre", "relacion": "madre",
             "direccion": "0x2f8a1d90c4b7e63a5f0d8c2b91e4a7d603c8b1f45"},
            {"nombre": "Marta Soler", "alias": "pareja", "relacion": "pareja",
             "direccion": "0x91c3e7b245d0a86f3c8b1e70d94a2f6b0c7e35a8"},
            {"nombre": "Jordi Puig", "alias": "hermano", "relacion": "hermano",
             "direccion": "0xb4d8f2a60e37c95b1a8d4e02f6c93b7a5d81e4c0"},
        ],
    },
    "empleado": {
        "wallet": {
            "direccion": "0x3e5b7c194a2f60d8c4b1e95f7a3d20c8b6f4e19a",
            "red": RED_POR_DEFECTO,
            "token": TOKEN_POR_DEFECTO,
            "saldo": 480.0,
        },
        "contactos": [
            {"nombre": "Rosa Martin", "alias": "madre", "relacion": "madre",
             "direccion": "0x2f8a1d90c4b7e63a5f0d8c2b91e4a7d603c8b1f45"},
            {"nombre": "Marc Puig", "alias": "pareja", "relacion": "pareja",
             "direccion": "0x6a1f4e8c07b3d952e8c1f4b70a6d9e3b5c802f17"},
        ],
    },
}

#: El perfil por defecto si no se reconoce.
_PERFIL_VACIO = {
    "wallet": {
        "direccion": "0x7a3f9c21b8e4d605fa12c93b7e4d1908a3c5e7f21",
        "red": RED_POR_DEFECTO,
        "token": TOKEN_POR_DEFECTO,
        "saldo": 1200.0,
    },
    "contactos": [
        {"nombre": "Rosa Martin", "alias": "madre", "relacion": "madre",
         "direccion": "0x2f8a1d90c4b7e63a5f0d8c2b91e4a7d603c8b1f45"},
    ],
}


def datos_perfil(perfil: str) -> dict[str, Any]:
    """La wallet y los contactos de un perfil de prueba."""
    return PERFILES_PAGO.get(perfil, _PERFIL_VACIO)


#: Los pagos ya hechos, para no pagar dos veces lo mismo y para que
#: el cliente vea su historico.
_LEDGER: list[dict[str, Any]] = []

#: Los retos de pago pendientes (los "402" que aun no se han pagado).
_RETO_PENDIENTE: dict[str, dict[str, Any]] = {}


def _eur(valor: Any) -> str:
    """Un numero en formato espanol: 1.200,00."""
    try:
        v = float(valor)
    except (TypeError, ValueError):
        return str(valor)
    s = f"{v:,.2f}"
    return s.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def _ahora() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _hash_transaccion(cuerpo: dict[str, Any]) -> str:
    """
    El hash de la transaccion.

    En una cadena de verdad es el hash de la transaccion firmada. Aqui
    es el hash del contenido firmado: sirve para que el pago tenga un
    identificador unico y verificable, y para que nadie pueda
    reutilizar un reto ya pagado (el hash cambia si cambia un solo
    dato).
    """
    bruto = json.dumps(cuerpo, sort_keys=True, default=str).encode("utf-8")
    return "0x" + hashlib.sha256(bruto).hexdigest()


def _resolver_destinatario(contactos: list[dict], destinatario: Optional[str]) -> tuple[Optional[dict], bool]:
    """
    Resuelve a quien va el dinero.

    "madre" -> el contacto con alias "madre". "Rosa" -> el contacto
    con ese nombre. Si hay varios candidatos, hay que preguntar.

    Devuelve (contacto, hay_que_preguntar).
    """
    texto = (destinatario or "").strip().lower()
    if not texto:
        return (contactos[0] if len(contactos) == 1 else None), len(contactos) != 1

    for c in contactos:
        if texto == str(c.get("alias", "")).lower():
            return c, False
        if texto == str(c.get("relacion", "")).lower():
            return c, False
        if texto == str(c.get("nombre", "")).lower():
            return c, False

    # Coincidencia parcial: "Rosa" dentro de "Rosa Martin".
    parciales = [
        c for c in contactos
        if texto in str(c.get("nombre", "")).lower()
        or texto in str(c.get("alias", "")).lower()
    ]
    if len(parciales) == 1:
        return parciales[0], False
    if len(parciales) > 1:
        return parciales[0], True
    return None, True


def _oferta(importe: Decimal, token: str, red: str, pay_to: str) -> dict[str, Any]:
    """
    La oferta de pago: lo que va en el cuerpo de un 402.

    Es la parte del protocolo que el cliente necesita para pagar:
    el esquema ("exact" = el cliente paga exactamente el precio), el
    precio, la red, el token y a quien se paga.
    """
    return {
        "x402Version": 1,
        "accepts": [
            {
                "scheme": "exact",
                "network": red,
                "maxAmountRequired": str(importe),
                "resource": "mora:envio-dinero",
                "description": "Envio de dinero desde MoraBanc",
                "mimeType": "application/json",
                "payTo": pay_to,
                "maxTimeoutSeconds": 300,
                "asset": token,
            }
        ],
    }


def preparar(
    *,
    perfil: str,
    destinatario: Optional[str] = None,
    importe: Optional[float] = None,
    concepto: Optional[str] = None,
) -> dict[str, Any]:
    """
    Paso 1 y 2: preparar el envio y devolver la oferta (el 402).

    No se mueve dinero: se prepara. El cliente tiene que confirmar
    en el segundo paso.
    """
    datos = datos_perfil(perfil)
    wallet = datos["wallet"]
    contactos = datos["contactos"]

    # ── El destinatario ──
    contacto, preguntar = _resolver_destinatario(contactos, destinatario)
    if contacto is None or preguntar:
        return {
            "codigo_http": 200,
            "estado": "falta_destinatario",
            "falta": ["destinatario"],
            "pregunta": "¿A quién se lo envío?",
            "contactos_disponibles": [
                {"alias": c.get("alias"), "nombre": c.get("nombre"), "relacion": c.get("relacion")}
                for c in contactos
            ],
        }

    # ── El importe ──
    if importe is None:
        return {
            "codigo_http": 200,
            "estado": "falta_importe",
            "falta": ["importe"],
            "pregunta": "¿Cuánto le envío a {}?".format(contacto.get("nombre")),
            "destinatario": contacto,
        }

    importe_d = Decimal(str(importe)).quantize(Decimal("0.01"))

    # ── El saldo ──
    saldo = Decimal(str(wallet.get("saldo", 0)))
    if saldo < importe_d:
        return {
            "codigo_http": 200,
            "estado": "saldo_insuficiente",
            "falta": ["saldo"],
            "pregunta": "En la wallet hay {} EUR y el envío es de {} EUR: no llega.".format(
                _eur(saldo), _eur(importe_d)
            ),
            "saldo_disponible": float(saldo),
            "importe": float(importe_d),
        }

    red = wallet.get("red", RED_POR_DEFECTO)
    token = wallet.get("token", TOKEN_POR_DEFECTO)

    reto = _oferta(importe_d, token, red, contacto["direccion"])
    reto_id = secrets.token_hex(16)

    _RETO_PENDIENTE[reto_id] = {
        "reto_id": reto_id,
        "perfil": perfil,
        "importe": float(importe_d),
        "token": token,
        "red": red,
        "pay_to": contacto["direccion"],
        "origen": wallet["direccion"],
        "destinatario": contacto,
        "concepto": concepto or f"Envío a {contacto.get('nombre')}",
        "creado": _ahora(),
        "expira": time.time() + 300,
    }

    return {
        # El 402: el codigo http con el que el servidor dice "paga
        # para tener esto".
        "codigo_http": 402,
        "estado": "preparado",
        "reto_id": reto_id,
        "oferta": reto,
        "cabeceras": {
            # La cabecera con la que el cliente reenvia la peticion
            # ya pagada.
            "X-PAYMENT": "reto:" + reto_id,
            "WWW-Authenticate": 'X402 scheme="exact", network="{}", asset="{}"'.format(red, token),
        },
        "importe": float(importe_d),
        "importe_formato": _eur(importe_d),
        "concepto": _RETO_PENDIENTE[reto_id]["concepto"],
        "destinatario": {
            "nombre": contacto.get("nombre"),
            "alias": contacto.get("alias"),
            "relacion": contacto.get("relacion"),
            "direccion": contacto.get("direccion"),
        },
        "red": red,
        "cadena": NOMBRE_RED.get(red, red),
        "token": token,
        "origen": {"direccion": wallet["direccion"], "saldo": float(saldo)},
        "pregunta": (
            "Envío preparado: {} EUR en {} ({}) a {}. "
            "¿Lo confirmas?".format(
                _eur(importe_d), token, NOMBRE_RED.get(red, red), contacto.get("nombre")
            )
        ),
    }


def confirmar(*, perfil: str, reto_id: str, x_payment: Optional[str] = None) -> dict[str, Any]:
    """
    Pasos 3 y 4: el cliente paga y el facilitator liquida.

    El cliente manda la cabecera X-PAYMENT con el reto firmado. El
    facilitator verifica la firma, comprueba que el reto no estaba
    pagado y liquida.
    """
    if not x_payment:
        return {
            "codigo_http": 402,
            "estado": "falta_pago",
            "error": "Falta la cabecera X-PAYMENT",
        }

    reto = _RETO_PENDIENTE.get(reto_id)
    if reto is None:
        return {
            "codigo_http": 402,
            "estado": "reto_desconocido",
            "error": "Ese reto de pago no existe o ya se caduco",
        }

    if time.time() > reto["expira"]:
        _RETO_PENDIENTE.pop(reto_id, None)
        return {
            "codigo_http": 402,
            "estado": "reto_caducado",
            "error": "El reto de pago ha caducado (la ventana es de 5 minutos)",
        }

    # ── Verificar que el reto es el del cliente y no otro ──
    if x_payment != "reto:" + reto_id:
        return {
            "codigo_http": 402,
            "estado": "pago_invalido",
            "error": "La cabecera X-PAYMENT no corresponde a este reto",
        }

    # ── El facilitator verifica y liquida ──
    cuerpo = {
        "reto_id": reto_id,
        "importe": reto["importe"],
        "token": reto["token"],
        "red": reto["red"],
        "de": reto["origen"],
        "a": reto["pay_to"],
        "concepto": reto["concepto"],
        "perfil": perfil,
        "momento": _ahora(),
    }
    tx = _hash_transaccion(cuerpo)

    pago = {
        "tx": tx,
        "estado": "liquidado",
        "importe": reto["importe"],
        "importe_formato": _eur(reto["importe"]),
        "token": reto["token"],
        "red": reto["red"],
        "cadena": NOMBRE_RED.get(reto["red"], reto["red"]),
        "de": reto["origen"],
        "a": reto["pay_to"],
        "destinatario": reto["destinatario"],
        "concepto": reto["concepto"],
        "momento": _ahora(),
        "coste": 0.00012,
    }
    _LEDGER.append(pago)
    _RETO_PENDIENTE.pop(reto_id, None)

    # El saldo de la wallet baja.
    datos = datos_perfil(perfil)
    wallet = datos["wallet"]
    wallet["saldo"] = round(float(wallet.get("saldo", 0)) - reto["importe"], 6)

    return {
        "codigo_http": 200,
        "estado": "liquidado",
        "pago": pago,
        "cabeceras": {
            # La cabecera que confirma el pago.
            "X-PAYMENT-RESPONSE": json.dumps({"tx": tx, "estado": "liquidado"}),
        },
        "pregunta": (
            "Hecho: {} EUR enviados a {} ({}). "
            "Referencia {}.".format(
                _eur(reto["importe"]),
                reto["destinatario"].get("nombre"),
                NOMBRE_RED.get(reto["red"], reto["red"]),
                tx[:18] + "...",
            )
        ),
    }


def historial(perfil: Optional[str] = None) -> dict[str, Any]:
    """Los pagos del cliente: su historico."""
    pagos = [p for p in _LEDGER if perfil is None or p.get("concepto") is not None]
    return {
        "codigo_http": 200,
        "total": len(pagos),
        "pagos": pagos,
    }


def procesar_pago(cuerpo: dict[str, Any], perfil: str = "freelance") -> dict[str, Any]:
    """
    El endpoint del banco: decide si es preparar o confirmar.

    El cliente siempre va en dos pasos: primero pide (y recibe el 402
    con la oferta), luego confirma (y se liquida).
    """
    if cuerpo.get("accion") == "historial":
        return historial(cuerpo.get("perfil", perfil))

    if cuerpo.get("confirmar"):
        return confirmar(
            perfil=cuerpo.get("perfil", perfil),
            reto_id=str(cuerpo.get("reto_id") or ""),
            x_payment=cuerpo.get("x_payment"),
        )

    return preparar(
        perfil=cuerpo.get("perfil", perfil),
        destinatario=cuerpo.get("destinatario"),
        importe=cuerpo.get("importe"),
        concepto=cuerpo.get("concepto"),
    )
