#!/usr/bin/env bash
# Despliegue de la infraestructura AWS con Terraform.
#
# POR QUE EXISTE
#   El "terraform apply" del dia 7 crea 40 recursos en 4-6 minutos. Si algo
#   falla a mitad (y Bedrock/OpenSearch/Cognito fallan a menudo la primera
#   vez), el equipo se queda con la mitad de la infra y sin tiempo.
#
#   Este script:
#     1. valida la configuracion ANTES de crear nada
#     2. muestra el plan (se lee, como dice el DEPLOY.md)
#     3. aplica con reintentos, porque los fallos transitorios de AWS
#        (coleccion de OpenSearch que aun no esta lista, IAM que tarda en
#        propagarse) son normales la primera vez
#     4. comprueba que la API responde al final
#
# USO
#   bash scripts/deploy_infra.sh
#   bash scripts/deploy_infra.sh --plan-only    # solo el plan, no crea nada
#
# VARIABLES
#   AWS_PROFILE / AWS_ACCESS_KEY_ID...   credenciales (las da MoraBanc)
#   TF_REGION     region (por defecto us-east-1: la cuenta del hackathon
#                 solo permite crear recursos ahi)
#   TF_RETRIES    reintentos del apply (por defecto 3)
set -uo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$RAIZ/terraform"

REGION="${TF_REGION:-us-east-1}"
RETRIES="${TF_RETRIES:-3}"
PLAN_ONLY=0
[ "${1:-}" = "--plan-only" ] && PLAN_ONLY=1

# Terraform local si no esta en el PATH.
if command -v terraform >/dev/null 2>&1; then
  TF=terraform
elif [ -x /data/cache/scratch/tfbin/terraform ]; then
  TF=/data/cache/scratch/tfbin/terraform
else
  echo "ERROR: terraform no encontrado." >&2
  echo "  Instalalo: https://developer.hashicorp.com/terraform/downloads" >&2
  exit 2
fi

export AWS_DEFAULT_REGION="$REGION"
export AWS_REGION="$REGION"

echo "==> Despliegue de la infraestructura MoraBanc"
echo "    region:   $REGION"
echo "    proyecto: $(grep -oE 'project_name.*default.*=.*"[^"]*"' variables.tf 2>/dev/null | grep -oE '"[^"]*"$' || echo 'morabanc-hackathon')"

# --- 0. Credenciales -----------------------------------------------------
echo ""
echo "==> Comprobando credenciales"

# El mensaje de error importa: el fallo mas probable del dia 7 son las
# credenciales (expiradas, de la region equivocada, o sin sesion).
credenciales_validas() {
  if command -v aws >/dev/null 2>&1; then
    aws sts get-caller-identity >/dev/null 2>&1 && return 0
    return 1
  fi
  # Sin aws cli no se puede comprobar: se deja pasar y lo decide terraform.
  return 0
}

if ! credenciales_validas; then
  echo "ERROR: las credenciales de AWS no son validas." >&2
  echo "" >&2
  echo "Causas habituales:" >&2
  echo "  - La sesion expiro (las claves ASIA* del workshop duran minutos/horas)" >&2
  echo "  - Falta AWS_SESSION_TOKEN en una credencial temporal" >&2
  echo "  - La region no es la de la cuenta" >&2
  echo "" >&2
  echo "Las da MoraBanc (+376 884 884). Exporta:" >&2
  echo "  export AWS_ACCESS_KEY_ID=..." >&2
  echo "  export AWS_SECRET_ACCESS_KEY=..." >&2
  echo "  export AWS_SESSION_TOKEN=...   # si es sesion temporal" >&2
  echo "  export AWS_DEFAULT_REGION=$REGION" >&2
  echo "  unset AWS_REGION   # si esta a otra region, pisa el valor" >&2
  echo "" >&2
  echo "OJO: la cuenta del hackathon solo permite crear en us-east-1." >&2
  echo "En eu-west-1 todo falla con 'not authorized to perform'." >&2
  echo "" >&2
  echo "Diagnostico del fallo real:" >&2
  aws sts get-caller-identity 2>&1 | head -4 | sed 's/^/  /' >&2
  exit 2
fi

if command -v aws >/dev/null 2>&1; then
  ACCT=$(aws sts get-caller-identity --query Account --output text 2>/dev/null)
  ROLE=$(aws sts get-caller-identity --query Arn --output text 2>/dev/null | sed 's|.*/||')
  echo "    cuenta: $ACCT  ($ROLE)"
fi

# --- 1. Init -------------------------------------------------------------
echo ""
echo "==> terraform init"
"$TF" init -input=false 2>&1 | tail -3

# --- 2. Validate ---------------------------------------------------------
echo ""
echo "==> terraform validate"
if ! "$TF" validate; then
  echo "ERROR: la configuracion no es valida. NO se aplica nada." >&2
  exit 1
fi

# --- 3. Format check -----------------------------------------------------
if ! "$TF" fmt -check -recursive >/dev/null 2>&1; then
  echo "AVISO: hay ficheros .tf sin formatear. Corrigiendo..."
  "$TF" fmt -recursive
fi

# --- 4. Plan -------------------------------------------------------------
echo ""
echo "==> terraform plan (LEELO antes de aplicar)"
"$TF" plan -input=false -out=/tmp/morabanc.tfplan 2>&1 | tail -25

