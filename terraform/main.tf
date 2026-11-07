############################################################
#  Hackathon MoraBanc — IA + Finanzas
#  Infraestructura AWS — 100% Terraform (requisito de las bases)
#
#  Base tecnica de MoraBanc, clausula cuarta:
#  "Toda la infraestructura AWS que se desarrolle o configure habra de estar
#   definida integramente mediante Terraform (HashiCorp), en su formato
#   nativo (HCL) o compatible."
#
#  Este fichero es el punto de entrada. Todo lo que se use en el hackathon
#  esta definido aqui: no hay un solo recurso creado a mano en la consola.
############################################################

terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.60"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = "morabanc-hackathon-ia-finanzas"
      ManagedBy   = "terraform"
      Event       = "morabanc-hackathon-2026"
      Environment = var.environment
    }
  }
}

# ---------------------------------------------------------------------------
#  Variables
# ---------------------------------------------------------------------------

variable "aws_region" {
  description = "Region de AWS. Eur-west-1 (Irlanda) por latencia baja desde Andorra."
  type        = string
  default     = "eu-west-1"
}

variable "environment" {
  description = "Entorno: dev | prod"
  type        = string
  default     = "dev"

  validation {
    condition     = contains(["dev", "prod"], var.environment)
    error_message = "environment debe ser dev o prod."
  }
}

variable "project_name" {
  description = "Prefijo de todos los recursos."
  type        = string
  default     = "morabanc-hackathon"
}

variable "bedrock_model_id" {
  description = "Modelo de Amazon Bedrock para el agente."
  type        = string
  default     = "amazon.nova-pro-v1:0"
}

variable "bedrock_kb_id" {
  description = "Knowledge Base de Bedrock con la normativa andorrana (opcional)."
  type        = string
  default     = ""
}

variable "enable_guardrails" {
  description = "Si activar Bedrock Guardrails (bloqueo de advice financiero no permitido y PII)."
  type        = bool
  default     = true
}

variable "log_retention_days" {
  description = "Retencion de logs en CloudWatch."
  type        = number
  default     = 14
}

variable "cors_allowed_origins" {
  description = "Origenes permitidos para el front estatico."
  type        = list(string)
  default     = ["http://localhost:5173", "http://localhost:3000"]
}

variable "alert_email" {
  description = "Email para las alarmas de CloudWatch (opcional)."
  type        = string
  default     = ""
}

# ---------------------------------------------------------------------------
#  Locales
# ---------------------------------------------------------------------------

data "aws_caller_identity" "current" {}

data "aws_region" "current" {}

locals {
  name = "${var.project_name}-${var.environment}"

  # El nombre de los buckets S3 es globalmente unico: le anadimos el id de
  # cuenta para evitar colisiones cuando hay varios equipos en la misma cuenta.
  bucket_suffix = "${data.aws_caller_identity.current.account_id}-${substr(data.aws_caller_identity.current.account_id, 0, 4)}"

  # Runtime de Lambda. python3.13 es el mas reciente disponible en el
  # provider aws 5.x (python3.14 todavia no lo soporta).
  python_runtime = "python3.13"

  # politica de IAM minima para las Lambdas: solo lo que necesitan
  lambda_log_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents",
      ]
      Resource = "arn:aws:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:log-group:/aws/lambda/${local.name}*"
    }]
  })

  tags = {
    Component = "morabanc-decision-engine"
  }
}

# ---------------------------------------------------------------------------
#  KMS — cifrado de datos
# ---------------------------------------------------------------------------

resource "aws_kms_key" "main" {
  description             = "Cifrado de datos del motor de decisiones (${local.name})"
  enable_key_rotation     = true
  deletion_window_in_days = 7
  tags                    = local.tags
}

resource "aws_kms_alias" "main" {
  name          = "alias/${local.name}"
  target_key_id = aws_kms_key.main.key_id
}

# ---------------------------------------------------------------------------
#  S3 — extractos bancarios y corpus normativo
# ---------------------------------------------------------------------------

