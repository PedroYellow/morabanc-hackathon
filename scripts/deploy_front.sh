#!/usr/bin/env bash
# Despliegue del front a S3 + configuracion de la API.
#
# En el hackathon, el proyecto se despliega con `terraform apply`, que ya
# publica el front (aws_s3_object sobre los ficheros del directorio frontend/).
# Este script sirve para:
#   1. regenerar los datos demo con el motor real
#   2. comprobar que todo esta listo
#   3. opcionalmente, publicar solo el front si ya se aplico el terraform
set -euo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$RAIZ"

echo "==> Regenerando los datos demo con el motor real (Python)"
python3 frontend/generar_demo_data.py

echo ""
echo "==> Inyectando la configuracion de la API en el front"

# Los valores vienen de `terraform output -json frontend_url_config`.
# Si no hay terraform aplicado, el front funciona en MODO DEMO (datos
# precalculados), que es lo que se usa en el pitch sin credenciales.
if command -v terraform >/dev/null 2>&1; then
  if CFG_JSON=$(terraform -chdir=terraform output -json frontend_url_config 2>/dev/null); then
    # Leemos TODOS los valores del output de una vez. Ojo: las claves son
    # api_url / cognito_client / cognito_domain / region (las define
    # terraform/main.tf en el output "frontend_url_config").
    read -r API_URL COGNITO_DOMAIN COGNITO_CLIENT_ID AWS_REGION API_KEY <<EOF
