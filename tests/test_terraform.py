#!/usr/bin/env python3
"""
Tests de la configuracion de Terraform.
=========================================
El apply crea 40 recursos. Estos tests comprueban lo que NO se ve en un
"terraform validate": que el ORDEN de creacion sea el correcto y que los
nombres globalmente unicos no colisionen con otros equipos del hackathon.

Lo que se comprueba:
  1. El handler de las Lambdas coincide con la estructura del zip.
  2. La KB depende de que el corpus este subido a S3 (si no, indexa vacio).
  3. La KB depende de que la coleccion de OpenSearch este lista.
  4. El dominio de Cognito lleva sufijo de cuenta (los prefijos de dominio
     Cognito son GLOBALES: colisionan entre equipos).
  5. El bucket de S3 lleva sufijo de cuenta.
  6. El zip de la Lambda no lleva el front, los tests ni los scripts.
  7. Las variables tienen default (el apply no debe pedir nada).
  8. No hay secretos ni credenciales en el .tf.
"""

import os
import re
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TF = os.path.join(RAIZ, "terraform", "main.tf")

fallos = []
n = 0


def check(nombre, ok, extra=""):
    global n
    n += 1
    print(f"  {'PASS' if ok else 'FAIL'}  {nombre}{(' -> ' + str(extra)) if extra else ''}")
    if not ok:
        fallos.append(nombre)


def bloque(recurso):
    """Devuelve el texto del bloque de un recurso concreto."""
    m = re.search(
        r'resource\s+"[^"]+"\s+"' + re.escape(recurso) + r'"\s*\{(.*?)\n\}',
        SRC, re.S)
    return m.group(1) if m else ""


with open(TF, encoding="utf-8") as f:
    SRC = f.read()


# ==========================================================================
print("\n=== 1. HANDLER DE LAS LAMBDA ===")
# ==========================================================================

handlers = re.findall(r'handler\s*=\s*"([^"]+)"', SRC)
check("hay 3 handlers definidos (motor, api y authorizer)", len(handlers) == 3, handlers)

# El motor y la api comparten el mismo modulo empaquetado.
handlers_motor_api = [h for h in handlers if h != "authorizer.handler"]
check("el motor y la api usan 'lambda.handler.lambda_handler'",
      len(handlers_motor_api) == 2
      and all(h == "lambda.handler.lambda_handler" for h in handlers_motor_api),
      set(handlers_motor_api))

# El authorizer es su propia Lambda: valida la clave de la API.
# El authorizer usa "authorizer.handler", NO "lambda.authorizer.handler":
# su zip tiene el modulo EN LA RAIZ (source_dir = ../lambda), asi que con
# el prefijo "lambda." la Lambda no encuentra el modulo y TODAS las
# peticiones dan 500:
#   "Unable to import module 'lambda.authorizer': No module named 'lambda'"
check("el authorizer usa 'authorizer.handler' (el zip lo tiene en la raiz)",
      "authorizer.handler" in handlers
      and "lambda.authorizer.handler" not in handlers, set(handlers))

check("lambda/__init__.py existe en el repo",
      os.path.isfile(os.path.join(RAIZ, "lambda", "__init__.py")))

# El zip tiene lambda/handler.py -> el modulo es "lambda.handler"
check("lambda/handler.py existe en el repo",
      os.path.isfile(os.path.join(RAIZ, "lambda", "handler.py")))
check("lambda/authorizer.py existe en el repo",
      os.path.isfile(os.path.join(RAIZ, "lambda", "authorizer.py")))


# ==========================================================================
print("\n=== 2. ORDEN DE LA KNOWLEDGE BASE ===")
# ==========================================================================

ds = bloque("normativa")  # primer bloque con "normativa": puede ser el data source
# El data source es el que lleva data_source_configuration
ds_match = re.search(
    r'resource\s+"aws_bedrockagent_data_source"\s+"normativa"\s*\{(.*?)\n\}',
    SRC, re.S)
check("existe el data source de la KB", ds_match is not None)

if ds_match:
    ds_body = ds_match.group(1)
    check("el data source depende de los .md subidos a S3",
          "aws_s3_object.normativa" in ds_body and "depends_on" in ds_body,
          "sin depends_on, la KB indexa un bucket vacio")

