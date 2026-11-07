#!/usr/bin/env bash
# Espera al cambio de DNS y emite el certificado HTTPS automaticamente.
#
# POR QUE EXISTE
#   Let's Encrypt valida el dominio resolvinglo desde internet: si el A record
#   sigue apuntando a la IP antigua, el CA no puede descargar el challenge y
#   la emision falla (no es un problema de configuracion). Por eso el
#   certificado solo se puede emitir DESPUES de cambiar el DNS.
#
#   Este script se queda mirando el DNS y, en cuanto apunta al servidor,
#   emite el certificado, configura el HTTPS y verifica el sitio.
#
# USO
#   bash scripts/wait_dns_and_https.sh              # espera hasta 60 min
#   bash scripts/wait_dns_and_https.sh --timeout 30 # espera 30 minutos
#   bash scripts/wait_dns_and_https.sh --check      # solo comprueba el estado
#
# SE PUEDE DEJAR EN SEGUNDO PLANO
#   nohup bash scripts/wait_dns_and_https.sh > /tmp/https.log 2>&1 &
set -uo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$RAIZ"

DEPLOY_HOST="${DEPLOY_HOST:-hvps}"
DEPLOY_ROOT="${DEPLOY_ROOT:-/var/www/welcomeandorra}"
DOMAIN="${DOMAIN:-welcomeandorra.com}"
TIMEOUT_MIN="${TIMEOUT_MIN:-60}"
SOLO_CHECK=0
[ "${1:-}" = "--check" ] && SOLO_CHECK=1

for arg in "$@"; do
  case "$arg" in
    --timeout) shift ;;
    --timeout=*) TIMEOUT_MIN="${arg#*=}";;
  esac
done

IP_SERV=$(ssh "$DEPLOY_HOST" "ip -4 addr show scope global | awk '/inet/{print \$2}' | cut -d/ -f1 | head -1")
echo "==> Esperando el DNS de $DOMAIN"
echo "    servidor: $IP_SERV"

dns_ip() {
  python3 - <<PY
import socket
try:
    print(socket.gethostbyname("$DOMAIN"))
except Exception:
    print("")
PY
}

# --- Comprobacion inmediata -------------------------------------------------
CURRENT=$(dns_ip)
if [ "$CURRENT" = "$IP_SERV" ]; then
  echo "    el DNS ya apunta al servidor ($CURRENT)"
else
  echo "    DNS actual: ${CURRENT:-sin resolver}"
  echo "    esperado:   $IP_SERV"
  echo ""
  echo "    Cambia en Hostinger -> DNS:"
  echo "      A  @    $IP_SERV"
  echo "      A  www  $IP_SERV"
  echo ""
fi

if [ "$SOLO_CHECK" = "1" ]; then
  if [ "$CURRENT" = "$IP_SERV" ]; then
    echo "==> El DNS esta bien. Ejecuta: bash scripts/deploy_welcome.sh"
  else
    echo "==> Todavia falta cambiar el DNS."
  fi
  exit 0
fi

# --- Espera activa ---------------------------------------------------------
INICIO=$(date +%s)
FIN=$((INICIO + TIMEOUT_MIN * 60))
intentos=0

while [ "$(date +%s)" -lt "$FIN" ]; do
  CURRENT=$(dns_ip)
  intentos=$((intentos + 1))

  if [ "$CURRENT" = "$IP_SERV" ]; then
    echo ""
    echo "==> DNS propagado ($CURRENT). Emitiendo el certificado..."
    sleep 20   # margen para que el ACME de Let's Encrypt resuelva tambien

    ssh "$DEPLOY_HOST" "
      certbot certonly --webroot -w '$DEPLOY_ROOT' \
        -d '$DOMAIN' -d 'www.$DOMAIN' \
        --non-interactive --agree-tos \
        --register-unsafely-without-email --keep-until-expiring 2>&1 | tail -6
    "

    if ssh "$DEPLOY_HOST" "test -f /etc/letsencrypt/live/$DOMAIN/fullchain.pem"; then
      echo ""
      echo "==> Certificado emitido. Configurando HTTPS en nginx..."
      bash scripts/deploy_welcome.sh
      echo ""
      echo "==> HTTPS listo:  https://$DOMAIN"
      exit 0
    fi

    echo ""
    echo "AVISO: el certificado no se emitio. Revisa:"
    echo "  ssh $DEPLOY_HOST 'certbot certonly --webroot -w $DEPLOY_ROOT -d $DOMAIN -d www.$DOMAIN'"
    exit 1
  fi

  # Comprobacion cada 30 s, con un resumen cada 10 intentos (5 min)
  if [ $((intentos % 10)) -eq 0 ]; then
    echo "    ... ${CURRENT:-sin resolver} (min $(($(date +%s) - INICIO))s)"
  fi
  sleep 30
done

echo ""
echo "==> Timeout: el DNS no ha cambiado en $TIMEOUT_MIN minutos."
echo "    Estado actual: ${CURRENT:-sin resolver} (servidor: $IP_SERV)"
echo "    Cuando lo cambies, ejecuta: bash scripts/deploy_welcome.sh"
exit 1