if [ "$PLAN_ONLY" = "1" ]; then
  echo ""
  echo "    (--plan-only: no se crea nada)"
  exit 0
fi

# --- 5. Apply con reintentos --------------------------------------------
echo ""
echo "==> terraform apply (hasta $RETRIES intentos)"

# El log del apply se guarda: hace falta para detectar si el fallo es de
# PERMISOS (falta de permiso en la cuenta) o transitorio (AWS propagando).
LOG_APPLY=/tmp/morabanc_apply.log

intento=1
while [ "$intento" -le "$RETRIES" ]; do
  echo ""
  echo "--- Intento $intento/$RETRIES ---"
  if "$TF" apply -input=false -auto-approve /tmp/morabanc.tfplan 2>&1 | tee "$LOG_APPLY" | tail -30; then
    echo ""
    echo "==> APLICADO"
    break
  fi
  echo ""
  echo "    el apply fallo (intento $intento/$RETRIES)"

  # --- Si el fallo es de permisos, reintentar sin las defensas opcionales --
  # La cuenta del workshop deniega explicitamente bedrock:TagResource y
  # aoss:CreateCollection. Guardrail y Knowledge Base son DEFENSAS: el
  # motor de decision y el RAG (ya opcional en el agente) funcionan sin
  # ellos. Es preferible desplegar el 90% que no desplegar nada.
  if grep -qE "not authorized to perform (bedrock:TagResource|aoss:CreateCollection|bedrock:CreateGuardrail)" "$LOG_APPLY" 2>/dev/null; then
    echo ""
    echo "    El fallo es de PERMISOS en la cuenta (no de codigo)."
    echo "    Reintentando sin el Guardrail y la Knowledge Base (opcionales)."
    echo ""
    "$TF" plan -input=false -out=/tmp/morabanc.tfplan \
      -var="enable_guardrails=false" -var="enable_kb=false" >/dev/null 2>&1
    if "$TF" apply -input=false -auto-approve /tmp/morabanc.tfplan 2>&1 | tee "$LOG_APPLY" | tail -20; then
      echo ""
      echo "==> APLICADO (sin Guardrail ni Knowledge Base: la cuenta no da permisos)"
      echo "    El motor y el RAG siguen funcionando; el RAG es opcional en el agente."
      break
    fi
    echo ""
    echo "    tambien fallo sin las defensas opcionales."
  fi

  if [ "$intento" -lt "$RETRIES" ]; then
    echo "    esperando 45 s y reintentando (AWS tarda en propagar IAM y OpenSearch)"
    sleep 45
    # Se regenera el plan: el estado puede haber cambiado (recursos a medias).
    "$TF" plan -input=false -out=/tmp/morabanc.tfplan >/dev/null 2>&1
  fi
  intento=$((intento + 1))
done

if [ "$intento" -gt "$RETRIES" ]; then
  echo ""
  echo "ERROR: el apply fallo $RETRIES veces. Ver DEPLOY.md, seccion 'Plan B'." >&2
  echo "" >&2
  echo "Lo que suele ser:" >&2
  grep -E "not authorized to perform|Error:" "$LOG_APPLY" 2>/dev/null | head -5 | sed 's/^/  /' >&2
  echo "" >&2
  echo "El modo demo local funciona sin AWS: no sacrifiques el motor por el cloud." >&2
  exit 1
fi

# --- 6. Outputs ----------------------------------------------------------
echo ""
echo "==> Outputs"
"$TF" output 2>&1

# --- 7. Verificacion -----------------------------------------------------
echo ""
echo "==> Verificando que la API responde"
API_URL=$("$TF" output -raw api_url 2>/dev/null || echo "")
# La API key vive dentro del output "frontend_url_config" (que es sensitive
# por eso). Se lee de ahi en vez de tener un output aparte.
API_KEY=$("$TF" output -json frontend_url_config 2>/dev/null | python3 -c "
import json, sys
try:
    print(json.load(sys.stdin).get('api_key', ''))
except Exception:
    print('')
" 2>/dev/null || echo "")
if [ -n "$API_URL" ]; then
  echo "    API: $API_URL"
  for i in $(seq 1 10); do
    if curl -sf "$API_URL/salud" >/dev/null 2>&1; then
      echo "    ✔ la API responde"
      curl -s "$API_URL/salud" | head -c 200; echo ""
      break
    fi
    [ "$i" = "10" ] && echo "    (aun no responde: la Lambda puede estar arrancando)"
    sleep 5
  done
else
  echo "    (sin api_url en los outputs)"
fi

# --- 8. Publicar el front ------------------------------------------------
echo ""
echo "==> Publicando el front con la config real"
cd "$RAIZ"
bash scripts/deploy_front.sh

echo ""
if [ "${FALLO:-0}" = "1" ]; then
  echo "==> Despliegue con INCIDENCIAS: revisa lo de arriba." >&2
  echo "    Front:  $("$TF" -chdir=terraform output -raw front_url 2>/dev/null || echo 'ver terraform output')"
  exit 1
fi
echo "==> LISTO"
echo "    Front:  $("$TF" -chdir=terraform output -raw front_url 2>/dev/null || echo 'ver terraform output')"
echo "    API:    $API_URL"