$(python3 -c "
import json, sys
cfg = json.loads(sys.argv[1])
# OJO: el output es sensitive, asi que Terraform lo devuelve como un STRING
# JSON dentro del JSON. Hay que desempaquetar dos veces o esto falla con
# 'str object has no attribute get'.
if isinstance(cfg, str):
    cfg = json.loads(cfg)
print(cfg.get('api_url', ''),
      cfg.get('cognito_domain', ''),
      cfg.get('cognito_client', ''),
      cfg.get('region', 'us-east-1'),
      cfg.get('api_key', ''))
" "$CFG_JSON")
EOF
    echo "    API:      $API_URL"
    echo "    Cognito:  ${COGNITO_DOMAIN:-<sin dominio>} / ${COGNITO_CLIENT_ID:-<sin client id>}"
    echo "    Region:   $AWS_REGION"
    # La API key NO se inyecta en el front: la CloudFront Function
    # "mora-inject-api-key" la anade en el edge, en las rutas /api/*.
    # Asi la clave nunca se descarga en el navegador.
    echo "    API key:  la anade la CloudFront Function en el edge (no va en el bundle)"
    python3 - "$COGNITO_DOMAIN" "$COGNITO_CLIENT_ID" "$AWS_REGION" <<'PY'
import json, re, sys
cognito_domain, cognito_client_id, region = sys.argv[1:4]
path = "frontend/index.html"
s = open(path, encoding="utf-8").read()

# Inyeccion IDEMPOTENTE: quitamos cualquier config previa antes de inyectar,
# para que ejecutar el script dos veces no duplique la linea.
s = re.sub(r"\n?<script>window\.__API_URL__=.*?</script>", "", s, flags=re.S)

cfg = ('<script>window.__API_URL__="/api";window.__API_KEY__="";'
       'window.__COGNITO_DOMAIN__=%s;'
       'window.__COGNITO_CLIENT_ID__=%s;window.__AWS_REGION__=%s;</script>'
       % (json.dumps(cognito_domain),
          json.dumps(cognito_client_id), json.dumps(region)))

# El marcador tiene que tolerar el versionado de assets (?v=...) que se
# usa para que un despliegue se vea al instante y no 5 minutos despues
# por la cache de CloudFront/nginx.
marker = re.search(r'<script src="assets/app\.js(?:\?[^"]*)?"></script>', s)
if not marker:
    print("ERROR: no se encontro el marker app.js en index.html", file=sys.stderr)
    sys.exit(1)
s = s.replace(marker.group(0), cfg + "\n" + marker.group(0))
open(path, "w", encoding="utf-8").write(s)
print("    config inyectada en index.html")
PY
  else
    echo "    (terraform aun sin aplicar: el front queda en MODO DEMO)"
  fi
else
  echo "    (terraform no instalado: el front queda en MODO DEMO)"
fi

echo ""
echo "==> Comprobando el front"
for f in index.html assets/app.js assets/styles.css data/demo_data.json \
         mb-login.html mb-empresas.html \
         assets/mb-portal.js assets/mb-portal.css \
         assets/mb-login.js assets/mb-login.css \
         data/mb_escenarios.json; do
  if [ -f "frontend/$f" ]; then
    printf "    OK  %-26s %8d bytes\n" "$f" "$(stat -c%s "frontend/$f")"
  else
    echo "    FALTA  $f"; exit 1
  fi
done

echo ""
echo "==> Publicando el front con aws s3 sync (opcional)"
if command -v aws >/dev/null 2>&1 && aws sts get-caller-identity >/dev/null 2>&1; then
  BUCKET=$(terraform -chdir=terraform output -raw bucket_datos 2>/dev/null || echo "")
  if [ -n "$BUCKET" ]; then
    # OJO: --delete borra lo que no este en frontend/. El corpus
    # NORMATIVO (normativa/*.md) lo publica terraform en el mismo bucket
    # y lo necesita la Knowledge Base de Bedrock: si se borra, el RAG se
    # queda sin normativa. Por eso se excluye.
    #
    # Tambien se excluye assets/mb/ (recursos de la web de MoraBanc que
    # se pueden subir aparte).
    #
    # El portal de empresas (mb-login.html, mb-empresas.html,
    # assets/mb-portal.*, assets/mb-login.*, data/mb_escenarios.json)
    # SI se publica: son parte del front.
    # OJO: aws s3 sync NO infiere el Content-Type. Sin --content-type,
    # los .html y .js se quedan como application/octet-stream y el
    # navegador los DESCARGA en vez de mostrarlos (por eso el portal
    # de empresas se abria como descarga y no como pagina).
    # Por eso se sube fichero a fichero con su tipo.
    python3 scripts/sync_front_s3.py "$BUCKET"
    echo "    publicado en s3://$BUCKET/"

    # La CloudFront Function se queda en stage DEVELOPMENT si no se
    # publica. Sin publicar, no inyecta la x-api-key y la API
    # responde 403. Terraform no lo hace solo.
    FN_ETAG=$(aws cloudfront describe-function --name mora-inject-api-key \
                 --query ETag --output text 2>/dev/null || true)
    if [ -n "$FN_ETAG" ] && [ "$FN_ETAG" != "None" ]; then
      aws cloudfront publish-function --name mora-inject-api-key \
        --if-match "$FN_ETAG" >/dev/null 2>&1 && \
        echo "    CloudFront Function publicada (LIVE)" || \
        echo "    AVISO: no se pudo publicar la CloudFront Function"
    fi

    # Invalidar la cache de CloudFront: si no, el front servido sigue
    # siendo el anterior durante hasta 5 minutos.
    DIST_ID=$(terraform -chdir=terraform output -raw cloudfront_distribution_id 2>/dev/null || echo "")
    if [ -n "$DIST_ID" ] && [ "$DIST_ID" != "" ]; then
      aws cloudfront create-invalidation --distribution-id "$DIST_ID" \
        --paths "/*" >/dev/null 2>&1 && \
        echo "    cache de CloudFront invalidada" || true
    fi
  fi
else
  echo "    (sin credenciales AWS: se publica con terraform apply)"
fi

echo ""
echo "==> Verificando el modo del front"

if grep -q "__API_URL__" frontend/index.html 2>/dev/null && \
   grep -q 'window.__API_URL__=""' frontend/index.html 2>/dev/null; then
  echo "    MODO DEMO — el front usa data/demo_data.json (datos del motor real)."
  echo "    Para el modo real: terraform apply y luego vuelve a ejecutar este script."
else
  echo "    MODO REAL — el front llama a la API en AWS."
fi

if grep -q "window.__API_URL__" frontend/index.html 2>/dev/null; then
  API_INJ=$(grep -o 'window.__API_URL__="[^"]*"' frontend/index.html | head -1)
  echo "    ${API_INJ}"
fi

echo ""
echo "Front listo."
