#!/usr/bin/env bash
# Espera a que el DNS de welcomeandorra.com apunte al VPS y entonces
# publica el front y emite el certificado HTTPS.
#
# POR QUE ESTE SCRIPT
#   La API de Hostinger devuelve "530 / error code: 1016" desde el
#   entorno del hackathon (el WAF bloquea por IP de origen), asi que el
#   cambio del A record lo tiene que hacer Pedro en el panel. Este
#   script se queda esperando y, en cuanto el DNS propaga, hace el resto
#   solo: subir el front, configurar nginx y emitir el certificado.
#
# USO
#   bash scripts/esperar_dns.sh              # espera hasta 30 min
#   bash scripts/esperar_dns.sh 60           # espera hasta 60 min
set -uo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$RAIZ"

DOMAIN="${DOMAIN:-welcomeandorra.com}"
MINUTOS="${1:-30}"
INTERVALO=20
IP_ESPERADA="${IP_ESPERADA:-}"

echo "==> Esperando a que $DOMAIN apunte al VPS (hasta $MINUTOS min)"
echo "    Objetivo: el registro A debe coincidir con la IP del servidor."
echo "    Ctrl+C para salir; el despliegue se puede lanzar despues a mano."
echo ""

IP_SERV=$(ssh "${DEPLOY_HOST:-hvps}" "ip -4 addr show scope global | awk '/inet/{print \$2}' | cut -d/ -f1 | head -1" 2>/dev/null || echo "")
if [ -z "$IP_SERV" ]; then
  echo "ERROR: no se pudo Averiguar la IP del servidor por SSH." >&2
  exit 1
fi
[ -n "$IP_ESPERADA" ] || IP_ESPERADA="$IP_SERV"
echo "    IP del servidor: $IP_SERV"

# Cuantas veces se ha visto cada IP, para no descartar un cambio que aun
# se este propagando entre varios servidores DNS.
declare -A VISTOS
FIN=$(( $(date +%s) + MINUTOS * 60 ))
intentos=0

while [ "$(date +%s)" -lt "$FIN" ]; do
  intentos=$((intentos + 1))
  IP_DNS=$(python3 - "$DOMAIN" <<'PY'
import json, sys, urllib.request
domain = sys.argv[1]
try:
    url = f"https://dns.google/resolve?name={domain}&type=A"
    with urllib.request.urlopen(url, timeout=15) as r:
        d = json.load(r)
    for a in d.get("Answer", []):
        if a.get("type") == 1:
            print(a["data"])
            break
except Exception:
    pass
PY
)
  if [ -n "$IP_DNS" ]; then
    VISTOS["$IP_DNS"]=$(( ${VISTOS["$IP_DNS"]:-0} + 1 ))
    echo "    [$intentos] $DOMAIN -> $IP_DNS   (servidor: $IP_SERV)"
    if [ "$IP_DNS" = "$IP_ESPERADA" ]; then
      echo ""
      echo "==> El DNS ya apunta al servidor. Desplegando."
      echo ""
      bash scripts/deploy_welcome.sh
      echo ""
      echo "==> Comprobacion final:"
      curl -sI --max-time 20 "https://$DOMAIN/" | head -3
      exit 0
    fi
  else
    echo "    [$intentos] $DOMAIN -> sin registro A todavia"
  fi
  sleep "$INTERVALO"
done

echo ""
echo "El DNS todavia no apunta a $IP_ESPERADA. Estado actual:"
for ip in "${!VISTOS[@]}"; do echo "  $ip (visto ${VISTOS[$ip]} veces)"; done
echo ""
echo "En el panel de Hostinger: DNS de $DOMAIN -> registro A de '@' -> $IP_ESPERADA"
exit 1