resource "aws_s3_bucket" "datos" {
  bucket = "${local.name}-datos-${local.bucket_suffix}"
  tags   = local.tags
}

resource "aws_s3_bucket_server_side_encryption_configuration" "datos" {
  bucket = aws_s3_bucket.datos.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.main.arn
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_public_access_block" "datos" {
  bucket = aws_s3_bucket.datos.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "datos" {
  bucket = aws_s3_bucket.datos.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "datos" {
  bucket = aws_s3_bucket.datos.id

  rule {
    id     = "caducar_extractos"
    status = "Enabled"

    filter {
      prefix = "extractos/"
    }

    expiration {
      days = 90
    }

    noncurrent_version_expiration {
      noncurrent_days = 30
    }
  }
}

# ---------------------------------------------------------------------------
#  DynamoDB — movimientos, escenarios y resultados medidos
# ---------------------------------------------------------------------------

resource "aws_dynamodb_table" "principal" {
  name         = "${local.name}-principal"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "empresa_id"
  range_key    = "registro_id"
  tags         = local.tags

  attribute {
    name = "empresa_id"
    type = "S"
  }

  attribute {
    name = "registro_id"
    type = "S"
  }

  # El TTL es lo que hace que esto sea un producto y no un archivo:
  # los datos del cliente se borran solos.
  ttl {
    attribute_name = "expira_en"
    enabled        = true
  }

  point_in_time_recovery {
    enabled = true
  }

  server_side_encryption {
    enabled = true
  }
}

# ---------------------------------------------------------------------------
#  CloudWatch — logs
# ---------------------------------------------------------------------------

resource "aws_cloudwatch_log_group" "lambda" {
  name              = "/aws/lambda/${local.name}"
  retention_in_days = var.log_retention_days
  kms_key_id        = aws_kms_key.main.arn
  tags              = local.tags
}

resource "aws_cloudwatch_log_group" "api" {
  name              = "/aws/lambda/${local.name}-api"
  retention_in_days = var.log_retention_days
  kms_key_id        = aws_kms_key.main.arn
  tags              = local.tags
}

# ---------------------------------------------------------------------------
#  IAM — roles de las Lambdas
# ---------------------------------------------------------------------------

data "aws_iam_policy_document" "lambda_assume" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

data "aws_iam_policy_document" "lambda_exec" {
  # Permisos de bedrock: solo invocar el modelo concreto que usamos.
  statement {
    sid       = "BedrockInvoke"
    effect    = "Allow"
    actions   = ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"]
    resources = ["arn:aws:bedrock:${var.aws_region}::foundation-model/${var.bedrock_model_id}"]

    condition {
      test     = "StringEquals"
      variable = "aws:RequestTag/Project"
      values   = ["morabanc-hackathon-ia-finanzas"]
    }
  }

  # RAG sobre la knowledge base (solo si esta configurada)
  dynamic "statement" {
    for_each = var.bedrock_kb_id != "" ? [1] : []
    content {
      sid       = "BedrockKnowledgeBase"
      effect    = "Allow"
      actions   = ["bedrock:Retrieve", "bedrock:RetrieveAndGenerate"]
      resources = ["arn:aws:bedrock:${var.aws_region}:${data.aws_caller_identity.current.account_id}:knowledge-base/${var.bedrock_kb_id}"]
    }
  }

  statement {
    sid       = "Logs"
    effect    = "Allow"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.lambda.arn}:*"]
  }

  statement {
    sid       = "DynamoDB"
    effect    = "Allow"
    actions   = ["dynamodb:PutItem", "dynamodb:GetItem", "dynamodb:Query", "dynamodb:UpdateItem", "dynamodb:DeleteItem"]
    resources = [aws_dynamodb_table.principal.arn]
  }

  statement {
    sid       = "S3Extractos"
    effect    = "Allow"
    actions   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
    resources = ["${aws_s3_bucket.datos.arn}/extractos/*"]
  }

  statement {
    sid       = "KMSDecrypt"
    effect    = "Allow"
    actions   = ["kms:Decrypt", "kms:GenerateDataKey"]
    resources = [aws_kms_key.main.arn]
  }
}

resource "aws_iam_role" "lambda" {
  name               = "${local.name}-lambda"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
  tags               = local.tags
}

resource "aws_iam_role_policy" "lambda" {
  name   = "${local.name}-lambda-policy"
  role   = aws_iam_role.lambda.id
  policy = data.aws_iam_policy_document.lambda_exec.json
}

# ---------------------------------------------------------------------------
#  Lambda — el motor (una sola, empaquetada con el codigo)
# ---------------------------------------------------------------------------

resource "aws_iam_role" "api" {
  name               = "${local.name}-api"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
  tags               = local.tags
}

resource "aws_iam_role_policy" "api" {
  name = "${local.name}-api-policy"
  role = aws_iam_role.api.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["lambda:InvokeFunction"]
      Resource = aws_lambda_function.motor.arn
    }]
  })
}