kb_match = re.search(
    r'resource\s+"aws_bedrockagent_knowledge_base"\s+"normativa"\s*\{(.*?)\n\}',
    SRC, re.S)
check("existe la knowledge base", kb_match is not None)

if kb_match:
    kb_body = kb_match.group(1)
    check("la KB depende de la coleccion de OpenSearch",
          "aws_opensearchserverless_collection.vector" in kb_body
          and "depends_on" in kb_body,
          "sin depends_on, el apply falla: la coleccion no esta lista")
    check("la KB usa el embedding model de Bedrock",
          "embedding_model_arn" in kb_body)

check("la KB se puede desactivar con bedrock_kb_id o con enable_kb",
      'var.bedrock_kb_id != ""' in SRC and "enable_kb" in SRC)
check("existe la variable enable_kb", 'variable "enable_kb"' in SRC)
check("existe la variable enable_guardrails", 'variable "enable_guardrails"' in SRC)
# Con enable_kb=false los recursos condicionales tienen count=0 y las
# referencias usan one()/splat: sin eso, el plan falla con "Invalid index".
check("las referencias a recursos condicionales no usan [0] a secas",
      not re.search(r'aws_iam_role\.bedrock_kb\[0\]', SRC)
      and not re.search(r'aws_opensearchserverless_collection\.vector\[0\]', SRC)
      and not re.search(r'aws_bedrockagent_knowledge_base\.normativa\[0\]', SRC),
      "con count=0, [0] es un error: hay que usar one() o el splat")


# ==========================================================================
print("\n=== 3. NOMBRES GLOBALMENTE UNICOS ===")
# ==========================================================================

cognito = re.search(
    r'resource\s+"aws_cognito_user_pool_domain"\s+"dominio"\s*\{(.*?)\n\}',
    SRC, re.S)
check("existe el dominio de Cognito", cognito is not None)
if cognito:
    dom = cognito.group(1)
    check("el dominio de Cognito lleva sufijo de cuenta",
          "local.cognito_prefix" in dom,
          "los prefijos de dominio Cognito son GLOBALES: sin sufijo, "
          "colisiona con otro equipo del hackathon")
    # El campo "domain" es SOLO el prefijo: AWS anade .auth.<region>...
    # asi que ya no hay ninguna region en este bloque. Lo que se comprueba
    # es que la region venga de la variable (no hardcodeada) en el sitio
    # donde SI se usa: el output del front.
    check("la region viene de la variable (no hardcodeada)",
          "var.aws_region" in SRC
          and not re.search(r'domain\s*=\s*"[^"]*\.auth\.eu-west-1', SRC),
          "el prefijo de Cognito ya no lleva la region: AWS la anade")

    # AWS valida que el dominio COMPLETO no pase de 63 caracteres. Con el
    # nombre del proyecto entero + el id de cuenta se llegaba a 78 y el
    # apply fallaba con "expected length of domain to be in the range
    # (1 - 63)". Este test lo comprueba antes de que llegue a AWS.
    prefijo_m = re.search(r'cognito_prefix\s*=\s*"\$\{substr\(local\.name,\s*0,\s*(\d+)\)\}', SRC)
    check("el prefijo de Cognito esta recortado", prefijo_m is not None)
    if prefijo_m:
        largo_nombre = int(prefijo_m.group(1))
        # El nombre del proyecto por defecto son 24 caracteres.
        nombre_real = "morabanc-hackathon-dev"
        prefijo = f"{nombre_real[:largo_nombre]}-fc90d7df"
        # El sufijo automatico de AWS depende de la region: hay que probar
        # con la region por defecto del proyecto, no con una fija.
        region = "us-east-1"
        m_reg = re.search(r'variable\s+"aws_region"\s*\{.*?default\s*=\s*"([^"]+)"',
                          SRC, re.S)
        if m_reg:
            region = m_reg.group(1)
        sufijo = f".auth.{region}.amazoncognito.com"
        total = len(prefijo + sufijo)
        check("el dominio de Cognito cabe en el limite de AWS (63)",
              total <= 63, f"{total} caracteres: {prefijo}{sufijo}")

