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
#   El dominio tiene que apuntar a la IP del servidor (187.127.64.126). El
#   nameserver es ns1/ns2.dns-parking.com (panel de Hostinger). Este script
#   NO toca el DNS: solo publica el front y deja el sitio sirviendo.
set -euo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$RAIZ"

DEPLOY_HOST="${DEPLOY_HOST:-hvps}"
DEPLOY_ROOT="${DEPLOY_ROOT:-/var/www/welcomeandorra}"
DOMAIN="${DOMAIN:-welcomeandorra.com}"
API_URL="${API_URL:-}"
USE_SSL=1
[ "${1:-}" = "--no-ssl" ] && USE_SSL=0

echo "==> Despliegue en $DOMAIN"
echo "    servidor: $DEPLOY_HOST"
echo "    destino: $DEPLOY_ROOT"

# --- 1. Regenerar los datos demo con el motor real ------------------------
echo ""
echo "==> Regenerando los datos demo con el motor real (Python)"
python3 frontend/generar_demo_data.py

# --- 2. Inyectar la config de la API (si la hay) -------------------------
if [ -n "$API_URL" ]; then
  echo ""
  echo "==> Inyectando la API: $API_URL"
  python3 - "$API_URL" <<'PY'
import json, re, sys
api_url = sys.argv[1]
p = "frontend/index.html"
s = open(p, encoding="utf-8").read()
# Idempotente: quita cualquier config previa antes de inyectar.
s = re.sub(r"\n?<script>window\.__API_URL__=.*?</script>", "", s, flags=re.S)
cfg = ('<script>window.__API_URL__=%s;window.__COGNITO_DOMAIN__=%s;'
       'window.__COGNITO_CLIENT_ID__=%s;window.__AWS_REGION__=%s;</script>'
       % (json.dumps(api_url), json.dumps(""), json.dumps(""), json.dumps("eu-west-1")))
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
