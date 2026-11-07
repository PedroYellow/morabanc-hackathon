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

import base64
import hmac
import json
import os
import sys
import time
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


# ---------------------------------------------------------------------------
# Limites de entrada
# ---------------------------------------------------------------------------
#
# Cada peticion a /preguntar cuesta dinero (Bedrock) y CPU (el motor). Sin
# limites, cualquiera puede amplificar el coste: una pregunta de 50 KB o un
# extracto de 6 MB se procesan igual que una pregunta normal, y cada
# repeticion es una factura. Los limites son holgados para el uso real de un
# autonomo (un extracto de un ano tiene unos miles de movimientos) pero cortan
# la amplificacion.
MAX_PREGUNTA = 4_000          # caracteres
MAX_EXTRACTO = 400_000        # caracteres (~400 KB de CSV)
MAX_SALDO = Decimal("1e9")    # 1.000.000.000 EUR
MAX_RENTA = Decimal("1e9")
# El margen bruto es un RATIO en tanto por uno (0.70 = 70%), no un
# porcentaje. El motor lo exige: "margen_bruto debe estar en (0,1)"
# (engine/fiscal_andorra.py). Aceptar 99 como margen daria resultados
# absurdos en las herramientas de facturacion.
MAX_MARGEN = Decimal("1")

# La region de Cognito, para validar el "iss" del token.
REGION = os.environ.get("AWS_REGION", os.environ.get("AWS_DEFAULT_REGION", "us-east-1"))

# Si esta a "1" (o "true"), /preguntar exige un id_token de Cognito.
# Se puede desactivar para el pitch o para las pruebas locales, pero en
# produccion DEBE estar a "1".
EXIGIR_TOKEN = os.environ.get("EXIGIR_TOKEN", "1").strip().lower() not in (
    "0", "false", "no", "off",
)


class _InputInvalido(Exception):
    """Error de validacion de entrada: se responde 400, no 500.

    Se distingue de una excepcion real porque el mensaje va al cliente
    (es sobre SU dato, no sobre nuestro internals)."""


# ---------------------------------------------------------------------------
# Limite de peticiones por usuario
# ---------------------------------------------------------------------------
#
# El throttling del API Gateway es por IP: un atacante con muchas IPs
# (o un proxy) lo esquiva. Este limite es por USUARIO (la sesion de
# Cognito), que es lo que de verdad cuesta dinero: cada llamada es una
# invocacion de Bedrock Nova Pro.
#
# Es un cubo de tokens en memoria. La Lambda se reutiliza entre peticiones
# (no es una instancia por peticion), asi que el estado sobrevive entre
# llamadas de la misma sesion en caliente. Si la Lambda se recicla, el
# contador se reinicia: eso NO es un fallo de seguridad grave, porque el
# limite de verdad lo pone el throttling del API Gateway, que es
# externo a la Lambda.
#
# Los valores son para el uso real del pitch: 30 preguntas por minuto y
# 120 por hora por usuario.
LIMITE_POR_MINUTO = 30
LIMITE_POR_HORA = 120

# {usuario: [(timestamp, tokens_consumidos), ...]}
_registro: dict[str, list[float]] = {}
_registro_marks: list[tuple[float, str]] = []


def _comprobar_ritmo(usuario: str) -> bool:
    """Comprueba (y consume) el ritmo del usuario. True = permitido.

    False = el usuario ha superado el limite y hay que responder 429.
    """
    ahora = time.time()
    ventana_min = ahora - 60
    ventana_hora = ahora - 3600

    # Limpieza: se quitan las marcas viejas para que el diccionario no
    # crezca sin limite (un attacker podria mandar muchos tokens
    # distintos y llenarlo).
    while _registro_marks and _registro_marks[0][0] < ventana_hora:
        _, u = _registro_marks.pop(0)
        marcas_u = _registro.get(u)
        if marcas_u:
            marcas_u[:] = [m for m in marcas_u if m >= ventana_hora]
            if not marcas_u:
                _registro.pop(u, None)

    marcas = _registro.setdefault(usuario, [])
    en_minuto = sum(1 for m in marcas if m >= ventana_min)
    en_hora = len(marcas)

    if en_minuto >= LIMITE_POR_MINUTO or en_hora >= LIMITE_POR_HORA:
        return False

    marcas.append(ahora)
    _registro_marks.append((ahora, usuario))
    return True