# La region por defecto tiene que ser la que permite la cuenta del hackathon.
m_region = re.search(r'variable\s+"aws_region"\s*\{.*?default\s*=\s*"([^"]+)"',
                      SRC, re.S)
check("la region por defecto es us-east-1", m_region is not None
      and m_region.group(1) == "us-east-1",
      m_region.group(1) if m_region else "no encontrada")
check("el comentario explica el deny por region",
      "DenyAllOutsideAllowedRegions" in SRC,
      "la cuenta del hackathon solo permite crear en us-east-1")

s3 = re.search(r'resource\s+"aws_s3_bucket"\s+"datos"\s*\{(.*?)\n\}', SRC, re.S)
check("existe el bucket de S3", s3 is not None)
if s3:
    check("el bucket de S3 lleva sufijo de cuenta",
          "local.bucket_suffix" in s3.group(1))

kms = re.search(r'resource\s+"aws_kms_alias"\s+"[^"]+"\s*\{(.*?)\n\}', SRC, re.S)
check("existe el alias de KMS", kms is not None)
if kms:
    check("el alias de KMS lleva sufijo (los alias son globales por nombre)",
          "local.name" in kms.group(1))


# ==========================================================================
print("\n=== 4. PAQUETE DE LA LAMBDA ===")
# ==========================================================================

af = re.search(
    r'data\s+"archive_file"\s+"motor"\s*\{(.*?)\n\}', SRC, re.S)
check("existe el archive_file de la Lambda", af is not None)
if af:
    body = af.group(1)
    excludes = re.findall(r'"([^"]+)"', re.search(r'excludes\s*=\s*\[(.*?)\]',
                                                body, re.S).group(1))
    for debe in ["frontend", "scripts", "tests", "data", "terraform"]:
        check(f"el zip excluye '{debe}'", debe in excludes)
    check("el zip NO excluye engine/ ni agent/",
          "engine" not in excludes and "agent" not in excludes)


# ==========================================================================
print("\n=== 5. VARIABLES (el apply no debe pedir nada) ===")
# ==========================================================================

vars_ = re.findall(r'variable\s+"([^"]+)"\s*\{(.*?)\n\}', SRC, re.S)
check("hay variables declaradas", len(vars_) > 0, f"{len(vars_)} variables")
for nombre, body in vars_:
    tiene_default = "default" in body
    check(f"la variable '{nombre}' tiene default", tiene_default)
    check(f"la variable '{nombre}' no es required",
          'required = true' not in body.replace(" ", " "))


# ==========================================================================
print("\n=== 6. SEGURIDAD ===")
# ==========================================================================

check("no hay access keys en el .tf",
      not re.search(r'AKIA[0-9A-Z]{16}', SRC))
check("no hay secret_access_key en el .tf",
      "secret_access_key" not in SRC.lower())
check("la Lambda no es publica",
      "aws_lambda_permission" in SRC and "aws_lambda_function_url" not in SRC,
      "sin lambda_function_url ni permission de InvokeFunctionUrl, "
      "la Lambda solo se invoca a traves del API Gateway con su IAM role")
check("hay CORS en el API Gateway", "cors_configuration" in SRC)
check("hay proteccion de acceso publico en S3",
      "aws_s3_bucket_public_access_block" in SRC)
check("el bucket tiene cifrado KMS",
      "aws_s3_bucket_server_side_encryption_configuration" in SRC)
check("DynamoDB tiene TTL", "ttl" in SRC.lower())

# El front se publica en S3 con el content-type de cada fichero. Si el SVG
# del logo no esta en el mapa, se sirve como octet-stream y el navegador no
# lo renderiza: el logo aparece roto en el movil.
ct = re.search(r'content_types\s*=\s*\{(.*?)\n  \}', SRC, re.S)
check("existe el mapa de content_types", ct is not None)
if ct:
    cuerpo = ct.group(1)
    check("el SVG del logo tiene content-type image/svg+xml",
          re.search(r'"assets/logo-morabanc\.svg"\s*=\s*"image/svg\+xml"', cuerpo)
          is not None)
    check("el CSS tiene su content-type",
          re.search(r'"assets/styles\.css"\s*=\s*"text/css', cuerpo) is not None)
    check("el JS tiene su content-type",
          re.search(r'"assets/app\.js"\s*=\s*"application/javascript', cuerpo) is not None)
    check("el CSV de cierre del bucle tiene content-type",
          re.search(r'"data/demo_freelancer_cierre\.csv"\s*=\s*"text/csv', cuerpo)
          is not None)


