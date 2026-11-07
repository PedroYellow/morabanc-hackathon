#!/usr/bin/env bash
# Despliegue del front en el VPS de Hostinger (welcomeandorra.com).
#
# QUE HACE
#   1. Regenera los datos demo con el motor real (Python) — el front NO
#      calcula nada, consume lo que genera el motor.
#   2. Sube el front estatico a /var/www/welcomeandorra en el servidor.
#   3. Crea/actualiza el vhost de nginx con HTTPS (Let's Encrypt).
#   4. Verifica que el sitio responde.
#
# USO
#   bash scripts/deploy_welcome.sh
#   bash scripts/deploy_welcome.sh --no-ssl    # sin certificado (solo HTTP)
#
# VARIABLES
#   DEPLOY_HOST   alias SSH del servidor (por defecto: hvps)
#   DEPLOY_ROOT   directorio en el servidor (por defecto: /var/www/welcomeandorra)
#   DOMAIN        dominio (por defecto: welcomeandorra.com)
#   API_URL       URL de la API en AWS. Si no se pone, el front queda en
#                 MODO DEMO (datos precalculados del motor, sin AWS).
#
# POR QUE EL DNS LO TIENE QUE CAMBIAR PEDRO
#   El dominio tiene que apuntar a la IP del servidor (179.197.243.234). El
#   nameserver es ns1/ns2.dns-parking.com (panel de Hostinger). Este script
#   NO toca el DNS: solo publica el front y deja el sitio sirviendo.
set -euo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$RAIZ"

DEPLOY_HOST="${DEPLOY_HOST:-hvps}"
DEPLOY_ROOT="${DEPLOY_ROOT:-/var/www/welcomeandorra}"
DOMAIN="${DOMAIN:-welcomeandorra.com}"
API_URL="${API_URL:-}"
API_KEY="${API_KEY:-}"
COGNITO_DOMAIN="${COGNITO_DOMAIN:-}"
COGNITO_CLIENT_ID="${COGNITO_CLIENT_ID:-}"
AWS_REGION="${AWS_REGION:-us-east-1}"
USE_SSL=1
[ "${1:-}" = "--no-ssl" ] && USE_SSL=0

# Si no se pasa API_URL a mano, se la pide a Terraform. Asi el front
# desplegado en el VPS queda con la API real (y la API key) sin que
# nadie tenga que acordarse de exportar variables.
#
# El output "frontend_url_config" es sensitive (lleva la API key), asi
# que se lee con -json. Si no hay Terraform, o no hay output todavia,
# el front se queda en MODO DEMO: que es valido y funciona.
if [ -z "$API_URL" ]; then
  TF_BIN="${TF_BIN:-terraform}"
  if command -v "$TF_BIN" >/dev/null 2>&1 || [ -x "$TF_BIN" ]; then
    if CFG_JSON=$("$TF_BIN" -chdir="$RAIZ/terraform" output -json frontend_url_config 2>/dev/null); then
      # El output es sensitive (lleva la API key), asi que se lee con -json.
      # OJO: el output "frontend_url_config" es sensitive, y Terraform lo
      # devuelve como un STRING JSON dentro del JSON ({"value": "{...}"}).
      # Por eso hay que desempaquetar dos veces: si lo que sale de json.load
      # es un string, se vuelve a parsear.
      #
      # Y OJO: aunque se parsee bien, la API key sale ENMASCARADA por el
      # CLI de Terraform ("0XRCHu...E4Y9"), porque el valor es sensitive.
      # Por eso la key se lee de la LAMBDA, que si la tiene en claro.
      eval "$(printf '%s' "$CFG_JSON" | python3 -c "
import json, shlex, sys
try:
    cfg = json.load(sys.stdin)
except Exception:
    sys.exit(0)
if isinstance(cfg, str):
    try:
        cfg = json.loads(cfg)
    except Exception:
        sys.exit(0)
