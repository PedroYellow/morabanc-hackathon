#!/usr/bin/env python3
"""Tests del authorizer de la API.

La API /preguntar llama a Bedrock: tiene coste y quota. Estos tests
comprueban que la proteccion por clave funciona de verdad:

  - sin clave configurada, NO se acepta ninguna peticion (fallo de
    despliegue, no una invitacion a dejar la API abierta)
  - con la clave incorrecta, se rechaza con 401
  - con la clave correcta, se permite con una policy de IAM valida
  - la clave no aparece en los logs ni en el codigo
"""

import importlib.util
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FALLA = 0


def check(desc, cond, extra=""):
    global FALLA
    if cond:
        print(f"  PASS  {desc}" + (f" -> {extra}" if extra else ""))
    else:
        FALLA += 1
        print(f"  FAIL  {desc}" + (f" -> {extra}" if extra else ""))


def cargar(clave):
    """Carga el authorizer con una clave concreta en el entorno."""
    if "API_KEY" in os.environ:
        del os.environ["API_KEY"]
    if clave is not None:
        os.environ["API_KEY"] = clave
    spec = importlib.util.spec_from_file_location(
        "authorizer_test", os.path.join(RAIZ, "lambda", "authorizer.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


print("=== AUTHORIZER: proteccion por clave ===")

# --- Sin clave configurada ------------------------------------------------
mod = cargar(None)
r = mod.handler({"headers": {"x-api-key": "cualquiera"}}, None)
check("sin API_KEY configurada se rechaza", r.get("statusCode") == 500, r.get("statusCode"))
check("el rechazo no revela la clave",
      "cualquiera" not in str(r), "la clave no debe aparecer en la respuesta")

# --- Clave incorrecta -----------------------------------------------------
mod = cargar("clave-buena-de-32-caracteres")
r = mod.handler({"headers": {"x-api-key": "clave-mala"}}, None)
check("clave incorrecta -> 401", r.get("statusCode") == 401, r.get("statusCode"))
check("clave incorrecta -> type UNAUTHORIZED", r.get("type") == "UNAUTHORIZED")

# --- Sin cabecera ---------------------------------------------------------
r = mod.handler({"headers": {}}, None)
check("sin cabecera x-api-key -> 401", r.get("statusCode") == 401, r.get("statusCode"))

# --- Headers en mayusculas (API Gateway puede mandarlos asi) --------------
r = mod.handler({"headers": {"X-API-Key": "clave-buena-de-32-caracteres"}}, None)
check("la cabecera se lee sin distinguir mayusculas",
      r.get("principalId") == "front-morabanc", r.get("principalId"))

# --- Clave correcta -------------------------------------------------------
# El ARN de la ruta lo manda API Gateway en el evento (no en el entorno: si
# el authorizer lo leyera de ROUTE_ARN, Terraform crearia un ciclo).
#
# OJO: la region la toma del ENTORNO (AWS_REGION / AWS_DEFAULT_REGION), y
# el proyecto esta en us-east-1. Antes el test traia "eu-west-1" fijo, que
# ya no correspondia a nada: el ARN construido salia con la region
# equivocada y el test fallaba por un motivo que no era un fallo del
# authorizer.
REGION = os.environ.get("AWS_REGION", os.environ.get("AWS_DEFAULT_REGION", "us-east-1"))
ARN_RUTA = f"arn:aws:execute-api:{REGION}:123456789012:abc/api/POST/preguntar"
r = mod.handler(
    {"headers": {"x-api-key": "clave-buena-de-32-caracteres"}, "routeArn": ARN_RUTA},
    None,
)
check("clave correcta -> policy Allow",
      r.get("policyDocument", {}).get("Statement", [{}])[0].get("Effect") == "Allow")
check("clave correcta -> principalId", r.get("principalId") == "front-morabanc")
stmt = r.get("policyDocument", {}).get("Statement", [{}])[0]
check("la policy permite solo execute-api:Invoke",
      stmt.get("Action") == "execute-api:Invoke", stmt.get("Action"))
check("la policy aplica a la ruta de /preguntar",
      "preguntar" in stmt.get("Resource", ""), stmt.get("Resource"))

# Sin routeArn en el evento: la policy debe salir con el recurso vacio, pero
# sin romperse (API Gateway siempre lo manda, pero no debe petar).
r = mod.handler({"headers": {"x-api-key": "clave-buena-de-32-caracteres"}}, None)
check("sin routeArn en el evento no rompe",
      r.get("policyDocument", {}).get("Statement", [{}])[0].get("Effect") == "Allow")
check("el authorizer no lee ROUTE_ARN del entorno (evita el ciclo de TF)",
      "ROUTE_ARN" not in open(
          os.path.join(RAIZ, "lambda", "authorizer.py"), encoding="utf-8"
      ).read())

# --- La clave no se filtra en el contexto ---------------------------------
r = mod.handler({"headers": {"x-api-key": "clave-buena-de-32-caracteres"}}, None)
check("la clave no aparece en el contexto devuelto",
      "clave-buena-de-32-caracteres" not in str(r))

# --- Comparacion en tiempo constante --------------------------------------
import inspect
src = open(os.path.join(RAIZ, "lambda", "authorizer.py"), encoding="utf-8").read()
check("la clave se compara con hmac.compare_digest",
      "compare_digest" in src)
check("la clave se lee del entorno, no del codigo",
      'os.environ.get("API_KEY"' in src)

# --- El handler de la API tambien valida (defensa en profundidad) ---------
h = open(os.path.join(RAIZ, "lambda", "handler.py"), encoding="utf-8").read()
check("el handler de la API tambien comprueba la clave",
      "x-api-key" in h and "compare_digest" in h)

# --- El front envia la cabecera -------------------------------------------
f = open(os.path.join(RAIZ, "frontend", "assets", "app.js"), encoding="utf-8").read()
check("el front envia la cabecera x-api-key", '"x-api-key"' in f)
check("el front lee la clave de la config", "__API_KEY__" in f)

# --- Terraform: el authorizer esta cableado ------------------------------
tf = open(os.path.join(RAIZ, "terraform", "main.tf"), encoding="utf-8").read()
check("existe la Lambda del authorizer",
      'aws_lambda_function" "authorizer"' in tf)
check("existe el authorizer de API Gateway",
      'aws_apigatewayv2_authorizer" "key"' in tf)
check("la ruta /preguntar usa autorizacion CUSTOM",
      'authorization_type = "CUSTOM"' in tf)
check("el authorizer valida la cabecera x-api-key",
      '$request.header.x-api-key' in tf)
check("la API tiene la clave en su entorno",
      "API_KEY" in tf)
check("la clave se genera con random_password",
      'random_password" "api_key"' in tf)
# La key vive dentro del output "frontend_url_config" (que es sensitive por
# eso). Terraform no permite que un output normal referencie un valor
# sensitive: por eso el config entero lleva sensitive = true.
check("el output con la key es sensitive",
      'output "frontend_url_config"' in tf and "sensitive = true" in tf)
check("la key se inyecta en el output del front",
      "api_key = random_password.api_key.result" in tf)
check("la Lambda del authorizer tiene permiso de invocacion",
      'aws_lambda_permission" "authorizer_api_gateway"' in tf)

print("")
if FALLA:
    print(f"{FALLA} TESTS FALLAN")
    sys.exit(1)
print("TODOS LOS TESTS DEL AUTHORIZER PASAN")
