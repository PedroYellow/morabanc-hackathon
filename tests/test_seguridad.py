#!/usr/bin/env python3
"""
Tests de seguridad del motor de MoraBanc.

QUE CUBRE
    Los hallazgos de la auditoria de seguridad (2026-11-07) sobre
    welcomeandorra.com, cada uno con su prueba de regresion:

      1. El traceback no se devuelve al cliente (fuga de internals).
      2. La comprobacion de la API key falla CERRADO (fail closed).
      3. Los numeros fuera de rango se rechazan con 400, no con 500.
      4. Las entradas tienen limite de tamano (amplificacion de coste).
      5. /preguntar exige un id_token de Cognito valido.
      6. El token se validan por issuer, audience, token_use y expiracion.
      7. El CORS por defecto NO es "*".
      8. El front no lleva la contrasena de demo en el bundle.
      9. El front manda el id_token a la API.
     10. El portal exige sesion (no cae a un usuario por defecto).
     11. El terraform declara la policy de cabeceras de seguridad.
     12. El terraform pasa el id_token por el edge a la API.

COMO SE EJECUTA
    python3 tests/test_seguridad.py
    (es un script standalone, igual que el resto de tests del repo)
"""

import base64
import importlib.util
import json
import os
import re
import sys
import time
from decimal import Decimal

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

FALLA = 0


def check(nombre, condicion, detalle=""):
    global FALLA
    if condicion:
        print(f"  PASS  {nombre}")
    else:
        FALLA += 1
        print(f"  FAIL  {nombre}" + (f" -> {detalle}" if detalle else ""))


# ---------------------------------------------------------------------------
# Cargar el handler con un entorno controlado
# ---------------------------------------------------------------------------
#
# API_KEY y las variables de Cognito se fijan ANTES de cargar el modulo,
# porque el handler las lee en el import (EXIGIR_TOKEN, REGION).
os.environ["API_KEY"] = "K" * 40
os.environ["AWS_REGION"] = "us-east-1"
os.environ["COGNITO_USER_POOL_ID"] = "us-east-1_TESTPOOL"
os.environ["COGNITO_CLIENT_ID"] = "testclientid"
os.environ.pop("CORS_ORIGIN", None)

_spec = importlib.util.spec_from_file_location(
    "mbhandler_seg", os.path.join(RAIZ, "lambda", "handler.py")
)
H = importlib.util.module_from_spec(_spec)
sys.modules["mbhandler_seg"] = H
_spec.loader.exec_module(H)


class _Ctx:
    aws_request_id = "req-test-123"


def _token(claims=None, firma="firma"):
    """Construye un token con los claims dados (para probar la validacion)."""
    base = {
        "iss": "us-east-1_TESTPOOL",
        "aud": "testclientid",
        "token_use": "id",
        "exp": time.time() + 3600,
        "preferred_username": "12TJ28",
    }
    if claims:
        base.update(claims)
    payload = base64.urlsafe_b64encode(json.dumps(base).encode()).decode().rstrip("=")
    return f"eyJhbGciOiJub25lIn0.{payload}.{firma}"


def _llamar(cuerpo, cabeceras=None):
    evento = {
        "rawPath": "/preguntar",
        "body": json.dumps(cuerpo) if cuerpo is not None else None,
        "headers": cabeceras or {},
        "requestContext": {"http": {"method": "POST"}},
    }
    return H.lambda_handler(evento, _Ctx())


def _status(resp):
    return resp["statusCode"]


def _body(resp):
    return json.loads(resp["body"])


KEY_BUENA = {"x-api-key": "K" * 40}

# Cabeceras con una sesion valida: para probar las capas de validacion
# (rangos y limites) hay que pasar la comprobacion de token, que va antes.
CON_SESION = {**KEY_BUENA, "authorization": "Bearer " + _token()}


# ---------------------------------------------------------------------------
print("=== 1. NO SE FUEGA EL TRACEBACK AL CLIENTE ===")
# ---------------------------------------------------------------------------
resp = _llamar({"pregunta": "hola", "saldo_actual": "abc"}, CON_SESION)
texto = resp["body"]
check("un saldo no numerico da 400, no 500", _status(resp) == 400, f"status={_status(resp)}")
check("la respuesta no lleva la clave 'trace'", "trace" not in texto)
check("la respuesta no lleva una ruta interna", "/var/task" not in texto)
check("la respuesta no lleva el nombre del fichero", "handler.py" not in texto)
check("la respuesta no filtra el tipo de excepcion", "InvalidOperation" not in texto)
check("la respuesta no filtra el mensaje interno de Decimal", "ConversionSyntax" not in texto)