if not isinstance(cfg, dict):
    sys.exit(0)
# OJO: los nombres son los del output "frontend_url_config":
# api_url, api_key, cognito_client (NO cognito_client_id), cognito_domain, region
for k in ('api_url', 'api_key', 'cognito_domain', 'cognito_client', 'region'):
    v = cfg.get(k) or ''
    if v:
        print(f'CFG_{k.upper()}={shlex.quote(str(v))}')
" 2>/dev/null)" || true
      # OJO: ${VAR:-} y no ${VAR-$X}: con "set -u", referenciar una variable
      # que no existe ABORTA el script ("unbound variable") y el despliegue
      # se queda a medias sin avisar.
      API_URL="${API_URL:-${CFG_API_URL:-}}"
      API_KEY="${API_KEY:-${CFG_API_KEY:-}}"
      COGNITO_DOMAIN="${COGNITO_DOMAIN:-${CFG_COGNITO_DOMAIN:-}}"
      COGNITO_CLIENT_ID="${COGNITO_CLIENT_ID:-${CFG_COGNITO_CLIENT:-}}"
      AWS_REGION="${AWS_REGION:-${CFG_REGION:-us-east-1}}"
      if [ -n "$API_URL" ]; then
        echo "    API detectada en terraform output: $API_URL"
      fi

      # La API key: terraform la enmascara (es sensitive), asi que se lee
      # del entorno de la Lambda, que si la tiene en claro.
      if [ -z "$API_KEY" ] || [ "$API_KEY" != "${API_KEY%%\.\.\.*}" ]; then
        _key_lambda=$(aws lambda get-function-configuration \
          --function-name "${FUNCION_API:-morabanc-hackathon-dev-api}" \
          --query 'Environment.Variables.API_KEY' --output text 2>/dev/null || true)
        if [ -n "$_key_lambda" ] && [ "$_key_lambda" != "None" ]; then
          API_KEY="$_key_lambda"
          echo "    API key leida de la Lambda (terraform la enmascara)"
        fi
      fi
      [ -n "$API_KEY" ] && echo "    API key presente (x-api-key)"
    fi
  fi
fi

echo "==> Despliegue en $DOMAIN"
echo "    servidor: $DEPLOY_HOST"
echo "    destino: $DEPLOY_ROOT"

# --- 1. Regenerar los datos demo con el motor real ------------------------
echo ""
echo "==> Regenerando los datos demo con el motor real (Python)"
python3 frontend/generar_demo_data.py

# --- 2. Inyectar la config de la API (si la hay) -------------------------
# IMPORTANTE: siempre se quita la config previa del index.html, haya API o
# no. Si no, al desplegar una vez con API y luego sin ella, el front se
# queda con la URL/API key viejas y el chat llama a un endpoint que ya no
# existe (o con una clave caducada).
#
# La API esta protegida con API key: el front tiene que enviar la clave
# en la cabecera x-api-key, o /preguntar responde 401.
#
# OJO: se inyecta la API key en el HTML del front. Es una clave de la
# cuenta del hackathon y solo controla la CUOTA de Bedrock, no datos
# sensibles. Para produccion, lo normal seria un token de sesion de
# Cognito en lugar de una clave estatica en el cliente.
# Siempre se limpia la config previa (idempotencia).
python3 <<'PY'
import re
p = "frontend/index.html"
s = open(p, encoding="utf-8").read()
s = re.sub(r"\n?<script>window\.__API_URL__=.*?</script>", "", s, flags=re.S)
open(p, "w", encoding="utf-8").write(s)
PY

if [ -n "$API_URL" ]; then
  echo ""
  echo "==> Inyectando la API: $API_URL"
  python3 - "$API_URL" "$API_KEY" "$COGNITO_DOMAIN" "$COGNITO_CLIENT_ID" "$AWS_REGION" <<'PY'