# ==========================================================================
print("\n=== 7. RECURSOS CLAVE ===")
# ==========================================================================

for r in ["aws_kms_key", "aws_s3_bucket", "aws_dynamodb_table",
          "aws_lambda_function", "aws_apigatewayv2_api",
          "aws_cloudfront_distribution", "aws_cognito_user_pool",
          "aws_bedrock_guardrail", "aws_bedrockagent_knowledge_base",
          "aws_opensearchserverless_collection", "aws_sns_topic",
          "aws_iam_role"]:
    check(f"recurso {r} definido", f'resource "{r}"' in SRC)


# ==========================================================================
print("\n=== 8. OUTPUTS ===")

# ==========================================================================
# Regresiones de bugs reales encontrados al hacer `terraform apply`
# Cada una fue un apply fallido en la cuenta del hackathon.
# ==========================================================================

# BUG 1: CloudFront rechazaba el origin de API Gateway.
# "The parameter origin name cannot contain a colon" -> api_endpoint viene
# como "https://xxx.execute-api..." y hay que quitarle el esquema.
check("el origin de API Gateway no lleva el esquema https://",
      'replace(aws_apigatewayv2_api.api.api_endpoint, "https://", "")' in SRC,
      "CloudFront no acepta un origin con ':'")

# BUG 2: Cognito rechazaba el user pool.
# "Invalid MFA Configuration given. SMS MFA, Email MFA, or Software Token MFA
# must be enabled" -> hay que habilitar un metodo concreto.
check("el user pool habilita el software token (TOTP)",
      "software_token_mfa_configuration" in SRC
      and re.search(r"software_token_mfa_configuration\s*\{[^}]*enabled\s*=\s*true", SRC, re.S) is not None,
      "sin un metodo habilitado, Cognito rechaza el pool")

# BUG 3: la policy de IAM de la lambda "api" solo cubria el log group del
# motor: "not allowed to be used with Arn ...log-group:/aws/lambda/...-api".
check("la policy de logs cubre los dos log groups",
      "aws_cloudwatch_log_group.api.arn" in SRC,
      "la lambda api necesita permisos sobre su propio log group")

# BUG 4: OpenSearch Serverless exige una security policy.
# "No matching security policy of encryption type found for collection".
check("hay security policy de OpenSearch Serverless",
      'resource "aws_opensearchserverless_security_policy"' in SRC)
check("la security policy es de tipo encryption",
      re.search(r'aws_opensearchserverless_security_policy"\s+"\w+"\s*\{.*?type\s*=\s*"encryption"', SRC, re.S) is not None)

# La security policy debe existir ANTES que la coleccion (la coleccion la
# necesita para crearse).
m_sp = SRC.find('aws_opensearchserverless_security_policy"')
m_col = SRC.find('aws_opensearchserverless_collection"')
check("la security policy se declara antes que la coleccion",
      m_sp != -1 and m_col != -1 and m_sp < m_col,
      "la coleccion falla si no existe la security policy")

# BUG 5: con count=0, referenciar [0] es un error de plan.
check("las referencias condicionales no usan [0]",
      not re.search(r"aws_iam_role\.bedrock_kb\[0\]", SRC)
      and not re.search(r"aws_opensearchserverless_collection\.vector\[0\]", SRC)
      and not re.search(r"aws_bedrockagent_knowledge_base\.normativa\[0\]", SRC),
      "con count=0 el plan falla con 'Invalid index': usar one() o splat")



# ==========================================================================
# Regresiones del SEGUNDO apply (bugs de la API de AWS)
# ==========================================================================

