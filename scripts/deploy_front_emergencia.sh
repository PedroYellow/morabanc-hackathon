#!/usr/bin/env bash
# Despliegue de emergencia del front a S3 + invalidacion de CloudFront.
#
# PARA QUE EXISTE
# ---------------
# `deploy_front.sh` lee la configuracion de `terraform output`, asi que
# necesita que terraform pueda hablar con AWS. Si lo unico que cambia
# son las CREDENCIALES (que caducan cada pocas horas del workshop),
# no hace falta un apply completo: el front son ficheros estaticos y
# solo hay que subirlos con su Content-Type y validar la cache.
#
# Este script hace exactamente eso, sin terraform:
#   1. sube los ficheros de frontend/ a S3 con el Content-Type correcto
#   2. invalida la cache de CloudFront
#   3. verifica que lo servido tiene el Content-Type y el contenido
#      esperados
#
# USO
# ----
#   source /data/cache/scratch/aws_env.sh   # credenciales nuevas
#   bash scripts/deploy_front_emergencia.sh
#
# Las credenciales se leen del entorno (AWS_ACCESS_KEY_ID,
# AWS_SECRET_ACCESS_KEY, AWS_SESSION_TOKEN). El script NO las escribe en
# ningun sitio: las guarda donde ya estaban (/data/cache/scratch/aws_env.sh,
# permisos 600, fuera del repo).
set -euo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$RAIZ"

BUCKET="morabanc-hackathon-dev-datos-539756034803-5397"
DISTRIBUCION="E1B4Z63SX4G4H8"
REGION="us-east-1"

# El AWS CLI esta descargado en /data/cache/scratch (no hay sudo para
# instalarlo).
export PATH="$PATH:/data/cache/scratch/awscli/bin:/data/cache/scratch/awscli/v2/current"

echo "==> Comprobando las credenciales"
aws sts get-caller-identity --output json >/dev/null 2>&1 || {
  echo "ERROR: las credenciales de AWS no son validas o han caducado." >&2
  echo "       Pide un juego nuevo en el taller (MoraBanc, +376 884 884)." >&2
  exit 1
}
echo "    OK"

echo ""
echo "==> Regenerando los datos demo con el motor real"
python3 frontend/generar_demo_data.py | tail -8

echo ""
echo "==> Subiendo el front a S3 (con el Content-Type correcto)"

# El Content-Type NO lo infiere el CLI a partir de la extension: si el
# objeto no existe, lo crea como application/octet-stream y, con
# nosniff, el navegador RECHAZA los modulos ESM (la voz de ElevenLabs
# no arranca) y descarga los .html en vez de mostrarlos.
subir() {
  local rel="$1" ct="$2" cache="$3"
  # Hay que BORRAR el objeto antes: si ya existe, "s3 cp" conserva el
  # Content-Type viejo y el arreglo no aterriza.
  aws s3 rm "s3://$BUCKET/$rel" >/dev/null 2>&1 || true
  if aws s3 cp "frontend/$rel" "s3://$BUCKET/$rel" \
       --content-type "$ct" --cache-control "$cache" --no-progress >/dev/null 2>&1; then
    echo "    OK    $rel"
  else
    echo "    FALLO $rel" >&2
    return 1
  fi
}

# Los HTML se releen pronto (el pitch puede cambiar algo entre medias).
for f in index.html mb-login.html mb-empresas.html mb-particulares.html maqueta.html; do
  [ -f "frontend/$f" ] && subir "$f" "text/html; charset=utf-8" "no-cache, must-revalidate"
done

