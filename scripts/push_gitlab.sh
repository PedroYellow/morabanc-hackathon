#!/usr/bin/env bash
# Publica el repo en GitLab de MoraBanc (el repositorio oficial del hackathon).
#
# POR QUE EXISTE ESTE SCRIPT ADEMAS DE sync_gitlab.sh
#   sync_gitlab.sh es el generico (verifica la suite y publica).
#   Este es el atajo para el dia del hackathon: ya tiene la URL y la
#   configuracion de credenciales de este proyecto, y da un mensaje claro
#   si el token no tiene permiso de escritura.
#
# USO
#   bash scripts/push_gitlab.sh
#
# SI FALLA CON 403
#   El token no tiene el permiso "Code: Push". Solucion en 30 segundos:
#   GitLab -> Edit profile -> Access Tokens -> Edit token
#     -> en "Projects", anade el proyecto morabanc-hackathon con rol
#        Maintainer y marca "Code: Push" -> Save.
#   O crea un token classic nuevo con el scope write_repository.
set -uo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$RAIZ"

REMOTE="${GITLAB_REMOTE:-https://gitlab.com/pedro322/morabanc-hackathon.git}"
BRANCH="${GITLAB_BRANCH:-main}"
CRED_FILE="${GITLAB_CRED_FILE:-/data/.git-credentials-gitlab}"

echo "==> Publicando en GitLab de MoraBanc"
echo "    destino: $REMOTE ($BRANCH)"

# --- Credenciales --------------------------------------------------------
# El token se guarda en un fichero FUERA del repo, con permisos 600, y se
# lee con credential.helper. Nunca va en la URL del remote ni en el codigo.
if [ ! -f "$CRED_FILE" ]; then
  echo ""
  echo "ERROR: no hay fichero de credenciales en $CRED_FILE" >&2
  echo "" >&2
  echo "Crealo con:" >&2
  echo "  printf 'https://pedro322:%s@gitlab.com\n' \"\$GITLAB_TOKEN\" > $CRED_FILE" >&2
  echo "  chmod 600 $CRED_FILE" >&2
  echo "" >&2
  echo "Y exporta GITLAB_TOKEN con un token que tenga 'Code: Push'." >&2
  exit 2
fi
chmod 600 "$CRED_FILE" 2>/dev/null || true

git config --local "credential.https://gitlab.com.helper" "store --file=$CRED_FILE"

if ! git remote get-url gitlab >/dev/null 2>&1; then
  git remote add gitlab "$REMOTE"
fi
git remote set-url gitlab "$REMOTE"

# --- Verificar antes de publicar -----------------------------------------
echo ""
echo "==> Verificando la suite antes de publicar"

# En una maquina de trabajo puede que Terraform y Chromium no esten en el
# PATH. Si estan en las rutas habituales de este host, los usamos: si no, la
# suite omite esas dos partes (lo avisa) y el motor entero se verifica igual.
[ -x "${TERRAFORM_BIN:-}" ] || [ -x /data/cache/scratch/tfbin/terraform ] && \
  export TERRAFORM_BIN="${TERRAFORM_BIN:-/data/cache/scratch/tfbin/terraform}"
if [ -d /data/cache/scratch/ptest/node_modules/playwright ]; then
  export FRONT_TEST_DIR="${FRONT_TEST_DIR:-/data/cache/scratch/ptest}"
  export CHROMIUM_LD_PATH="${CHROMIUM_LD_PATH:-/data/cache/scratch/chromedeps/root/usr/lib/x86_64-linux-gnu:/data/cache/scratch/chromedeps/root/lib/x86_64-linux-gnu}"
fi

if bash scripts/verificar.sh > /tmp/verify_push_gitlab.log 2>&1; then
  grep -E "Asserts correctos|Fallos:|omitido" /tmp/verify_push_gitlab.log | sed 's/^/    /'
else
  echo "    FALLO: la suite no pasa. No se publica nada." >&2
  tail -25 /tmp/verify_push_gitlab.log >&2
  exit 1
fi

# --- Publicar ------------------------------------------------------------
echo ""
echo "==> Push a GitLab"
if git push gitlab "HEAD:$BRANCH" 2>/tmp/push_gitlab.err; then
  echo ""
  echo "==> PUBLICADO. Verificacion:"
  git ls-remote gitlab "refs/heads/$BRANCH" | sed 's/^/    /'
  echo ""
  echo "    https://gitlab.com/pedro322/morabanc-hackathon/-/tree/$BRANCH"
  exit 0
fi

# --- Diagnostico ---------------------------------------------------------
echo ""
echo "==> El push fallo:" >&2
sed 's/^/    /' /tmp/push_gitlab.err >&2
echo ""

if grep -q "Code: Push\|fine-grained" /tmp/push_gitlab.err; then
  echo "  CAUSA: el token no tiene el permiso 'Code: Push'." >&2
  echo "" >&2
  echo "  Solucion (30 segundos):" >&2
  echo "    1. GitLab -> Edit profile -> Access Tokens" >&2
  echo "    2. Edit token (o Add new token):" >&2
  echo "       - classic: scope 'write_repository'" >&2
  echo "       - fine-grained: proyecto morabanc-hackathon," >&2
  echo "         rol Maintainer, marca 'Code: Push'" >&2
  echo "    3. Copia el token y:" >&2
  echo "       export GITLAB_TOKEN='glpat-...'" >&2
  echo "       printf 'https://pedro322:%s@gitlab.com\n' \"\$GITLAB_TOKEN\" > $CRED_FILE" >&2
  echo "       chmod 600 $CRED_FILE" >&2
  echo "       bash scripts/push_gitlab.sh" >&2
elif grep -qi "403\|denied" /tmp/push_gitlab.err; then
  echo "  CAUSA: acceso denegado. Comprueba que el token es de TU usuario" >&2
  echo "  (pedro322) y que el proyecto es el correcto." >&2
else
  echo "  Revisa el error de arriba." >&2
fi

echo ""
echo "  El repo de GitHub sigue siendo el maestro y esta actualizado:" >&2
echo "    https://github.com/PedroYellow/morabanc-hackathon" >&2
echo "  Si el wifi falla en la sala, el modo demo local funciona sin AWS." >&2
exit 1
