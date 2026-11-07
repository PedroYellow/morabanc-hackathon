"""
Lambda de entrada (API) — motor de decisiones financieras.
=======================================================
Este modulo es el handler que AWS Lambda ejecuta. El motor y el agente viajan
empaquetados en el mismo zip (ver terraform/main.tf, archive_file "motor").

Rutas:
  GET  /salud     -> health check
  POST /login     -> autentica contra Cognito y devuelve el token
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


def _login(event, context):
    """Autentica contra el user pool de Cognito y devuelve los tokens.

    Se usa ADMIN_USER_PASSWORD_AUTH porque el app client de Cognito es
    publico (sin client secret) y el token endpoint rechaza el grant
    "password" en ese caso. El resultado es el mismo: un id_token
    firmado por Cognito con los claims del usuario.

    El codigo de empresa (12TJ28) se busca en preferred_username. Si
    el usuario escribe el codigo, se traduce al email de ese usuario.
    """
    try:
        payload = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        return _resp(400, {"error": "JSON invalido"})

    usuario = str(payload.get("usuario") or "").strip()
    contrasena = str(payload.get("contrasena") or "")
    if not usuario or not contrasena:
        return _resp(400, {"error": "Faltan usuario o contrasena"})

    user_pool_id = os.environ.get("COGNITO_USER_POOL_ID", "")
    client_id = os.environ.get("COGNITO_CLIENT_ID", "")
    if not user_pool_id or not client_id:
        return _resp(503, {"error": "Cognito no configurado"})

    # Los codigos de empresa de prueba se traducen a su email: el pool
    # esta configurado con UsernameAttributes=['email'].
    codigos = {
        "12TJ28": "pedro.andre.miranda@morabanc-demo.ad",
        "12TJ29": "finanzas.andorradigital@morabanc-demo.ad",
        "12TJ30": "admin.barnesifils@morabanc-demo.ad",
        "12TJ31": "finanzas.ceramicacanillo@morabanc-demo.ad",
    }
    codigo = usuario.upper()
    email = codigos.get(codigo)
    if not email:
        email = usuario.lower() if "@" in usuario else None
    if not email:
        return _resp(401, {"error": "Usuari desconegut"})

    try:
        import boto3

        cognito = boto3.client("cognito-idp")
        auth = cognito.admin_initiate_auth(
            UserPoolId=user_pool_id,
            ClientId=client_id,
            AuthFlow="ADMIN_USER_PASSWORD_AUTH",
            AuthParameters={"USERNAME": email, "PASSWORD": contrasena},
        )
    except Exception as e:  # noqa: BLE001
        print("ERROR login:", str(e), file=sys.stderr)
        # NotAuthorizedException -> contrasena incorrecta
        msg = str(e)
        if "NotAuthorizedException" in msg or "incorrect password" in msg:
            return _resp(401, {"error": "Contrasenya incorrecta"})
        if "UserNotFoundException" in msg:
            return _resp(401, {"error": "Usuari desconegut"})
        return _resp(500, {"error": "No s'ha pogut autenticar"})

    resultado = auth.get("AuthenticationResult") or {}
    id_token = resultado.get("IdToken", "")
    refresh_token = resultado.get("RefreshToken", "")

    claims = {}
    try:
        import base64

        parte = id_token.split(".")[1]
        parte += "=" * (-len(parte) % 4)
        claims = json.loads(base64.urlsafe_b64decode(parte).decode("utf-8"))
    except Exception:  # noqa: BLE001
        pass

    return _resp(200, {
        "ok": True,
        "id_token": id_token,
        "refresh_token": refresh_token,
        "codigo": claims.get("preferred_username") or codigo,
        "nombre": claims.get("name") or "",
        "email": claims.get("email") or email,
    })


def lambda_handler(event, context):
    try:
        ruta = event.get("rawPath") or event.get("resource") or ""
        metodo = event.get("requestContext", {}).get("http", {}).get("method", "POST")

        if metodo == "OPTIONS":
            return _resp(204, {})

        if "salud" in ruta or "health" in ruta:
            return _salud(event, context)

        # El login va antes de la validacion de la API key: es el
        # punto de entrada al sistema y el edge ya anade la clave.
        if ruta.endswith("/login") or "/login" in ruta:
            return _login(event, context)

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