# Los datos: los lee el motor.
for f in frontend/data/*.json; do
  rel="${f#frontend/}"
  subir "$rel" "application/json; charset=utf-8" "max-age=300"
done
for f in frontend/data/*.csv; do
  rel="${f#frontend/}"
  subir "$rel" "text/csv; charset=utf-8" "max-age=300"
done

# Los assets: versionados en la URL, se cachean.
for f in frontend/assets/*.js; do
  rel="${f#frontend/}"
  subir "$rel" "application/javascript; charset=utf-8" "max-age=300"
done
for f in frontend/assets/*.css; do
  rel="${f#frontend/}"
  subir "$rel" "text/css; charset=utf-8" "max-age=300"
done
for f in frontend/assets/*.svg; do
  rel="${f#frontend/}"
  subir "$rel" "image/svg+xml" "max-age=300"
done
for f in frontend/assets/*.png frontend/assets/*.jpg frontend/assets/*.webp; do
  [ -f "$f" ] || continue
  rel="${f#frontend/}"
  case "$f" in
    *.png)  ct="image/png" ;;
    *.jpg)  ct="image/jpeg" ;;
    *.webp) ct="image/webp" ;;
  esac
  subir "$rel" "$ct" "max-age=300"
done
# Los assets de MoraBanc (subcarpeta mb/)
for f in frontend/assets/mb/*; do
  [ -f "$f" ] || continue
  rel="${f#frontend/}"
  case "$f" in
    *.svg) ct="image/svg+xml" ;;
    *.png) ct="image/png" ;;
    *.jpg) ct="image/jpeg" ;;
    *.css) ct="text/css; charset=utf-8" ;;
    *.js)  ct="application/javascript; charset=utf-8" ;;
    *)     ct="application/octet-stream" ;;
  esac
  subir "$rel" "$ct" "max-age=300"
done

echo ""
echo "==> Comprobando la CloudFront Function (inyecta la x-api-key en el edge)"
# Terraform NO publica las CloudFront Functions: las deja en stage
# DEVELOPMENT, donde NO se ejecutan. Si esta en DEVELOPMENT, la API
# responde 403 y parece un problema de permisos.
FUNC_ETAG=$(aws cloudfront describe-function --name mora-inject-api-key \
             --query ETag --output text 2>/dev/null || echo "")
FUNC_STAGE=$(aws cloudfront describe-function --name mora-inject-api-key \
              --query FunctionMetadata.Stage --output text 2>/dev/null || echo "?")
echo "    stage: $FUNC_STAGE"
if [ "$FUNC_STAGE" != "LIVE" ] && [ -n "$FUNC_ETAG" ]; then
  echo "    Publicando en LIVE..."
  aws cloudfront publish-function --name mora-inject-api-key --if-match "$FUNC_ETAG" >/dev/null
  sleep 3
  FUNC_STAGE=$(aws cloudfront describe-function --name mora-inject-api-key \
                --query FunctionMetadata.Stage --output text 2>/dev/null || echo "?")
  echo "    stage ahora: $FUNC_STAGE"
fi
# El ETag cambia en cada apply: se relee antes de publicar, no se cachea.
if [ "$FUNC_STAGE" != "LIVE" ]; then
  echo "AVISO: la CloudFront Function sigue en $FUNC_STAGE. La API puede dar 403." >&2
fi

echo ""
echo "==> Invalidando la cache de CloudFront"
INVAL=$(aws cloudfront create-invalidation --distribution-id "$DISTRIBUCION" \
        --paths "/*" --query Invalidation.Id --output text)
echo "    $INVAL"

# Esperar a que termine: mientras esta InProgress, los edge nodes
# siguen sirviendo la version anterior y la comprobacion de abajo
# daria un falso negativo.
for i in $(seq 1 30); do
  ESTADO=$(aws cloudfront get-invalidation --distribution-id "$DISTRIBUCION" \
           --id "$INVAL" --query Invalidation.Status --output text 2>/dev/null || echo "?")
  [ "$ESTADO" = "Completed" ] && break
  sleep 4
done
echo "    estado: $ESTADO"

echo ""
echo "==> Verificando lo que se sirve de verdad"
fallos=0
comprobar() {
  local url="$1" ct="$2" contenido="$3"
  local servido
  servido=$(curl -sI -m 25 "$url" | tr -d '\r' | grep -i '^content-type' | head -1 | tr -d '\n')
  if echo "$servido" | grep -qi "$ct"; then
    if [ -n "$contenido" ] && ! curl -s -m 25 "$url" | grep -q "$contenido"; then
      echo "    FALLO $url (content-type bien, contenido viejo)"
      fallos=$((fallos+1))
      return
    fi
    echo "    OK    $(basename "$url")  $servido"
  else
    echo "    FALLO $url  content-type: ${servido:-<ninguno>}"
    fallos=$((fallos+1))
  fi
}

BASE="https://welcomeandorra.com"
comprobar "$BASE/index.html" "text/html" "__API_URL__"
comprobar "$BASE/mb-login.html" "text/html" "mb-login.js"
comprobar "$BASE/mb-empresas.html" "text/html" "frameAsesor"
comprobar "$BASE/assets/app.js" "javascript" "esEmpresa"
comprobar "$BASE/assets/mb-login.js" "javascript" "esEmpresa"
comprobar "$BASE/assets/mb-portal.js" "javascript" "mb-selector-empresas"
comprobar "$BASE/assets/elevenlabs-client.js" "javascript" "Conversation"
comprobar "$BASE/assets/livekit-client.js" "javascript" ""
comprobar "$BASE/assets/libsamplerate.worklet.js" "javascript" ""
comprobar "$BASE/data/demo_data.json" "json" "crecimiento"
comprobar "$BASE/data/mb_escenarios.json" "json" "crecimiento"

echo ""
if [ "$fallos" -eq 0 ]; then
  echo "TODO CORRECTO: el front sirve el contenido nuevo con el Content-Type correcto."
else
  echo "$fallos comprobacion(es) fallaron." >&2
  exit 1
fi
