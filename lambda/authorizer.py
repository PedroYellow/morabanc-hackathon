"""Authorizer de API Gateway: valida la clave del front.

POR QUE EXISTE
    /preguntar llama a Bedrock, que cuesta dinero y tiene quota. Si la API
    queda abierta, cualquiera que descubra la URL puede gastarnos la
    cuota del equipo (y ensuciar las metricas que vera el jurado).

QUE HACE
    Es un authorizer de tipo REQUEST. Compara la cabecera "x-api-key" con la
    clave guardada en la variable de entorno API_KEY. Si coincide, devuelve
    una policy de IAM que permite invocar la ruta; si no, devuelve un 401.

    La clave se compara en tiempo constante para no filtrar informacion por
    analisis temporal, aunque para un hackathon es mas IMPORTANT que un
    atacanteDeduzca la clave probando: la clave se genera con
    terraform "random_password" (alfanumerica, 32 caracteres) y solo vive en
    la variable de entorno de esta Lambda y en el front publicado.

    La clave NUNCA se escribe en el codigo ni se imprime en los logs.
"""

import hashlib
import hmac
import json
import os

API_KEY = os.environ.get("API_KEY", "")

# La region del API Gateway. En Lambda la pone la plataforma (AWS_REGION),
# pero en local puede venir en AWS_DEFAULT_REGION.
#
# El default es us-east-1, NO eu-west-1: es la region donde esta
# desplegado el proyecto (la cuenta del workshop tiene una policy
# "DenyAllOutsideAllowedRegions" que solo permite us-east-1).
#
# Con el default equivocado, el authorizer construia el ARN de la ruta
# con una region que no es la del API Gateway, la policy no casaba con
# la ruta y API Gateway respondia 403 Forbidden (con la clave correcta).
REGION = (
    os.environ.get("AWS_REGION")
    or os.environ.get("AWS_DEFAULT_REGION")
    or "us-east-1"
)
ACCOUNT = os.environ.get("MB_ACCOUNT_ID", "")

# El ARN de la ruta NO se guarda aqui a proposito: si el authorizer lo
# leyera de su entorno, Terraform crearia un ciclo (la ruta depende del
# authorizer y el authorizer de la ruta). API Gateway envia el ARN de la ruta
# en el evento, asi que se usa ese.


def _policy(principal_id, effect, reason, route_arn):
    """Construye la policy de IAM que espera API Gateway."""
    return {
        "principalId": principal_id,
        "policyDocument": {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Action": "execute-api:Invoke",
                    "Effect": effect,
                    "Resource": route_arn,
                }
            ],
        },
        "context": {"razon": reason},
    }


def _error(code, msg):
    return {
        "statusCode": code,
        "type": "UNAUTHORIZED" if code == 401 else "SERVER_ERROR",
        "message": msg,
    }


def handler(event, context):
    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
    recibida = headers.get("x-api-key", "")

    # Sin clave configurada no se acepta nada: es un fallo de despliegue, no
    # una invitation a dejar la API abierta.
    if not API_KEY:
        print("ERROR: API_KEY no esta definida en el entorno de la Lambda")
        return _error(500, "authorizer mal configurado")

    if not hmac.compare_digest(recibida.encode("utf-8"), API_KEY.encode("utf-8")):
        print("AUTH: clave incorrecta")
        return _error(401, "clave invalida")

    # OJO: en HTTP API con authorizer REQUEST, el "routeArn" del evento
    # NO viene (es una opcion de payload format 1.0). El arn de la ruta
    # hay que construirlo a mano con lo que si viene:
    # requestContext.http.method + requestContext.http.path.
    #
    # Si el arn sale vacio o incorrecto, la policy que devuelve el
    # authorizer no autoriza la invocacion y API Gateway responde 403
    # Forbidden (aunque la clave sea correcta).
    rc = event.get("requestContext", {}) or {}
    http = rc.get("http", {}) or {}
    metodo = http.get("method", "POST")
    camino = http.get("path", "") or event.get("rawPath", "") or ""
    api_id = rc.get("apiId", "") or os.environ.get("MB_API_ID", "")
    stage = rc.get("stage", "$default")

    # El arn que espera API Gateway para una ruta: <api-id>/<stage>/<metodo>/<ruta>
    # Con el stage "$default" NO va (las rutas del stage por defecto se
    # invocan como <api-id>/<metodo>/<ruta>).
    if stage and stage != "$default":
        route_arn = f"arn:aws:execute-api:{REGION}:{ACCOUNT}:{api_id}/{stage}/{metodo}{camino}"
    else:
        route_arn = f"arn:aws:execute-api:{REGION}:{ACCOUNT}:{api_id}/{metodo}{camino}"

    # OJO: si el ARN construido sale MAL FORMADO (sin api_id, sin cuenta
    # o con "None" dentro), NO sirve: la policy no autorizaria la ruta y
    # API Gateway responderia 403 Forbidden aunque la clave sea correcta.
    #
    # En ese caso se usa el "routeArn" del evento, que es el ARN real de
    # la ruta y el que API Gateway espera. Antes el fallback solo se
    # disparaba con el ARN VACIO, no con uno mal formado, asi que un
    # evento sin requestContext producia
    # "arn:aws:execute-api:us-east-1::/POST" y el 403.
    if not route_arn or "None" in route_arn or not api_id or not camino:
        route_arn = event.get("routeArn", "") or ""
    if not route_arn or "None" in route_arn:
        # Sin ARN no se puede autorizar la invocacion. Se devuelve la
        # policy con el recurso que API Gateway espera cuando el
        # authorizer no puede determinar la ruta: "arn:aws:execute-api:
        # <region>:*" no vale; lo correcto es un "*" de api, que es lo
        # que hace un authorizer REQUEST sin ruta conocida.
        route_arn = f"arn:aws:execute-api:{REGION}:{ACCOUNT}:*"

    print("AUTH", metodo, camino, "->", route_arn)

    return _policy("front-morabanc", "Allow", "clave correcta", route_arn)
