"""
Lambda de entrada (API) — motor de decisiones financieras.
=======================================================
Este modulo es el handler que AWS Lambda ejecuta. El motor y el agente viajan
empaquetados en el mismo zip (ver terraform/main.tf, archive_file "motor").

Rutas:
  GET  /salud     -> health check
  POST /preguntar  -> pregunta al agente

Formato de entrada de /preguntar:
  {
    "pregunta": "¿Puedo contratar a alguien a 2.400 brutos?",
    "empresa_id": "emp_123",
    "extracto_csv": "Fecha;Concepto;Importe\\n...",   # opcional
    "saldo_actual": 8500,        # opcional
    "renta_neta_anual": 30000,   # opcional
    "margen_bruto": 0.70,        # opcional
    "actividad": "Freelance de servicios"
  }
"""

import hmac
import json
import os
import sys
import traceback
from datetime import date
from decimal import Decimal

# El zip incluye engine/, agent/ y lambda/ en la raiz. Lambda ejecuta el
# handler con /var/task como cwd, pero anadimos explicitamente las tres
# rutas para que funcione tanto en AWS como en local.
_RAIZ = os.path.dirname(os.path.abspath(__file__))
for _ruta in (_RAIZ, os.path.dirname(_RAIZ)):
    if _ruta not in sys.path:
        sys.path.insert(0, _ruta)

from engine.tesoreria import parse_extracto_csv  # noqa: E402
from agent.bedrock_agent import AgenteFinanciero, ContextoEmpresa  # noqa: E402


def _cors_headers():
    return {
        "Access-Control-Allow-Origin": os.environ.get("CORS_ORIGIN", "*"),
        "Access-Control-Allow-Headers": "Content-Type,Authorization",
        "Access-Control-Allow-Methods": "OPTIONS,GET,POST",
    }


def _resp(status: int, body: dict):
    return {
        "statusCode": status,
        "headers": _cors_headers(),
        "body": json.dumps(body, ensure_ascii=False, default=str),
    }


def _salud(event, context):
    return _resp(200, {
        "ok": True,
        "servicio": "morabanc-decision-engine",
        "entorno": os.environ.get("ENVIRONMENT", "dev"),
        "modelo": os.environ.get("BEDROCK_MODEL_ID", ""),
        "kb": bool(os.environ.get("BEDROCK_KB_ID")),
    })


def lambda_handler(event, context):
    try:
        ruta = event.get("rawPath") or event.get("resource") or ""
        metodo = event.get("requestContext", {}).get("http", {}).get("method", "POST")

        if metodo == "OPTIONS":
            return _resp(204, {})

        if "salud" in ruta or "health" in ruta:
            return _salud(event, context)

        # Defensa en profundidad: el authorizer de API Gateway ya valida la
        # clave, pero si alguien invoca la Lambda directamente (o se cambia
        # el authorize a NONE por error) esta comprobacion lo para.
        api_key = os.environ.get("API_KEY", "")
        if api_key:
            cabeceras = {
                k.lower(): v for k, v in (event.get("headers") or {}).items()
            }
            if not hmac.compare_digest(
                cabeceras.get("x-api-key", "").encode("utf-8"),
                api_key.encode("utf-8"),
            ):
                return _resp(401, {"error": "Clave de API invalida"})

        if not event.get("body"):
            return _resp(400, {"error": "Cuerpo vacio"})

        try:
            payload = json.loads(event["body"])
        except json.JSONDecodeError:
            return _resp(400, {"error": "JSON invalido"})

        pregunta = (payload.get("pregunta") or "").strip()
        if not pregunta:
            return _resp(400, {"error": "Falta el campo 'pregunta'"})

        # --- Contexto de la empresa ---------------------------------------
        movimientos = []
        extracto = payload.get("extracto_csv")
        if extracto:
            movimientos = parse_extracto_csv(extracto)

        ctx = ContextoEmpresa(
            movimientos=movimientos,
            saldo_actual=Decimal(str(payload.get("saldo_actual", 0))),
            renta_neta_anual=(
                Decimal(str(payload["renta_neta_anual"]))
                if payload.get("renta_neta_anual") is not None else None
            ),
            margen_bruto=(
                Decimal(str(payload["margen_bruto"]))
                if payload.get("margen_bruto") is not None else None
            ),
            actividad=payload.get("actividad", ""),
            fecha_consejo=(
                date.fromisoformat(payload["fecha_consejo"])
                if payload.get("fecha_consejo") else None
            ),
        )

        # El flag BEDROCK_MOCK=1 permite ensayar la demo sin credenciales
        # AWS. Los numeros son los mismos: el mock solo cambia quien redacta.
        agente = AgenteFinanciero(ctx)
        resultado = agente.preguntar(pregunta)

        return _resp(200, {
            "pregunta": pregunta,
            "respuesta": resultado["respuesta"],
            "herramientas": resultado["herramientas"],
            "empresa_id": payload.get("empresa_id"),
        })
    except Exception as e:  # noqa: BLE001
        # En un hackathon, un error silencioso es un pitch muerto: devolvemos
        # el traceback para poder depurar en caliente.
        print("ERROR:", str(e), file=sys.stderr)
        traceback.print_exc()
        return _resp(500, {
            "error": str(e),
            "herramientas": [],
            "respuesta": "",
            "trace": traceback.format_exc()[-2000:],
        })