# El error generico tampoco puede delatar los internals.
print("\n=== 2. LA API KEY FALLA CERRADO ===")
guardado = os.environ.pop("API_KEY")
resp = _llamar({"pregunta": "hola"}, {"authorization": "Bearer " + _token()})
check("sin API_KEY en el entorno responde 500", _status(resp) == 500, f"status={_status(resp)}")
check("sin API_KEY no devuelve 200 (no falla abierto)", _status(resp) != 200)
os.environ["API_KEY"] = guardado

resp = _llamar({"pregunta": "hola"}, {"x-api-key": "clave-incorrecta", "authorization": "Bearer " + _token()})
check("con API key incorrecta responde 401", _status(resp) == 401, f"status={_status(resp)}")

# ---------------------------------------------------------------------------
print("\n=== 3. LOS NUMEROS TIENEN RANGO ===")
# ---------------------------------------------------------------------------
for campo, valor in [
    ("saldo_actual", "abc"),
    ("saldo_actual", -1),
    ("saldo_actual", 10 ** 30),
    ("renta_neta_anual", "mil euros"),
    ("renta_neta_anual", 10 ** 30),
    ("margen_bruto", 99),
    ("margen_bruto", "x"),
]:
    resp = _llamar({"pregunta": "hola", campo: valor}, CON_SESION)
    check(
        f"{campo}={valor!r} se rechaza con 400",
        _status(resp) == 400,
        f"status={_status(resp)}",
    )

resp = _llamar({"pregunta": "hola", "fecha_consejo": "no-es-fecha"}, CON_SESION)
check("una fecha invalida da 400", _status(resp) == 400, f"status={_status(resp)}")

# ---------------------------------------------------------------------------
print("\n=== 4. LAS ENTRADAS TIENEN LIMITE DE TAMANO ===")
# ---------------------------------------------------------------------------
resp = _llamar({"pregunta": "x" * (H.MAX_PREGUNTA + 1)}, CON_SESION)
check("una pregunta demasiado larga da 413", _status(resp) == 413, f"status={_status(resp)}")

resp = _llamar({"pregunta": "x" * (H.MAX_PREGUNTA - 1)}, CON_SESION)
check("una pregunta dentro del limite NO da 413", _status(resp) != 413, f"status={_status(resp)}")

resp = _llamar({"pregunta": "hola", "extracto_csv": "a" * (H.MAX_EXTRACTO + 1)}, CON_SESION)
check("un extracto demasiado grande da 413", _status(resp) == 413, f"status={_status(resp)}")

resp = _llamar({"pregunta": "hola", "extracto_csv": "a" * 1000}, CON_SESION)
check("un extracto dentro del limite NO da 413", _status(resp) != 413, f"status={_status(resp)}")

# ---------------------------------------------------------------------------
print("\n=== 5. /preguntar EXIGE SESION DE COGNITO ===")
# ---------------------------------------------------------------------------
check("EXIGIR_TOKEN esta activo por defecto", H.EXIGIR_TOKEN is True)

resp = _llamar({"pregunta": "hola"}, KEY_BUENA)
check("sin token responde 401", _status(resp) == 401, f"status={_status(resp)}")
check("el mensaje de 401 no filtra internals", "trace" not in resp["body"])

resp = _llamar({"pregunta": "hola"}, {**KEY_BUENA, "authorization": "Bearer basura"})
check("con un token basura responde 401", _status(resp) == 401, f"status={_status(resp)}")

resp = _llamar({"pregunta": "hola"}, {**KEY_BUENA, "authorization": "Bearer " + _token()})
check("con un token valido NO da 401", _status(resp) != 401, f"status={_status(resp)}")