import json, re, sys
api_url, api_key, cognito_domain, cognito_client_id, region = sys.argv[1:6]
p = "frontend/index.html"
s = open(p, encoding="utf-8").read()
cfg = ('<script>window.__API_URL__=%s;window.__API_KEY__=%s;'
       'window.__COGNITO_DOMAIN__=%s;window.__COGNITO_CLIENT_ID__=%s;'
       'window.__AWS_REGION__=%s;</script>'
       % (json.dumps(api_url), json.dumps(api_key),
          json.dumps(cognito_domain), json.dumps(cognito_client_id),
          json.dumps(region)))
marker = '<script src="assets/app.js"></script>'
assert marker in s, "no se encontro el marker app.js"
open(p, "w", encoding="utf-8").write(s.replace(marker, cfg + "\n" + marker))
print("    config inyectada")
PY
else
  echo ""
  echo "    (sin API_URL: el front queda en MODO DEMO, que es una demo valida)"
fi

# --- 3. Subir los ficheros ------------------------------------------------
echo ""
echo "==> Subiendo el front al servidor"
# rsync preserva permisos y borra lo que ya no existe (-delete).
# Se excluye generar_demo_data.py (no es del front) y los ficheros de test.
ssh "$DEPLOY_HOST" "mkdir -p '$DEPLOY_ROOT/assets' '$DEPLOY_ROOT/data' '$DEPLOY_ROOT/.well-known/acme-challenge'"

for f in index.html; do
  scp -q "frontend/$f" "$DEPLOY_HOST:$DEPLOY_ROOT/$f"
  echo "    $f"