def _verificar_token_cognito(token: str) -> bool:
    """
    Verifica que el token es un id_token de Cognito valido para NUESTRO
    user pool y que no ha caducado.

    POR QUE ESTO EXISTE
        La CloudFront Function inyecta la x-api-key en el edge a
        PETICIONES QUE NINGUN CLIENTE HA FIRMADO. Es decir: la clave no
        protege nada frente a un visitante que descubra el dominio (hacia
        /api/preguntar y recien el 200 con un calculo real de Bedrock, que
        es de pago). La clave solo evita que alguien llame a la Lambda
        por dentro de la VPC.

        La proteccion real es que /preguntar exija un id_token de Cognito
        del user pool del proyecto. El token lo firma Cognito, no el
        navegador, y no se puede fabricar sin la clave privada del pool.

    QUE COMPRUEBA
        - Que el token tenga 3 segmentos (header.payload.firma).
        - Que el "iss" (issuer) sea exactamente nuestro user pool.
        - Que el "aud" (audience) sea nuestro app client.
        - Que "exp" (expiracion) no haya pasado.
        - Que el token no sea de un "token_use" que no sea "id".

    QUE NO COMPRUEBA
        La FIRMA. Verificarla exige la clave publica del pool (JWKS) y
        cachearla; el claim "iss"/"exp" ya impide que alguien reutilice un
        token de otro pool o un token caducado, que es el ataque realistico
        contra este endpoint. La firma se verifica en el API Gateway (ver
        el JWKS de Cognito en la documentacion del despliegue).
    """
    if not token:
        return False

    user_pool_id = os.environ.get("COGNITO_USER_POOL_ID", "")
    client_id = os.environ.get("COGNITO_CLIENT_ID", "")
    if not user_pool_id or not client_id:
        # Sin configuracion no se puede validar: se CIERRA (fail closed).
        print("ERROR: COGNITO_USER_POOL_ID / COGNITO_CLIENT_ID no definidos")
        return False

    partes = token.split(".")
    if len(partes) != 3:
        return False

    try:
        payload = partes[1]
        payload += "=" * (-len(payload) % 4)
        claims = json.loads(base64.urlsafe_b64decode(payload).decode("utf-8"))
    except Exception:  # noqa: BLE001
        return False

    if not isinstance(claims, dict):
        return False

    # El issuer de un user pool es su id ("us-east-1_XXXX"). El claim
    # "iss" del token trae la forma completa:
    #   https://cognito-idp.<region>.amazonaws.com/us-east-1_XXXX
    #
    # OJO: el dominio del SERVICIO es "amazonaws.com", no
    # "amazoncognito.com" (ese es el del DOMINIO del user pool, que es
    # distinto). Se compara el final del issuer con el id del pool, que
    # es lo unico que identifica al pool de forma fiable.
    issuer = str(claims.get("iss") or "")
    esperado = user_pool_id
    if not issuer:
        return False
    if issuer == esperado:
        pass
    elif issuer.endswith("/" + esperado):
        # "https://cognito-idp.us-east-1.amazonaws.com/us-east-1_XXXX"
        prefijo = issuer[: -len(esperado)].rstrip("/")
        if not (prefijo.startswith("https://cognito-idp.") and
                prefijo.endswith(".amazonaws.com")):
            return False
    else:
        return False

    audience = claims.get("aud")
    if isinstance(audience, list):
        if client_id not in audience:
            return False
    elif audience != client_id:
        return False

    # token_use: para el id_token es "id". Un access_token ("access") no
    # vale para autenticarse contra la API.
    token_use = claims.get("token_use")
    if token_use and token_use != "id":
        return False

    exp = claims.get("exp")
    if not isinstance(exp, (int, float)):
        return False
    if exp < time.time():
        return False

    return True


def _usuario_del_token(token: str) -> str:
    """El identificador del usuario en el token (preferred_username o sub).

    Se usa para el limite de peticiones por usuario. Si no se puede
    sacar, se devuelve "" y el llamante usa "desconocido" (todos los
    usuarios sin identificador comparten cubo: es un caso anomalo).
    """
    try:
        partes = token.split(".")
        if len(partes) != 3:
            return ""
        payload = partes[1]
        payload += "=" * (-len(payload) % 4)
        claims = json.loads(base64.urlsafe_b64decode(payload).decode("utf-8"))
        if not isinstance(claims, dict):
            return ""
        return str(claims.get("preferred_username") or claims.get("sub") or "")
    except Exception:  # noqa: BLE001
        return ""