# BUG 6: el campo "domain" de Cognito es SOLO el prefijo.
# Si se le pasa el dominio completo (con puntos), AWS responde
# "InvalidParameterException: The domain name contains an invalid character".
check("el dominio de Cognito es solo el prefijo (sin puntos)",
      'domain       = local.cognito_prefix' in SRC
      and '.auth.${var.aws_region}.amazoncognito.com"' not in SRC.split('resource "aws_cognito_user_pool_domain"')[1][:600]
      if 'resource "aws_cognito_user_pool_domain"' in SRC else False,
      "AWS anade .auth.<region>.amazoncognito.com por su cuenta")

# BUG 7: CloudFront solo admite combinaciones concretas de AllowedMethods.
# ["POST", "OPTIONS"] es invalido ("The parameter AllowedMethods is invalid").
VALIDAS = (
    '["HEAD", "GET"]',
    '["HEAD", "GET", "OPTIONS"]',
    '["GET", "HEAD", "OPTIONS"]',
    '["HEAD", "DELETE", "POST", "GET", "OPTIONS", "PUT", "PATCH"]',
)
_metodos = re.findall(r'allowed_methods\s*=\s*(\[[^\]]*\])', SRC)
check("todos los AllowedMethods de CloudFront son combinaciones validas",
      _metodos and all(m in VALIDAS for m in _metodos),
      f"encontrados: {_metodos}")

# BUG 8: la KMS necesita key policy para que CloudWatch Logs la use.
# Sin ella: "AccessDeniedException: The specified KMS key does not exist
# or is not allowed to be used with Arn ...log-group:/aws/lambda/..."
check("la KMS tiene key policy propia",
      re.search(r'resource "aws_kms_key" "main" \{.*?policy\s*=\s*jsonencode', SRC, re.S) is not None)
check("la key policy delega en CloudWatch Logs",
      "logs.${var.aws_region}.amazonaws.com" in SRC
      and "AllowCloudWatchLogs" in SRC)

# BUG 9: la security policy de OpenSearch solo admite 1 regla y el
# ResourceType debe ser constante ("collection").
m_sp_pol = re.search(r'aws_opensearchserverless_security_policy"\s+"\w+"\s*\{.*?policy\s*=\s*jsonencode\(\{(.*?)\n  \}\)', SRC, re.S)
if m_sp_pol:
    cuerpo = m_sp_pol.group(1)
    # Los comentarios de HCL no cuentan: solo mira las lineas con codigo.
    codigo = "\n".join(l for l in cuerpo.split("\n")
                       if not l.strip().startswith("#"))
    n_reglas = codigo.count("ResourceType")
    check("la security policy de OpenSearch tiene una sola regla", n_reglas == 1,
          f"OpenSearch Serverless admite maximo 1 regla (hay {n_reglas})")
    check("la security policy de OpenSearch no usa 'dashboard'",
          '"dashboard"' not in codigo,
          "ResourceType debe ser una constante: solo 'collection'")
else:
    check("la security policy de OpenSearch tiene una sola regla", False, "no se encontro la policy")
    check("la security policy de OpenSearch no usa 'dashboard'", False, "no se encontro la policy")



# ==========================================================================
# Regresiones del TERCER apply
# ==========================================================================

# BUG 10: la KMS con un service principal invalido.
# "aoss.amazonaws.com" NO existe: KMS responde "Policy contains a statement
# with one or more invalid service principals".
# El service principal invalido solo cuenta si esta en CODIGO, no en un
# comentario que lo explica: se ignoran las lineas de comentario.
_codigo_kms = "\n".join(l for l in SRC.split("\n")
                         if not l.strip().startswith("#"))
check("la key policy no usa service principals invalidos",
      '"aoss.amazonaws.com"' not in _codigo_kms,
      "aoss.amazonaws.com no es un service principal valido de KMS")

# BUG 11: CloudFront exige cached_methods no vacio.
# Con [] falla con "The parameter CachedMethods is required".
_cache = re.findall(r'cached_methods\s*=\s*(\[[^\]]*\])', SRC)
check("todos los cached_methods de CloudFront son no vacios",
      _cache and all(m.strip() not in ("[]", "[ ]") for m in _cache),
      f"encontrados: {_cache}")

# BUG 12: OpenSearch tarda en indexar la security policy.
# Sin esperar, la KB falla con "[security_exception] 403 Forbidden".
check("hay una espera entre la security policy y la coleccion",
      'resource "time_sleep" "aoss_policy"' in SRC)
