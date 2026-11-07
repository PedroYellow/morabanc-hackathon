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
check("hay 2 handlers definidos", len(handlers) == 2, handlers)
check("ambos son 'lambda.handler.lambda_handler'",
      all(h == "lambda.handler.lambda_handler" for h in handlers),
      set(handlers))
check("lambda/__init__.py existe en el repo",
      os.path.isfile(os.path.join(RAIZ, "lambda", "__init__.py")))

# El zip tiene lambda/handler.py -> el modulo es "lambda.handler"
check("lambda/handler.py existe en el repo",
      os.path.isfile(os.path.join(RAIZ, "lambda", "handler.py")))


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

check("la KB se puede desactivar con bedrock_kb_id",
      'var.bedrock_kb_id != "" ? 0 : 1' in SRC)


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
          "local.bucket_suffix" in dom,
          "los prefijos de dominio Cognito son GLOBALES: sin sufijo, "
          "colisiona con otro equipo del hackathon")
    check("el dominio usa var.aws_region (no eu-west-1 hardcodeado)",
          "var.aws_region" in dom)

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