# ---------------------------------------------------------------------------
print("\n=== 6. EL TOKEN SE VALIDA EN SERIO ===")
# ---------------------------------------------------------------------------
casos = [
    ("token caducado", {"exp": time.time() - 10}),
    ("token de otro user pool", {"iss": "us-east-1_OTROPOOL"}),
    ("token de otra app client", {"aud": "otro_cliente"}),
    ("access_token en vez de id_token", {"token_use": "access"}),
    ("token sin exp", {"exp": None}),
    # El issuer real de Cognito trae la URL completa del servicio, y el
    # dominio del SERVICIO es "amazonaws.com" (no "amazoncognito.com",
    # que es el del dominio del user pool). Este caso real salio de un
    # token de produccion: sin esta cobertura, /preguntar daba 401 con
    # un token perfectamente valido.
    ("issuer con la URL real del servicio",
     {"iss": "https://cognito-idp.us-east-1.amazonaws.com/us-east-1_TESTPOOL"}),
]
for nombre, claims in casos:
    resp = _llamar({"pregunta": "hola"}, {**KEY_BUENA, "authorization": "Bearer " + _token(claims)})
    if nombre.startswith("issuer con la URL real"):
        check(f"{nombre} se ACEPTA", _status(resp) != 401, f"status={_status(resp)}")
    else:
        check(f"{nombre} se rechaza con 401", _status(resp) == 401, f"status={_status(resp)}")

# Un issuer con el pool correcto pero de otro host tiene que rechazarse.
resp = _llamar({"pregunta": "hola"}, {**KEY_BUENA, "authorization": "Bearer " + _token(
    {"iss": "https://cognito-idp.evil.example.com/us-east-1_TESTPOOL"})})
check("un issuer con otro host se rechaza con 401", _status(resp) == 401, f"status={_status(resp)}")

# ---------------------------------------------------------------------------
print("\n=== 5b. LIMITE DE PETICIONES POR USUARIO ===")
# ---------------------------------------------------------------------------
# El limite es por usuario (la sesion), no por IP: es lo que protege la
# cuota de Bedrock.
H._registro.clear()
H._registro_marks.clear()

check("el limite por minuto esta definido", H.LIMITE_POR_MINUTO > 0)
check("el limite por hora esta definido", H.LIMITE_POR_HORA > 0)

permitido = True
for _ in range(H.LIMITE_POR_MINUTO):
    if not H._comprobar_ritmo("usuario-test"):
        permitido = False
        break
check("se puede llegar al limite sin ser bloqueado", permitido)

check("al superar el limite se bloquea", H._comprobar_ritmo("usuario-test") is False)
check("otro usuario no se ve afectado", H._comprobar_ritmo("otro-usuario") is True)

# Y de verdad, por HTTP.
H._registro.clear()
H._registro_marks.clear()
for _ in range(H.LIMITE_POR_MINUTO):
    _llamar({"pregunta": "hola"}, CON_SESION)
resp = _llamar({"pregunta": "hola"}, CON_SESION)
check("tras el limite la API responde 429", _status(resp) == 429, f"status={_status(resp)}")
H._registro.clear()
H._registro_marks.clear()

# El usuario sale del token, no de la URL.
check("el usuario se saca del token", H._usuario_del_token(_token()) == "12TJ28")

# ---------------------------------------------------------------------------
print("\n=== 7. EL CORS POR DEFECTO NO ES WILDCARD ===")
# ---------------------------------------------------------------------------
origen = H._cors_headers()["Access-Control-Allow-Origin"]
check("el CORS por defecto no es '*'", origen != "*", f"origen={origen}")
check(
    "el CORS por defecto incluye welcomeandorra.com",
    "https://welcomeandorra.com" in origen,
    f"origen={origen}",
)

os.environ["CORS_ORIGIN"] = "https://ejemplo.test"
check(
    "CORS_ORIGIN explicito se respeta",
    H._cors_headers()["Access-Control-Allow-Origin"] == "https://ejemplo.test",
)
os.environ.pop("CORS_ORIGIN", None)

# ---------------------------------------------------------------------------
print("\n=== 8-10. EL FRONT NO DEJA HUELLAS DE DEMO ===")
# ---------------------------------------------------------------------------
login_js = open(os.path.join(RAIZ, "frontend", "assets", "mb-login.js"), encoding="utf-8").read()
portal_js = open(os.path.join(RAIZ, "frontend", "assets", "mb-portal.js"), encoding="utf-8").read()
app_js = open(os.path.join(RAIZ, "frontend", "assets", "app.js"), encoding="utf-8").read()

# La contrasena de demo no puede estar asignada a una variable del bundle.
asignacion = re.search(r'PASSWORD_VALIDA\s*=\s*"([^"]*)"', login_js)
check("PASSWORD_VALIDA no tiene ninguna contrasena", asignacion is not None and asignacion.group(1) == "",
      f"valor={asignacion.group(1) if asignacion else 'no encontrado'}")