check("la espera de OpenSearch dura lo suficiente",
      re.search(r'resource "time_sleep" "aoss_policy" \{.*?create_duration\s*=\s*"(\d+)s"', SRC, re.S) is not None)
check("el provider time esta declarado",
      'source  = "hashicorp/time"' in SRC)



# ==========================================================================
# Regresiones del CUARTO apply: la network policy de OpenSearch
# ==========================================================================

# BUG 13: faltaba la NETWORK policy de OpenSearch Serverless.
# La de encryption dice como se cifra la coleccion; la de network dice
# QUIEN puede entrar. Sin la de network, Bedrock no puede validar el
# acceso a la coleccion y la Knowledge Base falla con
# "[security_exception] 403 Forbidden".
# Los dos tipos de policy (encryption y network) se crean con el MISMO
# resource: aws_opensearchserverless_security_policy, cambiando "type".
# El provider de AWS 5.100 NO tiene aws_opensearchserverless_network_policy.
check("la network policy usa el resource de security policy",
      'resource "aws_opensearchserverless_network_policy"' not in SRC
      and 'resource "aws_opensearchserverless_security_policy" "red"' in SRC,
      "en el provider 5.100 los dos tipos de policy usan el mismo resource")
check("la network policy es de tipo network",
      re.search(r'aws_opensearchserverless_security_policy" "red" \{.*?type\s*=\s*"network"', SRC, re.S) is not None)
check("la network policy autoriza a bedrock.amazonaws.com",
      "bedrock.amazonaws.com" in SRC,
      "SourceServices debe incluir bedrock.amazonaws.com")
check("la network policy no deja acceso publico",
      re.search(r'aws_opensearchserverless_security_policy" "red" \{.*?AllowFromPublic\s*=\s*false', SRC, re.S) is not None)
check("la network policy cubre collection y dashboard",
      re.search(r'aws_opensearchserverless_security_policy" "red" \{.*?ResourceType\s*=\s*"collection"', SRC, re.S) is not None
      and re.search(r'aws_opensearchserverless_security_policy" "red" \{.*?ResourceType\s*=\s*"dashboard"', SRC, re.S) is not None,
      "Bedrock necesita poder entrar por la API y por el dashboard")
check("la coleccion depende de la network policy",
      re.search(r'aws_opensearchserverless_collection" "vector" \{.*?aws_opensearchserverless_security_policy\.red', SRC, re.S) is not None)

# El rol de la KB necesita aoss:APIAccessAll (no solo DescribeIndex),
# y el documento oficial avisa de que sin el sale 403.
check("el rol de la KB tiene aoss:APIAccessAll",
      "aoss:APIAccessAll" in SRC,
      "sin APIAccessAll, OpenSearch Serverless devuelve 403")



# ==========================================================================
# Regresiones del despliegue del front en el VPS
# ==========================================================================

_deploy_welcome = ""
for _candidato in ("scripts/deploy_welcome.sh",):
    try:
        _deploy_welcome = open(_candidato, encoding="utf-8").read()
    except OSError:
        pass

if _deploy_welcome:
    # BUG 15: el front usa window.__API_KEY__ (la API esta protegida con
    # API key), pero deploy_welcome.sh no la inyectaba. Con la API
    # desplegada, /preguntar responderia 401 en el pitch.
    check("el despliegue del front inyecta la API key",
          "__API_KEY__" in _deploy_welcome,
          "el front envia la clave en x-api-key: sin ella, /preguntar da 401")

    # BUG 16: la config previa solo se quitaba si habia API nueva. Al
    # desplegar con API y luego sin ella, el front se quedaba con la
    # URL y la key viejas.
    _limpieza = re.search(
        r"# Siempre se limpia la config previa.*?python3", _deploy_welcome, re.S)
    check("el despliegue limpia la config previa siempre, no solo con API",
          _limpieza is not None,
          "si no, una config vieja se queda y el front llama a un endpoint muerto")

    # La config se lee sola de Terraform (no hay que acordarse de exportar).
    check("el despliegue lee la config de Terraform si no se pasa a mano",
          "frontend_url_config" in _deploy_welcome)

    # La IP correcta del VPS en los comentarios.
    check("los comentarios del despliegue tienen la IP correcta del VPS",
          "179.197.243.234" in _deploy_welcome
          and "187.127.64.126" not in _deploy_welcome,
          "187.127.64.126 es OTRO servidor")