# El zip de la Lambda contiene el codigo COMPLETO del proyecto:
#   /lambda/handler.py  -> el handler
#   /engine/            -> motor determinista (fiscal + tesoreria)
#   /agent/             -> agente de Bedrock (tool-use)
# El handler hace sys.path.insert con su propio directorio, asi que la
# estructura del zip debe ser plana en la raiz.
data "archive_file" "motor" {
  type        = "zip"
  source_dir  = "${path.module}/.."
  output_path = "${path.module}/.build/motor.zip"
  # El zip lleva SOLO lo que la Lambda necesita en runtime: engine/, agent/,
  # lambda/ y el paquete normativo. Fuera todo lo demas (front, scripts,
  # demos, terraform, tests) — no solo engorda el paquete: reduces el
  # cold start y evita subir ficheros que no son codigo.
  excludes = [
    "__pycache__",
    "*.pyc",
    ".pytest_cache",
    ".build",
    ".github",
    "terraform",
    "data",
    "tests",
    "scripts",
    "frontend",
    "demo.py",
    "demo_integrada.py",
    "*.md",
    "*.html",
    "*.json",
    ".git",
  ]
}

resource "aws_lambda_function" "motor" {
  function_name = "${local.name}-motor"
  role          = aws_iam_role.lambda.arn
  # El zip tiene engine/, agent/ y lambda/ en la raiz, y lambda/ tiene un
  # __init__.py: el modulo es "lambda.handler" y la funcion "lambda_handler".
  # Con "handler.lambda_handler" la Lambda no encuentra el modulo y falla
  # con ModuleNotFoundError en la primera invocacion.
  handler     = "lambda.handler.lambda_handler"
  runtime     = local.python_runtime
  timeout     = 60
  memory_size = 1024

  filename         = data.archive_file.motor.output_path
  source_code_hash = data.archive_file.motor.output_base64sha256

  environment {
    variables = {
      AWS_REGION       = var.aws_region
      BEDROCK_MODEL_ID = var.bedrock_model_id
      BEDROCK_KB_ID    = var.bedrock_kb_id
      BUCKET_DATOS     = aws_s3_bucket.datos.id
      TABLE_PRINCIPAL  = aws_dynamodb_table.principal.name
      KMS_KEY_ID       = aws_kms_key.main.key_id
      ENVIRONMENT      = var.environment
      PYTHONPATH       = "/var/task"
    }
  }

  tracing_config {
    mode = "Active"
  }

  depends_on = [
    aws_cloudwatch_log_group.lambda,
    aws_iam_role_policy.lambda,
  ]

  tags = local.tags
}

