#!/usr/bin/env bash
# Sincroniza el repo maestro (GitHub) con el GitLab de MoraBanc.
#
# POR QUE EXISTE
#   Las bases del hackathon dicen que el codigo debe ir al espacio/proyecto
#   que crea MoraBanc en GitLab. No es un detalle: "el incumplimiento podra
#   dar lugar a la descalificacion". GitHub es donde trabajamos; GitLab es
#   donde hay que entregar. Este script mantiene los dos sincronizados.
#
# USO
#   GITLAB_REMOTE=git@gitlab.com:morabanc/equipo-ia-finanzas.git \
#   bash scripts/sync_gitlab.sh
#
#   o, si ya existe el remote:
#   bash scripts/sync_gitlab.sh
#
# VARIABLES
#   GITLAB_REMOTE   URL del repo GitLab de MoraBanc (sin .git o con .git)
#   GITLAB_BRANCH   rama destino (por defecto: la rama actual)
#   DRY_RUN=1       muestra lo que haria sin tocar nada
set -euo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$RAIZ"

GITLAB_REMOTE="${GITLAB_REMOTE:-}"
GITLAB_BRANCH="${GITLAB_BRANCH:-$(git rev-parse --abbrev-ref HEAD)}"
DRY_RUN="${DRY_RUN:-0}"

echo "==> Sincronizando con el GitLab de MoraBanc"
echo "    repo:    $RAIZ"
echo "    destino: ${GITLAB_REMOTE:-<sin configurar>} (rama $GITLAB_BRANCH)"

if [ -z "$GITLAB_REMOTE" ]; then
  echo ""
  echo "ERROR: falta GITLAB_REMOTE." >&2
  echo "  Ejemplo:" >&2
  echo "    GITLAB_REMOTE=git@gitlab.com:<grupo>/<proyecto>.git bash scripts/sync_gitlab.sh" >&2
  echo "" >&2
  echo "El acceso al GitLab de MoraBanc se pide a la organizacion (+376 884 884)." >&2
  echo "Es un requisito de descalificacion, no un detalle: preguntadlo el dia 7 a primera hora." >&2
  exit 2
fi

# --- Estado del repo: solo sincronizar si la suite esta verde -------------
echo ""
echo "==> Verificando que la suite pasa antes de publicar"
if bash scripts/verificar.sh > /tmp/verify_gitlab.log 2>&1; then
  grep -E "Asserts correctos|Fallos:|TODO VERIFICADO" /tmp/verify_gitlab.log | sed 's/^/    /'
else
  echo "    FALLO: la suite no pasa. No se publica nada." >&2
  tail -30 /tmp/verify_gitlab.log >&2
  exit 1
fi

# --- Configurar el remote -----------------------------------------------
if git remote get-url gitlab >/dev/null 2>&1; then
  git remote set-url gitlab "$GITLAB_REMOTE"
  echo ""
  echo "==> Remote 'gitlab' actualizado"
else
  git remote add gitlab "$GITLAB_REMOTE"
  echo ""
  echo "==> Remote 'gitlab' creado"
fi

if [ "$DRY_RUN" = "1" ]; then
  echo ""
  echo "==> DRY RUN: no se hace push. El push real seria:"
  echo "    git push gitlab HEAD:$GITLAB_BRANCH --force-with-lease"
  exit 0
fi

# --- Publicar ------------------------------------------------------------
echo ""
echo "==> Publicando en GitLab"
git push gitlab "HEAD:$GITLAB_BRANCH" --force-with-lease

echo ""
echo "==> GitLab sincronizado."
echo "    Verifica:  git ls-remote gitlab | head"
echo ""
echo "RECUERDA: las bases piden el codigo en el GitLab de MoraBanc."
echo "Confirma que la rama '$GITLAB_BRANCH' es la que espera el proyecto."