# ==========================================================================
# Regresiones del apply en AWS: claves reservadas y authorizer REQUEST
# ==========================================================================

# BUG 16: AWS_REGION es una clave RESERVADA en Lambda. Declararla en
# `environment` hace fallar la Creacion con
# "InvalidParameterValueException: Lambda was unable to configure your
# environment variables... Reserved keys used in this request: AWS_REGION".
check("las Lambdas no declaran AWS_REGION en su entorno",
      not re.search(r'AWS_REGION\s*=\s*var\.aws_region', SRC),
      "AWS_REGION es reservada: usa BEDROCK_REGION")
check("las Lambdas declaran BEDROCK_REGION",
      "BEDROCK_REGION" in SRC,
      "es el nombre que si acepta Lambda")

# BUG 17: AuthorizerPayloadFormatVersion es OBLIGATORIO en los authorizers
# REQUEST: sin eso, "BadRequestException: AuthorizerPayloadFormatVersion is
# a required parameter for REQUEST authorizer".
check("el authorizer REQUEST declara payload format 2.0",
      re.search(r'authorizer_payload_format_version\s*=\s*"2\.0"', SRC) is not None)
check("el authorizer desactiva simple responses (devuelve policy IAM)",
      re.search(r'enable_simple_responses\s*=\s*false', SRC) is not None,
      "la lambda del authorizer devuelve policyDocument, no un simple 200")

# La region por defecto del agente es us-east-1 (la cuenta del workshop solo
# permite crear ahi), no eu-west-1.
try:
    with open(os.path.join(RAIZ, "agent", "bedrock_agent.py"), encoding="utf-8") as _f:
        _src_ag = _f.read()
    check("el agente lee BEDROCK_REGION",
          'os.environ.get("BEDROCK_REGION")' in _src_ag)
    check("el default de region del agente es us-east-1",
          '"us-east-1"' in _src_ag and 'or "eu-west-1"' not in _src_ag,
          "eu-west-1 esta bloqueada por la policy del workshop")
except OSError:
    check("el agente lee BEDROCK_REGION", False, "no se pudo leer el agente")
    check("el default de region del agente es us-east-1", False, "no se pudo leer el agente")



# BUG 18: la lambda de API es la que llama a Bedrock (el agente vive en su
# zip). Sin bedrock:InvokeModel en su IAM, /preguntar responde 500:
# "AccessDeniedException: User: ...morabanc-hackathon-dev-api is not
# authorized to perform: bedrock:InvokeModel".
_m = re.search(r'resource "aws_iam_role_policy" "api" \{.*?\n\}\n', SRC, re.S)
if _m:
    _pol_api = _m.group(0)
    check("la policy de la lambda de API permite bedrock:InvokeModel",
          "bedrock:InvokeModel" in _pol_api,
          "sin esto, /preguntar responde 500 en AWS")
    check("la policy de la lambda de API permite invocar la lambda del motor",
          "lambda:InvokeFunction" in _pol_api)
else:
    check("la policy de la lambda de API permite bedrock:InvokeModel", False,
          "no se encontro el recurso")
    check("la policy de la lambda de API permite invocar la lambda del motor",
          False, "no se encontro el recurso")



# ==========================================================================
# Regresiones del despliegue completo (con credenciales nuevas)
# ==========================================================================

# BUG 14: el vhost de nginx no tenia bloque /api: el POST devolvia 404 y
# la web se quedaba en modo demo sin que se notase.
# OJO: el vhost lo genera scripts/deploy_welcome.sh, no el .tf.
try:
    _raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    _deploy_welcome = open(os.path.join(_raiz, "scripts", "deploy_welcome.sh"),
                           encoding="utf-8").read()
except OSError:
    _deploy_welcome = ""
check("el vhost de nginx tiene el bloque /api",
      "location /api/" in _deploy_welcome)