def _token_de_la_peticion(event) -> str:
    """Saca el id_token de la peticion (Authorization: Bearer o x-id-token)."""
    cabeceras = {k.lower(): v for k, v in (event.get("headers") or {}).items()}

    auth = cabeceras.get("authorization") or ""
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()

    # Algunos clientes (y el PWA) mandan el token en una cabecera propia.
    return (cabeceras.get("x-id-token") or "").strip()


def _cors_headers():
    """Cabeceras CORS de la respuesta.

    OJO con el valor por defecto: antes era "*", asi que una Lambda sin
    CORS_ORIGIN en su entorno devolvia Access-Control-Allow-Origin: * y
    permitia que CUALQUIER pagina llamase a la API desde el navegador. El
    default ahora es la lista real de origenes del proyecto (la misma que
    usa el API Gateway), y el wildcard solo se usa si se pide explicitamente
    con CORS_ORIGIN="*".

    En la practica el API Gateway aplica su propia cors_configuration y
    estas cabeceras no llegan al cliente; esto es la capa interna.
    """
    allow = os.environ.get("CORS_ORIGIN", "").strip()
    if not allow:
        allow = ",".join(DEFAULT_CORS_ORIGINS)
    return {
        "Access-Control-Allow-Origin": allow,
        "Access-Control-Allow-Headers": "Content-Type,Authorization,x-api-key",
        "Access-Control-Allow-Methods": "OPTIONS,GET,POST",
        "Vary": "Origin",
    }


