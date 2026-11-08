"""
Los tests del motor de pagos con x402.

Se ejecutan sin pytest (no esta instalado en el entorno):

    python3 tests/test_pagos_x402.py

Lo que se comprueba:
  1. El ciclo completo: 402 -> X-PAYMENT -> liquidado.
  2. Que no se pueda pagar dos veces lo mismo.
  3. Que sin confirmar no se mueva dinero (y que el saldo no baje).
  4. Que el agente resuelva "mi madre" sin preguntar.
  5. Que pida lo que falta (importe, destinatario).
  6. Que avise si no llega el saldo.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from decimal import Decimal

from engine import pagos_x402
from agent.bedrock_agent import _detectar_pago


FALLOS: list[str] = []


def comprobar(condicion: bool, mensaje: str) -> None:
    if condicion:
        print(f"  OK   {mensaje}")
    else:
        print(f"  FALLA {mensaje}")
        FALLOS.append(mensaje)


def test_ciclo_completo():
    """El ciclo x402: 402, luego el pago, luego liquidado."""
    print("\n1. EL CICLO COMPLETO")
    r = pagos_x402.preparar(perfil="freelance", destinatario="madre", importe=200)

    comprobar(r["estado"] == "preparado", "el envio queda preparado")
    comprobar(r["codigo_http"] == 402, "el servidor responde 402 Payment Required")

    oferta = r["oferta"]["accepts"][0]
    comprobar(oferta["scheme"] == "exact", "el esquema es 'exact'")
    comprobar(oferta["asset"] == "USDC", "el token es USDC")
    comprobar(oferta["network"] == "eip155:8453", "la red es Base (eip155:8453)")
    comprobar(oferta["payTo"].startswith("0x"), "la oferta dice a quien se paga")
    comprobar(
        r["cabeceras"]["X-PAYMENT"] == "reto:" + r["reto_id"],
        "la cabecera X-PAYMENT lleva el reto",
    )

    # El cliente paga y reenvia.
    r2 = pagos_x402.confirmar(
        perfil="freelance",
        reto_id=r["reto_id"],
        x_payment=r["cabeceras"]["X-PAYMENT"],
    )
    comprobar(r2["estado"] == "liquidado", "el pago se liquida")
    comprobar(r2["codigo_http"] == 200, "el servidor responde 200")
    comprobar(r2["pago"]["tx"].startswith("0x"), "la transaccion tiene hash")
    comprobar(
        "X-PAYMENT-RESPONSE" in r2["cabeceras"],
        "la respuesta lleva la cabecera X-PAYMENT-RESPONSE",
    )
    comprobar(
        r2["pago"]["destinatario"]["nombre"] == "Rosa Martin",
        "el dinero va a Rosa Martin (la madre)",
    )
    comprobar(r2["pago"]["importe_formato"] == "200,00", "el importe, en formato español")


def test_no_se_paga_dos_veces():
    """El doble gasto: un reto no se puede cobrar dos veces."""
    print("\n2. NO SE PAGA DOS VECES")
    r = pagos_x402.preparar(perfil="freelance", destinatario="madre", importe=50)
    pagos_x402.confirmar(
        perfil="freelance", reto_id=r["reto_id"], x_payment=r["cabeceras"]["X-PAYMENT"]
    )
    r2 = pagos_x402.confirmar(
        perfil="freelance", reto_id=r["reto_id"], x_payment=r["cabeceras"]["X-PAYMENT"]
    )
    comprobar(r2["estado"] != "liquidado", "el segundo intento no liquida")
    comprobar(r2["codigo_http"] == 402, "el segundo intento responde 402")


def test_sin_confirmar_no_se_mueve_dinero():
    """Preparar no es enviar: el saldo no baja hasta confirmar."""
    print("\n3. SIN CONFIRMAR NO SE MUEVE DINERO")
    saldo_antes = pagos_x402.datos_perfil("empleado")["wallet"]["saldo"]
    r = pagos_x402.preparar(perfil="empleado", destinatario="madre", importe=100)
    saldo_despues = pagos_x402.datos_perfil("empleado")["wallet"]["saldo"]
    comprobar(saldo_antes == saldo_despues, "el saldo no baja al preparar")
    comprobar(r["estado"] == "preparado", "el envio queda pendiente de confirmar")

    pagos_x402.confirmar(
        perfil="empleado", reto_id=r["reto_id"], x_payment=r["cabeceras"]["X-PAYMENT"]
    )
    saldo_final = pagos_x402.datos_perfil("empleado")["wallet"]["saldo"]
    comprobar(saldo_final == round(saldo_antes - 100, 6), "el saldo baja al confirmar")


def test_la_herramienta_del_agente():
    """La herramienta del agente: resuelve "mi madre" y pide lo que falta."""
    print("\n4. LA HERRAMIENTA DEL AGENTE")
    from agent.bedrock_agent import ejecutar_tool, ContextoEmpresa

    ctx = ContextoEmpresa(
        saldo_actual=Decimal("8500"),
        renta_neta_anual=Decimal("30000"),
        margen_bruto=Decimal("0.70"),
        actividad="Freelance",
        empresa_id="freelance",
    )

    # Detecta el destinatario y el importe en la frase.
    d, i = _detectar_pago("enviale 200 euros a mi madre")
    comprobar(d == "madre", "detecta 'mi madre' como destinatario")
    comprobar(i == 200.0, "detecta el importe (200)")

    d2, i2 = _detectar_pago("manda 150 a mi madre Rosa")
    comprobar(d2 == "madre", "detecta 'madre' en una frase con nombre")
    comprobar(i2 == 150.0, "detecta el importe sin 'euros'")

    # Sin importe: el motor pregunta.
    r = ejecutar_tool("preparar_pago", ctx, {"destinatario": "madre"})
    comprobar(
        "falta_importe" in str(r["resultado"].get("estado", "")) or r["resultado"].get("falta"),
        "sin importe, se pide el importe",
    )

    # Con importe: se prepara y trae el reto.
    r2 = ejecutar_tool("preparar_pago", ctx, {"destinatario": "madre", "importe": 200})
    comprobar(r2["resultado"].get("estado") == "preparado", "con importe, se prepara")
    comprobar(bool(r2["resultado"].get("reto_id")), "el resultado trae el reto")
    comprobar(
        bool(r2["resultado"].get("cabeceras", {}).get("X-PAYMENT")),
        "el resultado trae la cabecera X-PAYMENT",
    )


def test_lo_que_falta_y_el_saldo():
    """Cuando falta algo, se pregunta; si no llega, se avisa."""
    print("\n5. LO QUE FALTA Y EL SALDO")
    r = pagos_x402.preparar(perfil="freelance", destinatario="madre")
    comprobar(r["estado"] == "falta_importe", "sin importe, falta el importe")
    comprobar("Cuánto" in r["pregunta"], "la pregunta pide el importe")

    r2 = pagos_x402.preparar(perfil="freelance", importe=50)
    comprobar(r2["estado"] == "falta_destinatario", "sin destinatario, falta el destinatario")
    comprobar(len(r2["contactos_disponibles"]) > 0, "el banco ofrece sus contactos")

    r3 = pagos_x402.preparar(perfil="freelance", destinatario="madre", importe=999999)
    comprobar(r3["estado"] == "saldo_insuficiente", "si no llega el saldo, se avisa")
    comprobar("no llega" in r3["pregunta"], "el aviso dice que no llega")


def test_historial():
    """Los pagos quedan registrados."""
    print("\n6. EL HISTORIAL")
    h = pagos_x402.historial()
    comprobar(h["total"] > 0, "los pagos quedan registrados")
    comprobar(
        all("tx" in p for p in h["pagos"]),
        "cada pago tiene su hash de transaccion",
    )


if __name__ == "__main__":
    test_ciclo_completo()
    test_no_se_paga_dos_veces()
    test_sin_confirmar_no_se_mueve_dinero()
    test_la_herramienta_del_agente()
    test_lo_que_falta_y_el_saldo()
    test_historial()

    print("\n" + "=" * 56)
    if FALLOS:
        print(f"{len(FALLOS)} FALLO(S):")
        for f in FALLOS:
            print("  -", f)
        sys.exit(1)
    print("TODO OK")