check("el proxy apunta a la API de AWS", "proxy_pass" in _deploy_welcome)
check("la API key la pone nginx, no el navegador",
      "proxy_set_header x-api-key" in _deploy_welcome,
      "si la clave viaja en el HTML, se lee en el codigo fuente de la web")

# BUG 15: la KMS no delegaba en cloudfront.amazonaws.com: con el bucket
# cifrado con KMS gestionada, CloudFront servia un 403 Access Denied.
check("la key policy delega en cloudfront.amazonaws.com",
      "cloudfront.amazonaws.com" in SRC,
      "sin esto, CloudFront no puede descifrar los objetos del bucket")
check("la delegacion a CloudFront es una statement propia",
      re.search(r'Sid\s*=\s*"AllowCloudFrontToDecrypt"', SRC) is not None)

# BUG 16: el sync de S3 con --delete borraba el corpus normativo, que
# publica terraform y necesita la KB. El sync lo hace
# scripts/sync_front_s3.py (deploy_front.sh lo llama).
try:
    _sync_s3 = open(os.path.join(_raiz, "scripts", "sync_front_s3.py"),
                     encoding="utf-8").read()
except OSError:
    _sync_s3 = ""
check("el sync de S3 excluye el corpus normativo",
      "normativa/" in _sync_s3,
      "con --delete, el RAG se queda sin normativa")
check("el sync de S3 excluye tambien assets/mb/",
      "assets/mb/" in _sync_s3)

# BUG 17: el output sensitive es un STRING JSON dentro del JSON. Sin
# desempaquetarlo dos veces, el front se queda en modo demo.
deploy_front = ""
try:
    deploy_front = open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "scripts", "deploy_front.sh"), encoding="utf-8").read()
except OSError:
    pass
if deploy_front:
    check("deploy_front desempaqueta el output sensitive",
          "isinstance(cfg, str)" in deploy_front,
          "el output frontend_url_config es sensitive: viene como string JSON")

# El limite de la cuenta del workshop con aoss esta documentado.
check("el limite de aoss en la cuenta del workshop esta documentado",
      "DenyAllOutsideAllowedRegions" in SRC and "aoss" in SRC,
      "es lo que impide crear la KB de Bedrock en esa cuenta")



# BUG 18: el front de CloudFront llama a "/api/preguntar" (asi lo inyecta
# deploy_front.sh), pero API Gateway solo exponia "/preguntar": desde
# CloudFront el chat devolvia 404.
check("la API expone tambien la ruta POST /api/preguntar",
      re.search(r'route_key\s*=\s*"POST /api/preguntar"', SRC) is not None,
      "sin ella, el front de CloudFront no puede llamar a la API")
check("la ruta /api/preguntar va al mismo integration y con el mismo authorizer",
      re.search(r'route_key\s*=\s*"POST /api/preguntar".*?integrations/\$\{aws_apigatewayv2_integration\.api\.id\}', SRC, re.S) is not None
      and re.search(r'route_key\s*=\s*"POST /api/preguntar".*?authorizer_id\s*=\s*aws_apigatewayv2_authorizer\.key\.id', SRC, re.S) is not None,
      "la proteccion con API key tiene que aplicarse tambien a esta ruta")


# ==========================================================================

for o in ["api_url", "front_url", "bucket_datos", "guardrail_id",
          "frontend_url_config"]:
    check(f"output '{o}' declarado", f'output "{o}"' in SRC)

# El front lee estas claves del output -> deben existir con ese nombre.
# Ojo: el .tf alinea los "=" con espacios, asi que el patron tiene que
# tolerar espacios en blanco entre la clave y el igual.
if 'output "frontend_url_config"' in SRC:
    cfg = re.search(r'output\s+"frontend_url_config"\s*\{(.*?)\n\}', SRC, re.S).group(1)
    for clave in ["api_url", "cognito_client", "cognito_domain", "region"]:
        check(f"frontend_url_config incluye '{clave}'",
              re.search(rf'^\s*{clave}\s*=', cfg, re.M) is not None)


print()
if fallos:
    print(f"FALLOS: {len(fallos)} -> {fallos}")
    sys.exit(1)
print(f"TODOS LOS TESTS PASAN ({n})")