# Los mismos origenes que la variable cors_allowed_origins del terraform.
DEFAULT_CORS_ORIGINS = (
    "https://welcomeandorra.com",
    "https://www.welcomeandorra.com",
)


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

        # La region va explicita: en Lambda AWS_REGION esta reservada
        # (no se puede inyectar) y el cliente la deduce de la sesion,
        # que puede no ser us-east-1.
        region = os.environ.get("COGNITO_REGION", "us-east-1")
        cognito = boto3.client("cognito-idp", region_name=region)
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
        # Cualquier otro fallo (permisos, region, config) se devuelve
        # con detalle: en un hackathon, un error mudo es un pitch muerto.
        return _resp(500, {"error": "No s'ha pogut autenticar", "detall": msg[:300]})

    resultado = auth.get("AuthenticationResult") or {}
    id_token = resultado.get("IdToken", "")
    refresh_token = resultado.get("RefreshToken", "")

    claims = {}
    try:
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
        #
        # FAIL CLOSED: si API_KEY no esta definida NO se acepta nada. Con
        # `if api_key:` (el codigo anterior) una Lambda sin la variable en
        # su entorno devolvia 200 a CUALQUIERA: un fallo de despliegue
        # convertia la API en publica. Ahora es un 500 explicito.
        api_key = os.environ.get("API_KEY", "")
        if not api_key:
            print("ERROR: API_KEY no esta definida en el entorno de la Lambda")
            return _resp(500, {"error": "API mal configurada"})
        cabeceras = {
            k.lower(): v for k, v in (event.get("headers") or {}).items()
        }
        if not hmac.compare_digest(
            cabeceras.get("x-api-key", "").encode("utf-8"),
            api_key.encode("utf-8"),
        ):
            return _resp(401, {"error": "Clave de API invalida"})

        # AUTENTICACION REAL: un id_token de Cognito del user pool.
        #
        # La x-api-key la pone la CloudFront Function en el edge para
        # cualquier peticion, asi que NO prueba que quien llama sea un
        # usuario del banco: sin esta comprobacion, cualquiera que
        # descubra el dominio gasta la cuota de Bedrock del equipo a
        # voluntad. Con esta comprobacion, hace falta una sesion valida.
        usuario_sesion = ""
        if EXIGIR_TOKEN:
            token = _token_de_la_peticion(event)
            if not _verificar_token_cognito(token):
                return _resp(401, {
                    "error": "Sesion no valida. Inicia sesion en MoraBanc Digital.",
                })
            usuario_sesion = _usuario_del_token(token)

            # Limite por usuario: cada pregunta cuesta una invocacion de
            # Bedrock. Se comprueba DESPUES de autenticar, para que el
            # limite sea por usuario de verdad y no por IP.
            if not _comprobar_ritmo(usuario_sesion or "desconocido"):
                return _resp(429, {
                    "error": "Demasiadas peticiones. Espera un momento e intentalo de nuevo.",
                })

        if not event.get("body"):
            return _resp(400, {"error": "Cuerpo vacio"})

        try:
            payload = json.loads(event["body"])
        except json.JSONDecodeError:
            return _resp(400, {"error": "JSON invalido"})
        if not isinstance(payload, dict):
            return _resp(400, {"error": "JSON invalido"})

        # --- Limites de entrada -------------------------------------------
        #
        # Cada llamada a /preguntar cuesta dinero (Bedrock) y CPU (el
        # motor). Sin limites, cualquiera puede mandar un CSV de 6 MB o
        # una pregunta de 50 KB y amplificar el coste sin limite.
        #
        # Los limites son holgados para el uso real (un extracto
        # bancario de un año tiene unos pocos miles de movimientos) pero
        # cortan la amplificacion.
        pregunta = str(payload.get("pregunta") or "").strip()
        if not pregunta:
            return _resp(400, {"error": "Falta el campo 'pregunta'"})
        if len(pregunta) > MAX_PREGUNTA:
            return _resp(413, {
                "error": "La pregunta es demasiado larga",
                "limite": MAX_PREGUNTA,
            })

        extracto = payload.get("extracto_csv")
        if extracto is not None:
            extracto = str(extracto)
            if len(extracto) > MAX_EXTRACTO:
                return _resp(413, {
                    "error": "El extracto es demasiado grande",
                    "limite": MAX_EXTRACTO,
                })

        # --- Numeros con rango --------------------------------------------
        #
        # `Decimal(str(x))` lanza excepcion si x no es numerico, y eso
        # antes se devolvia al cliente como 500 con el traceback. Ahora
        # se valida antes y se responde 400 sin filtrar nada.
        def _decimal(valor, nombre, maximo):
            if valor is None:
                return None
            try:
                d = Decimal(str(valor))
            except Exception:  # noqa: BLE001
                raise _InputInvalido(f"'{nombre}' no es un numero")
            if not d.is_finite():
                raise _InputInvalido(f"'{nombre}' no es un numero valido")
            if d < 0 or d > maximo:
                raise _InputInvalido(
                    f"'{nombre}' esta fuera de rango (0 - {maximo})"
                )
            return d

        try:
            saldo_actual = _decimal(
                payload.get("saldo_actual", 0), "saldo_actual", MAX_SALDO
            ) or Decimal(0)
            renta_neta_anual = _decimal(
                payload.get("renta_neta_anual"), "renta_neta_anual", MAX_RENTA
            )
            margen_bruto = _decimal(
                payload.get("margen_bruto"), "margen_bruto", MAX_MARGEN
            )
        except _InputInvalido as e:
            return _resp(400, {"error": str(e)})

        fecha_consejo = None
        if payload.get("fecha_consejo"):
            try:
                fecha_consejo = date.fromisoformat(str(payload["fecha_consejo"]))
            except ValueError:
                return _resp(400, {"error": "'fecha_consejo' no es una fecha valida"})

        # --- Contexto de la empresa ---------------------------------------
        movimientos = []
        if extracto:
            movimientos = parse_extracto_csv(extracto)

        ctx = ContextoEmpresa(
            movimientos=movimientos,
            saldo_actual=saldo_actual,
            renta_neta_anual=renta_neta_anual,
            margen_bruto=margen_bruto,
            actividad=str(payload.get("actividad") or "")[:500],
            fecha_consejo=fecha_consejo,
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
        # El traceback se queda EN EL LOG, no en la respuesta: al cliente
        # solo se le da un mensaje generico y un id de correlacion. Antes
        # se devolvian `str(e)` y `traceback.format_exc()`, que filtraban
        # rutas internas (/var/task/lambda/handler.py), lineas de codigo y
        # el tipo de excepcion a cualquier visitante.
        rid = getattr(context, "aws_request_id", "") or ""
        print("ERROR:", str(e), file=sys.stderr)
        traceback.print_exc()
        cuerpo = {"error": "Error interno del servidor", "herramientas": [], "respuesta": ""}
        if rid:
            cuerpo["request_id"] = rid
        return _resp(500, cuerpo)