resource "aws_lambda_function" "api" {
  function_name = "${local.name}-api"
  role          = aws_iam_role.api.arn
  # Mismo criterio que la Lambda "motor": el modulo es "lambda.handler".
  handler     = "lambda.handler.lambda_handler"
  runtime     = local.python_runtime
  timeout     = 30
  memory_size = 512

  filename         = data.archive_file.motor.output_path
  source_code_hash = data.archive_file.motor.output_base64sha256

  environment {
    variables = {
      AWS_REGION      = var.aws_region
      FUNC_MOTOR_NAME = aws_lambda_function.motor.function_name
      BUCKET_DATOS    = aws_s3_bucket.datos.id
      TABLE_PRINCIPAL = aws_dynamodb_table.principal.name
      ENVIRONMENT     = var.environment
    }
  }

  tracing_config {
    mode = "Active"
  }

  depends_on = [
    aws_cloudwatch_log_group.api,
    aws_iam_role_policy.api,
  ]

  tags = local.tags
}

# ---------------------------------------------------------------------------
#  API Gateway — HTTP API (mas simple y barato que REST)
# ---------------------------------------------------------------------------

resource "aws_apigatewayv2_api" "api" {
  name          = "${local.name}-api"
  description   = "API del motor de decisiones financieras para autonomos y pymes de Andorra"
  protocol_type = "HTTP"

  cors_configuration {
    allow_origins = var.cors_allowed_origins
    allow_methods = ["GET", "POST", "OPTIONS"]
    allow_headers = ["Content-Type", "Authorization"]
    max_age       = 3600
  }

  tags = local.tags
}

resource "aws_apigatewayv2_integration" "api" {
  api_id                 = aws_apigatewayv2_api.api.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.api.invoke_arn
  integration_method     = "POST"
  payload_format_version = "2.0"
  timeout_milliseconds   = 29000
}

resource "aws_apigatewayv2_route" "preguntar" {
  api_id    = aws_apigatewayv2_api.api.id
  route_key = "POST /preguntar"
  target    = "integrations/${aws_apigatewayv2_integration.api.id}"
}

resource "aws_apigatewayv2_route" "salud" {
  api_id    = aws_apigatewayv2_api.api.id
  route_key = "GET /salud"
  target    = "integrations/${aws_apigatewayv2_integration.api.id}"
}

resource "aws_apigatewayv2_stage" "api" {
  api_id      = aws_apigatewayv2_api.api.id
  name        = "$default"
  auto_deploy = true
  tags        = local.tags
}

