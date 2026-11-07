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
print(cfg.get('api_url', ''),
      cfg.get('cognito_domain', ''),
      cfg.get('cognito_client', ''),
      cfg.get('region', 'eu-west-1'),
      cfg.get('api_key', ''))
" "$CFG_JSON")
EOF
    echo "    API:      $API_URL"
    echo "    Cognito:  ${COGNITO_DOMAIN:-<sin dominio>} / ${COGNITO_CLIENT_ID:-<sin client id>}"
    echo "    Region:   $AWS_REGION"
    [ -n "$API_KEY" ] && echo "    API key:  ${API_KEY:0:4}... (inyectada en el front)"
    python3 - "$API_URL" "$COGNITO_DOMAIN" "$COGNITO_CLIENT_ID" "$AWS_REGION" "$API_KEY" <<'PY'
import json, re, sys
api_url, cognito_domain, cognito_client_id, region, api_key = sys.argv[1:6]
path = "frontend/index.html"
s = open(path, encoding="utf-8").read()

# Inyeccion IDEMPOTENTE: quitamos cualquier config previa antes de inyectar,
# para que ejecutar el script dos veces no duplique la linea.
s = re.sub(r"\n?<script>window\.__API_URL__=.*?</script>", "", s, flags=re.S)

cfg = ('<script>window.__API_URL__=%s;window.__API_KEY__=%s;'
       'window.__COGNITO_DOMAIN__=%s;'
       'window.__COGNITO_CLIENT_ID__=%s;window.__AWS_REGION__=%s;</script>'
       % (json.dumps(api_url), json.dumps(api_key), json.dumps(cognito_domain),
          json.dumps(cognito_client_id), json.dumps(region)))

marker = '<script src="assets/app.js"></script>'
if marker not in s:
    print("ERROR: no se encontro el marker app.js en index.html", file=sys.stderr)
    sys.exit(1)
s = s.replace(marker, cfg + "\n" + marker)
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
for f in index.html assets/app.js assets/styles.css data/demo_data.json; do
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
    aws s3 sync frontend/ "s3://$BUCKET/" --exclude "generar_demo_data.py" --delete
    echo "    publicado en s3://$BUCKET/"
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
