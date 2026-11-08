#!/bin/bash
# Desplegar el motor local en el VPS.
#
# Uso: bash scripts/desplegar_motor_local.sh
#
# Sube el motor (engine/ y agent/), el servidor y el parche del nginx,
# y reinicia el servicio. Es idempotente.

set -euo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VPS="${VPS:-hvps}"
DIR_REMOTO=/var/www/morabanc-motor

echo "==> Subiendo el motor a ${VPS}:${DIR_REMOTO}"
ssh "$VPS" "mkdir -p ${DIR_REMOTO}"
scp -q -r "$RAIZ/engine" "$RAIZ/agent" "$VPS:${DIR_REMOTO}/"
scp -q "$RAIZ/scripts/motor_local.py" "$VPS:${DIR_REMOTO}/"

echo "==> Instalando el servicio"
scp -q "$RAIZ/scripts/morabanc-motor.service" "$VPS:/tmp/morabanc-motor.service"
ssh "$VPS" "sudo cp /tmp/morabanc-motor.service /etc/systemd/system/ && \
            sudo systemctl daemon-reload && \
            sudo systemctl enable --now morabanc-motor && \
            sudo systemctl restart morabanc-motor && \
            sleep 2 && systemctl is-active morabanc-motor"

echo "==> Comprobando"
ssh "$VPS" "curl -s -m 10 http://127.0.0.1:8811/salud"
echo
echo "Listo. La ruta /api/preguntar del nginx debe apuntar a 127.0.0.1:8811."