resource "aws_lambda_permission" "api_gateway" {
  statement_id  = "AllowExecutionFromAPIGateway"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.api.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.api.execution_arn}/*/*"
}

# ---------------------------------------------------------------------------
#  Cognito — autenticacion (el cliente es un autonomo, no un empleado)
# ---------------------------------------------------------------------------

resource "aws_cognito_user_pool" "usuarios" {
  name = "${local.name}-usuarios"

  auto_verified_attributes = ["email"]
  username_attributes      = ["email"]

  password_policy {
    minimum_length                   = 12
    require_lowercase                = true
    require_numbers                  = true
    require_symbols                  = true
    require_uppercase                = true
    temporary_password_validity_days = 3
  }

  mfa_configuration = "OPTIONAL"

  account_recovery_setting {
    recovery_mechanism {
      name     = "verified_email"
      priority = 1
    }
  }

  tags = local.tags
}

resource "aws_cognito_user_pool_client" "web" {
  name                                 = "${local.name}-web"
  user_pool_id                         = aws_cognito_user_pool.usuarios.id
  generate_secret                      = false
  explicit_auth_flows                  = ["ALLOW_USER_PASSWORD_AUTH", "ALLOW_REFRESH_TOKEN_AUTH"]
  supported_identity_providers         = ["COGNITO"]
  allowed_oauth_flows_user_pool_client = true
  callback_urls                        = var.cors_allowed_origins
  allowed_oauth_flows                  = ["code"]
  allowed_oauth_scopes                 = ["email", "openid", "profile"]
  # Validez de los tokens en HORAS (el provider las interpreta como horas).
  access_token_validity   = 1
  id_token_validity       = 1
  refresh_token_validity  = 720
  enable_token_revocation = true
}

resource "aws_cognito_user_pool_domain" "dominio" {
  # El prefijo de un dominio Cognito es GLOBAL: si otro equipo del hackathon
  # usa el mismo nombre de proyecto en esta region, el apply falla con
  # "Domain already exists" y no es recuperable sin destroy. Anadimos el id
  # de cuenta (igual que el bucket de S3) para que cada equipo tenga el suyo.
  domain       = "${local.name}-${local.bucket_suffix}.auth.${var.aws_region}.amazoncognito.com"
  user_pool_id = aws_cognito_user_pool.usuarios.id
}

# ---------------------------------------------------------------------------
#  CloudFront — el front estatico
# ---------------------------------------------------------------------------

resource "random_id" "suffix" {
  byte_length = 4
}

resource "aws_cloudfront_origin_access_control" "s3" {
  name                              = "${local.name}-oac"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

resource "aws_cloudfront_distribution" "web" {
  enabled             = true
  is_ipv6_enabled     = true
  comment             = "Front del motor de decisiones — ${local.name}"
  default_root_object = "index.html"
  price_class         = "PriceClass_100"

  aliases = var.environment == "prod" && var.dominio_principal != "" ? ["${local.name}.${var.dominio_principal}"] : []

  # Origen 1: el front estatico en S3
  origin {
    domain_name              = aws_s3_bucket.datos.bucket_regional_domain_name
    origin_id                = "s3-${aws_s3_bucket.datos.id}"
    origin_access_control_id = aws_cloudfront_origin_access_control.s3.id
  }

  # Origen 2: la API (comportamiento propio, sin cache)
  origin {
    domain_name = aws_apigatewayv2_api.api.api_endpoint
    origin_id   = "api-${aws_apigatewayv2_api.api.id}"

    custom_origin_config {
      origin_protocol_policy = "https-only"
      origin_ssl_protocols   = ["TLSv1.2"]
      http_port              = 80
      https_port             = 443
    }
  }

  # Front: cache corta en el html, larga en los assets versionados
  default_cache_behavior {
    target_origin_id       = "s3-${aws_s3_bucket.datos.id}"
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["GET", "HEAD", "OPTIONS"]
    cached_methods         = ["GET", "HEAD"]
    compress               = true

    forwarded_values {
      query_string = false
      cookies {
        forward = "none"
      }
    }

    min_ttl     = 0
    default_ttl = 60
    max_ttl     = 300
  }

  # API: nunca cacheada
  ordered_cache_behavior {
    path_pattern           = "/preguntar"
    target_origin_id       = "api-${aws_apigatewayv2_api.api.id}"
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["POST", "OPTIONS"]
    cached_methods         = []
    compress               = true

    forwarded_values {
      query_string = false
      headers      = ["Origin"]
      cookies {
        forward = "none"
      }
    }

    min_ttl     = 0
    default_ttl = 0
    max_ttl     = 0
  }

  ordered_cache_behavior {
    path_pattern           = "/salud"
    target_origin_id       = "api-${aws_apigatewayv2_api.api.id}"
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["GET", "HEAD", "OPTIONS"]
    cached_methods         = []
    compress               = true

    forwarded_values {
      query_string = false
      cookies {
        forward = "none"
      }
    }

    min_ttl     = 0
    default_ttl = 0
    max_ttl     = 0
  }

  custom_error_response {
    error_code         = 404
    response_code      = 200
    response_page_path = "/index.html"
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    cloudfront_default_certificate = true
  }

  tags = local.tags
}

variable "dominio_principal" {
  description = "Dominio principal (solo prod). Ej: app.morabanc-demo.ad"
  type        = string
  default     = ""
}

resource "aws_s3_bucket_policy" "front" {
  bucket = aws_s3_bucket.datos.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid    = "CloudFrontReadOnly"
      Effect = "Allow"
      Principal = {
        Service = "cloudfront.amazonaws.com"
      }
      Action   = "s3:GetObject"
      Resource = "${aws_s3_bucket.datos.arn}/*"
      Condition = {
        StringEquals = {
          "AWS:SourceArn" = aws_cloudfront_distribution.web.arn
        }
      }
    }]
  })
}

# ---------------------------------------------------------------------------
#  Bedrock Guardrails — bloquea advice financiero no permitido y PII
# ---------------------------------------------------------------------------

resource "aws_bedrock_guardrail" "principal" {
  count = var.enable_guardrails ? 1 : 0

  name                      = "${local.name}-guardrails"
  description               = "Filtra PII, prompt injection yAnswers fuera de politica en el agente"
  blocked_input_messaging   = "Lo siento, no puedo procesar esa solicitud porque incluye datos que no puedo tratar de esa forma."
  blocked_outputs_messaging = "Lo siento, no puedo dar ese tipo de asesoramiento financiero."

  content_policy_config {
    # Bedrock ofrece estos filtros de contenido. El "advice financiero no
    # permitido" lo cubrimos en la capa de sistema del agente (que prohibe
    # dar recomendaciones de inversion) y aqui filtramos lo que si es
    # controlable: inyeccion de prompts y contenido fuera de politica.
    filters_config {
      type            = "PROMPT_ATTACK"
      input_strength  = "HIGH"
      output_strength = "NONE"
    }

    filters_config {
      type            = "MISCONDUCT"
      input_strength  = "MEDIUM"
      output_strength = "MEDIUM"
    }

    filters_config {
      type            = "INSULTS"
      input_strength  = "LOW"
      output_strength = "LOW"
    }
  }

  sensitive_information_policy_config {
    # La accion se define por entidad (no hay input/output_strength aqui):
    # los datos sensibles se anonimizan y los secretos se bloquean.
    pii_entities_config {
      type   = "EMAIL"
      action = "ANONYMIZE"
    }

    pii_entities_config {
      type   = "PHONE"
      action = "ANONYMIZE"
    }

    pii_entities_config {
      type   = "CREDIT_DEBIT_CARD_NUMBER"
      action = "BLOCK"
    }

    pii_entities_config {
      type   = "AWS_SECRET_KEY"
      action = "BLOCK"
    }
  }

  tags = local.tags
}

# ---------------------------------------------------------------------------
#  Bedrock Knowledge Base — normativa andorrana (RAG)
# ---------------------------------------------------------------------------

resource "aws_bedrockagent_knowledge_base" "normativa" {
  count = var.bedrock_kb_id != "" ? 0 : 1

  name        = "${local.name}-kb"
  description = "Normativa fiscal andorrana (IRPF, IGI, CASS) y productos de MoraBanc"
  role_arn    = aws_iam_role.bedrock_kb[0].arn

  # La coleccion de OpenSearch Serverless tarda ~1-2 minutos en estar lista
  # para recibir indices. Si la KB se crea antes, el apply falla con un
  # error de coleccion no encontrada y hay que reintentar a mano.
  depends_on = [aws_opensearchserverless_collection.vector]

  knowledge_base_configuration {
    type = "VECTOR"

    vector_knowledge_base_configuration {
      embedding_model_arn = "arn:aws:bedrock:${var.aws_region}::foundation-model/amazon.titan-embed-text-v2:0"
    }
  }

  storage_configuration {
    type = "OPENSEARCH_SERVERLESS"

    opensearch_serverless_configuration {
      collection_arn    = aws_opensearchserverless_collection.vector[0].arn
      vector_index_name = "default"

      field_mapping {
        vector_field   = "bedrock-knowledge-base-default-vector"
        text_field     = "AMAZON_BEDROCK_TEXT_CHUNK"
        metadata_field = "AMAZON_BEDROCK_METADATA"
      }
    }
  }

  tags = local.tags
}

# El data source (los PDFs de normativa) va aparte: la KB es el indice,
# el data source es lo que se ingesta.
resource "aws_bedrockagent_data_source" "normativa" {
  count = var.bedrock_kb_id != "" ? 0 : 1

  name              = "${local.name}-normativa-s3"
  description       = "Normativa fiscal andorrana y productos MoraBanc desde S3"
  knowledge_base_id = aws_bedrockagent_knowledge_base.normativa[0].id

  # ORDEN CRITICO: el data source ingesta de S3, asi que los .md de
  # normativa/ tienen que estar SUBIDOS antes de que se cree. Sin esta
  # dependencia explicita Terraform no garantiza el orden y la KB indexa
  # un bucket vacio (y luego no se vuelve a indexar solo).
  depends_on = [aws_s3_object.normativa]

  data_source_configuration {
    type = "S3"

    s3_configuration {
      bucket_arn         = aws_s3_bucket.datos.arn
      inclusion_prefixes = ["normativa/"]
    }
  }

  vector_ingestion_configuration {
    chunking_configuration {
      chunking_strategy = "FIXED_SIZE"
    }

    parsing_configuration {
      parsing_strategy = "BEDROCK_FOUNDATION_MODEL"
    }
  }

  server_side_encryption_configuration {
    kms_key_arn = aws_kms_key.main.arn
  }
}

resource "aws_opensearchserverless_collection" "vector" {
  count = var.bedrock_kb_id != "" ? 0 : 1

  name = "${local.name}-vector"
  type = "VECTORSEARCH"

  tags = local.tags
}

data "aws_iam_policy_document" "bedrock_kb_assume" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["bedrock.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "bedrock_kb" {
  count = var.bedrock_kb_id != "" ? 0 : 1

  name               = "${local.name}-kb-role"
  assume_role_policy = data.aws_iam_policy_document.bedrock_kb_assume.json
  tags               = local.tags
}

resource "aws_iam_role_policy" "bedrock_kb" {
  count = var.bedrock_kb_id != "" ? 0 : 1

  name = "${local.name}-kb-policy"
  role = aws_iam_role.bedrock_kb[0].id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["aoss:APIAccessAll"]
        Resource = [aws_opensearchserverless_collection.vector[0].arn]
      },
      {
        Effect   = "Allow"
        Action   = ["bedrock:InvokeModel"]
        Resource = ["arn:aws:bedrock:${var.aws_region}::foundation-model/amazon.titan-embed-text-v2:0"]
      },
      {
        Effect   = "Allow"
        Action   = ["kms:Decrypt"]
        Resource = [aws_kms_key.main.arn]
      },
    ]
  })
}

# ---------------------------------------------------------------------------
#  Alarmas — si el motor falla, nos enteramos
# ---------------------------------------------------------------------------

resource "aws_cloudwatch_metric_alarm" "errores_motor" {
  alarm_name          = "${local.name}-errores-motor"
  alarm_description   = "Errores en la Lambda del motor"
  namespace           = "AWS/Lambda"
  metric_name         = "Errors"
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"

  dimensions = {
    FunctionName = aws_lambda_function.motor.function_name
  }

  alarm_actions = var.alert_email != "" ? [aws_sns_topic.alertas[0].arn] : []
}

resource "aws_sns_topic" "alertas" {
  count = var.alert_email != "" ? 1 : 0

  name = "${local.name}-alertas"
  tags = local.tags
}

resource "aws_sns_topic_subscription" "email" {
  count = var.alert_email != "" ? 1 : 0

  topic_arn = aws_sns_topic.alertas[0].arn
  protocol  = "email"
  endpoint  = var.alert_email
}

# ---------------------------------------------------------------------------
#  Corpus normativo — para la Knowledge Base (RAG)
# ---------------------------------------------------------------------------
# El corpus lo genera normativa/generar_corpus.py con los importes verificados
# contra BOPA, CASS y Govern d'Andorra. Se publica con el prefijo "normativa/"
# que es el que ingestiona el data source de Bedrock.
resource "aws_s3_object" "normativa" {
  for_each = fileset("${path.module}/../normativa", "*.md")

  bucket       = aws_s3_bucket.datos.id
  key          = "normativa/${each.value}"
  source       = "${path.module}/../normativa/${each.value}"
  etag         = filemd5("${path.module}/../normativa/${each.value}")
  content_type = "text/markdown; charset=utf-8"

  depends_on = [aws_s3_bucket_policy.front]
}

# ---------------------------------------------------------------------------
#  Front estatico — subida a S3 con cache-busting
# ---------------------------------------------------------------------------
# El front se sirve desde S3 via CloudFront. Cada fichero lleva su hash en el
# nombre para que el cache del navegador lo invalide al desplegar.
data "archive_file" "front" {
  type        = "zip"
  source_dir  = "${path.module}/../frontend"
  output_path = "${path.module}/.build/front.zip"
  excludes    = ["generar_demo_data.py", "__pycache__", "*.pyc"]
}

resource "aws_s3_object" "front" {
  for_each = fileset("${path.module}/../frontend", "**")

  bucket       = aws_s3_bucket.datos.id
  key          = each.value
  source       = "${path.module}/../frontend/${each.value}"
  etag         = filemd5("${path.module}/../frontend/${each.value}")
  content_type = lookup(local.content_types, each.value, "application/octet-stream")

  # El front se sirve con la politica de CloudFront.
  depends_on = [aws_s3_bucket_policy.front]
}

locals {
  content_types = {
    "index.html"                         = "text/html; charset=utf-8"
    "assets/styles.css"                  = "text/css; charset=utf-8"
    "assets/app.js"                      = "application/javascript; charset=utf-8"
    # El logo real de MoraBanc. Sin esto se publicaria como
    # application/octet-stream y el navegador NO lo renderiza como imagen:
    # el logo aparece roto en el movil.
    "assets/logo-morabanc.svg"           = "image/svg+xml"
    "data/demo_data.json"                = "application/json; charset=utf-8"
    "data/demo_freelance.csv"            = "text/csv; charset=utf-8"
    "data/demo_comercio.csv"             = "text/csv; charset=utf-8"
    "data/demo_freelancer_contratar.csv" = "text/csv; charset=utf-8"
    "data/demo_freelancer_cierre.csv"    = "text/csv; charset=utf-8"
  }
}

# NOTA sobre la invalidacion de cache:
# El provider hashicorp/aws no expone un recurso de invalidacion de
# CloudFront. El front se publica con TTL corto (60s) para el html y con
# el etag del fichero, de forma que un cambio se ve en menos de un minuto.
# Para invalidacion inmediata en produccion: aws cloudfront create-invalidation
# --distribution-id <id> --paths "/*"  (o usar el prefijo de version).

# ---------------------------------------------------------------------------
#  Salidas — para el README y el pitch
# ---------------------------------------------------------------------------

output "api_url" {
  description = "URL base de la API."
  value       = aws_apigatewayv2_stage.api.invoke_url
}

output "front_url" {
  description = "URL del front estatico."
  value       = "https://${aws_cloudfront_distribution.web.domain_name}"
}

output "cognito_user_pool_id" {
  description = "ID del user pool de Cognito."
  value       = aws_cognito_user_pool.usuarios.id
}

output "cognito_client_id" {
  description = "ID del client de Cognito para el front."
  value       = aws_cognito_user_pool_client.web.id
}

output "cognito_domain" {
  description = "Dominio de Cognito para el login del front."
  value       = aws_cognito_user_pool_domain.dominio.domain
}

output "bucket_datos" {
  description = "Bucket de extractos y corpus normativo."
  value       = aws_s3_bucket.datos.id
}

output "tabla_dynamodb" {
  description = "Tabla de movimientos y escenarios."
  value       = aws_dynamodb_table.principal.name
}

output "guardrail_id" {
  description = "ID del guardrail (si esta activo)."
  value       = var.enable_guardrails ? aws_bedrock_guardrail.principal[0].guardrail_id : "desactivado"
}

output "frontend_url_config" {
  description = "URL a configurar en el front."
  value = jsonencode({
    api_url          = aws_apigatewayv2_stage.api.invoke_url
    cognito_client   = aws_cognito_user_pool_client.web.id
    cognito_domain   = aws_cognito_user_pool_domain.dominio.domain
    region           = var.aws_region
    bucket_extractos = aws_s3_bucket.datos.id
  })
}