# El portal no puede caer a un usuario por defecto sin sesion.
check("el portal no cae al usuario 12TJ28 por defecto",
      not re.search(r'\|\|\s*"12TJ28"\s*\)\.toUpperCase', portal_js))
check("el portal exige sesion o modo demo explicito",
      "modoDemoExplicito" in portal_js and "mb-login.html?next=" in portal_js)

# El front tiene que mandar el token a la API.
check("el front manda el id_token a la API", "Authorization" in app_js and "tokenDeSesion" in app_js)
check("el front tiene el helper tokenDeSesion", "function tokenDeSesion" in app_js)

# ---------------------------------------------------------------------------
print("\n=== 11-12. EL TERRAFORM DECLARA LAS CABECERAS Y EL PASO DEL TOKEN ===")
# ---------------------------------------------------------------------------
tf = open(os.path.join(RAIZ, "terraform", "main.tf"), encoding="utf-8").read()

check("existe la policy de cabeceras de seguridad",
      'aws_cloudfront_response_headers_policy" "seguridad"' in tf)
check("la policy define CSP", "content_security_policy" in tf)
check("la policy define HSTS", "strict_transport_security" in tf)
check("la policy define X-Frame-Options", "frame_options" in tf)
check("la policy define X-Content-Type-Options", "content_type_options" in tf)
check("la policy impide el clickjacking con frame-ancestors", "frame-ancestors 'none'" in tf)

# Todas las cache behaviors de la distribucion llevan la policy.
behaviors = re.findall(r"(?:default_cache_behavior|ordered_cache_behavior) \{(.*?)\n  \}", tf, re.S)
con_headers = [b for b in behaviors if "response_headers_policy_id" in b]
check(f"todas las cache behaviors llevan la policy ({len(con_headers)}/{len(behaviors)})",
      len(con_headers) == len(behaviors) and len(behaviors) > 0)

check("la Lambda de la API exige token", 'EXIGIR_TOKEN' in tf)
check("la Lambda de la API tiene el id del user pool", "COGNITO_USER_POOL_ID" in tf)
check("la Lambda de la API tiene el id del app client", "COGNITO_CLIENT_ID" in tf)
check("el CORS de la Lambda no es wildcard", 'CORS_ORIGIN = join(",", var.cors_allowed_origins)' in tf)

# El token tiene que poder llegar a la Lambda: la origin request policy
# tiene que reenviar la cabecera Authorization.
origen_politica = re.search(
    r'resource "aws_cloudfront_origin_request_policy" "api_headers" \{(.*?)\n\}', tf, re.S
)
check("existe la origin request policy de la API", origen_politica is not None)
if origen_politica:
    check("la origin request policy reenvia Authorization",
          "authorization" in origen_politica.group(1).lower())

# La ruta /login tiene que existir y ser alcanzable desde el front.
check("existe la ruta /login en el API Gateway", 'route_key = "POST /login"' in tf)
check("existe la ruta /api/login en el API Gateway", 'route_key = "POST /api/login"' in tf)
check("CloudFront enruta /api/login a la API", 'path_pattern           = "/api/login"' in tf)

# El throttling del API Gateway (por IP) y el limite por usuario (en la
# Lambda) son las dos capas que protegen la cuota de Bedrock.
check("el stage de la API tiene throttling", "default_route_settings" in tf)
check("el throttling define un limite de peticiones", "throttling_rate_limit" in tf)
check("el throttling define un burst", "throttling_burst_limit" in tf)

# El guardrail se crea en el terraform, pero si no se pasa en la llamada
# a converse NO hace nada: hay que conectarlo.
agente = open(os.path.join(RAIZ, "agent", "bedrock_agent.py"), encoding="utf-8").read()
check("el agente lee el id del guardrail", "BEDROCK_GUARDRAIL_ID" in agente)
check("el agente pasa el guardrail en la llamada a converse",
      "guardrailConfig" in agente and "guardrailIdentifier" in agente)
check("el terraform pasa el id del guardrail a la Lambda", "BEDROCK_GUARDRAIL_ID" in tf)
check("el guardrail bloqueado no es un 500",
      "GuardrailIntervened" in agente)

# ---------------------------------------------------------------------------
print("")
if FALLA:
    print(f"{FALLA} TESTS FALLAN")
    sys.exit(1)
print("TODOS LOS TESTS DE SEGURIDAD PASAN")