done
for f in frontend/assets/*; do
  scp -q "$f" "$DEPLOY_HOST:$DEPLOY_ROOT/assets/$(basename "$f")"
  echo "    assets/$(basename "$f")"
done
for f in frontend/data/*; do
  base=$(basename "$f")
  [ "$base" = "generar_demo_data.py" ] && continue
  scp -q "$f" "$DEPLOY_HOST:$DEPLOY_ROOT/data/$base"
  echo "    data/$base"
done

ssh "$DEPLOY_HOST" "chown -R www-data:www-data '$DEPLOY_ROOT' && chmod -R 755 '$DEPLOY_ROOT'"

# --- 4. vhost de nginx ---------------------------------------------------
echo ""
echo "==> Configurando nginx"
cat > /tmp/welcome_vhost.conf <<EOF
server {
    listen 80;
    listen [::]:80;
    server_name $DOMAIN www.$DOMAIN;

    root $DEPLOY_ROOT;
    index index.html;
    charset utf-8;

    # ACME HTTP-01 challenge (para el certificado)
    location ^~ /.well-known/acme-challenge/ {
        root $DEPLOY_ROOT;
        default_type "text/plain";
        allow all;
    }

    location / {
        try_files \$uri \$uri/ =404;
    }

    # Cache: el HTML se relee siempre, los assets se cachean poco (el front
    # se actualiza justo antes del pitch).
    location ~* \.(css|js|svg)$ {
        expires 5m;
        add_header Cache-Control "public, max-age=300";
    }

    location ~* \.json$ {
        expires 5m;
        add_header Cache-Control "public, max-age=300";
        default_type "application/json; charset=utf-8";
    }

    # Los CSV de los extractos de demo: sin esto salen como
    # application/octet-stream y el navegador no los lee bien.
    location ~* \.csv$ {
        expires 5m;
        add_header Cache-Control "public, max-age=300";
        default_type "text/csv; charset=utf-8";
    }

    location = /index.html {
        add_header Cache-Control "no-cache, must-revalidate";
    }

    gzip on;
    gzip_types text/css application/javascript application/json image/svg+xml;
    gzip_min_length 512;
}
EOF
scp -q /tmp/welcome_vhost.conf "$DEPLOY_HOST:/etc/nginx/sites-available/welcomeandorra.conf"
ssh "$DEPLOY_HOST" "
  ln -sf /etc/nginx/sites-available/welcomeandorra.conf /etc/nginx/sites-enabled/welcomeandorra.conf
  nginx -t 2>&1 | tail -2
  systemctl reload nginx
"
rm -f /tmp/welcome_vhost.conf

# --- 5. Certificado HTTPS ------------------------------------------------
if [ "$USE_SSL" = "1" ]; then
  echo ""
  echo "==> Certificado HTTPS (Let's Encrypt)"
  # Solo se puede emitir si el dominio ya apunta a este servidor. Si el DNS
  # aun no esta cambiado, se avisa y se sigue con HTTP.
  # La IP del servidor: la publica del enlace, no la de loopback. hostname -I
  # puede devolver varias (IPv6 primero), asi que se filtra la IPv4.
  IP_SERV=$(ssh "$DEPLOY_HOST" "ip -4 addr show scope global | awk '/inet/{print \$2}' | cut -d/ -f1 | head -1")
  IP_DNS=$(python3 - <<'PY'
import socket
try:
    print(socket.gethostbyname("welcomeandorra.com"))
except Exception:
    print("")
PY
)
  echo "    servidor: $IP_SERV · DNS: ${IP_DNS:-sin resolver}"
  if [ "$IP_SERV" = "$IP_DNS" ]; then
    ssh "$DEPLOY_HOST" "
      certbot --nginx -d $DOMAIN -d www.$DOMAIN \
        --non-interactive --agree-tos \
        --register-unsafely-without-email --redirect 2>&1 | tail -4
    "
  else
    echo "    AVISO: el DNS aun no apunta a este servidor (DNS=$IP_DNS, servidor=$IP_SERV)."
    echo "    Cambia el A record de $DOMAIN a $IP_SERV y luego ejecuta:"
    echo "      bash scripts/deploy_welcome.sh"
    echo "    El sitio funciona por HTTP mientras tanto."
  fi
fi

# --- 6. Verificar ---------------------------------------------------------
echo ""
echo "==> Verificando"
sleep 2
CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 20 "http://$DOMAIN/" 2>/dev/null || echo "000")
echo "    http://$DOMAIN/ -> HTTP $CODE"

# Si el DNS aun no apunta al servidor, se verifica por IP con el Host header:
# es exactamente lo que veria el navegador cuando se corrija el DNS.
if [ "$CODE" != "200" ]; then
  IP_SERV=$(ssh "$DEPLOY_HOST" "ip -4 addr show scope global | awk '/inet/{print \$2}' | cut -d/ -f1 | head -1")
  CODE_IP=$(curl -s -H "Host: $DOMAIN" -o /dev/null -w "%{http_code}" --max-time 20 "http://$IP_SERV/" 2>/dev/null || echo "000")
  echo "    http://$IP_SERV/ (Host: $DOMAIN) -> HTTP $CODE_IP"
  if [ "$CODE_IP" = "200" ]; then
    echo "    -> el vhost funciona. Solo falta el A record: $DOMAIN -> $IP_SERV"
  fi
  CODE="$CODE_IP"
fi

if [ "$CODE" = "200" ]; then
  echo ""
  echo "    CONTENIDO:"
  curl -s --max-time 20 "http://$DOMAIN/" | grep -oE "<title>[^<]*</title>" | sed 's/^/      /'
  curl -s --max-time 20 "http://$DOMAIN/" | grep -oE 'logo-morabanc\.svg' | head -1 | sed 's/^/      logo: /'
  if [ "$USE_SSL" = "1" ] && [ "$CODE" = "200" ]; then
    CODE_S=$(curl -s -o /dev/null -w "%{http_code}" --max-time 20 "https://$DOMAIN/" 2>/dev/null || echo "000")
    echo "    https://$DOMAIN/ -> HTTP $CODE_S"
  fi
fi

echo ""
echo "==> Hecho."
