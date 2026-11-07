#!/usr/bin/env bash
# Verificacion completa del proyecto.
# Ejecuta todo lo que se puede verificar sin credenciales AWS.
set -uo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$RAIZ"

TOTAL_PASS=0
TOTAL_FAIL=0
FALLOS=()

banner() {
  echo ""
  echo "=============================================================="
  echo "  $1"
  echo "=============================================================="
}

run_suite() {
  local nombre="$1"; shift
  local cmd="$*"
  banner "$nombre"
  local out
  out="$(eval "$cmd" 2>&1)"
  echo "$out" | grep -E "^  (PASS|FAIL)" | tail -3
  local p f
  p=$(echo "$out" | grep -cE "^\s+PASS")
  f=$(echo "$out" | grep -cE "^\s+FAIL")
  TOTAL_PASS=$((TOTAL_PASS + p))
  TOTAL_FAIL=$((TOTAL_FAIL + f))
  # Cada suite imprime su propio mensaje final. El patron acepta
  # cualquier sufijo: "TODOS LOS TESTS DEL ASISTENTE PASAN",
  # "TODOS LOS TESTS DEL AUTHORIZER PASAN", "TODOS LOS TESTS PASAN"...
  if echo "$out" | grep -qE "TODOS LOS TESTS( DEL [A-Z ]+)? PASAN|LA LAMBDA FUNCIONA|Success! The configuration is valid"; then
    echo "  ✔ $nombre — $p asserts"
  else
    echo "  ✘ $nombre — $f fallos"
    echo "$out" | grep -E "^  FAIL|Error" | head -5
    FALLOS+=("$nombre")
  fi
}

# Limpieza de caches
find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null

run_suite "Motor fiscal andorrano" "python3 tests/test_fiscal.py"
run_suite "Motor de tesoreria"    "python3 tests/test_tesoreria.py"
run_suite "Bucle de cierre"        "python3 tests/test_cierre.py"
run_suite "Agente de Bedrock"     "python3 tests/test_agente.py"
run_suite "Formato del pitch"     "python3 tests/test_formato.py"
run_suite "Terraform (orden y IaC)" "python3 tests/test_terraform.py"
run_suite "Proteccion de la API" "python3 tests/test_authorizer.py"
run_suite "Asistente de voz"     "python3 tests/test_asistente.py"
run_suite "Lambda empaquetada"    "bash scripts/test_lambda.sh"

# El test del frontend necesita Chromium + Playwright. Si no estan, se omite
# con un aviso claro en vez de romper la verificacion.
# PLAYWRIGHT_DIR: raiz donde esta node_modules con playwright (opcional).
# FRONT_TEST_DIR:  directorio con test_frontend.js y sus dependencias.
PLAYWRIGHT_DIR="${PLAYWRIGHT_DIR:-}"
FRONT_TEST_DIR="${FRONT_TEST_DIR:-}"
if [ -z "$FRONT_TEST_DIR" ] && [ -n "$PLAYWRIGHT_DIR" ]; then
  FRONT_TEST_DIR="$PLAYWRIGHT_DIR"
fi
if command -v node >/dev/null 2>&1 && [ -n "$FRONT_TEST_DIR" ] && \
   [ -d "$FRONT_TEST_DIR/node_modules/playwright" ]; then
  banner "Frontend (Chromium real)"
  # El test necesita node_modules/playwright junto al script. Si el directorio
  # de pruebas no contiene el script, se copia alli (patron CI: deps en el
  # raiz del repo, script en scripts/).
  # IMPORTANTE: se copia SIEMPRE, para no usar una copia vieja del test
  # (si no, un test nuevo no se ejecuta y la suite sigue "en verde" sin
  # comprobar nada nuevo).
  FRONT_SCRIPT="$FRONT_TEST_DIR/test_frontend.js"
  cp "$RAIZ/scripts/test_frontend.js" "$FRONT_SCRIPT"
  FRONT_OUT="$(cd "$FRONT_TEST_DIR" && \
    ${CHROMIUM_LD_PATH:+env LD_LIBRARY_PATH="$CHROMIUM_LD_PATH"} \
    node "$(basename "$FRONT_SCRIPT")" http://localhost:8899/ 2>&1)"
  echo "$FRONT_OUT" | grep -E "^  (PASS|FAIL)" | tail -3
  FP=$(echo "$FRONT_OUT" | grep -cE "^\s+PASS")
  FF=$(echo "$FRONT_OUT" | grep -cE "^\s+FAIL")
  TOTAL_PASS=$((TOTAL_PASS + FP))
  TOTAL_FAIL=$((TOTAL_FAIL + FF))
  if echo "$FRONT_OUT" | grep -q "TODOS LOS TESTS DEL FRONTEND PASAN"; then
    echo "  ✔ Frontend — $FP asserts"
  else
    echo "  ✘ Frontend — $FF fallos"
    echo "$FRONT_OUT" | grep -E "^\s+FAIL|ERROR" | head -5
    FALLOS+=("Frontend")
  fi

  # --- El asistente de voz y la carga de archivos ----------------------
  # El cuadro de voz tiene que saludar y guiar, y los archivos se tienen
  # que poder arrastrar a cualquier parte de la pagina.
  ASIS_SCRIPT="$FRONT_TEST_DIR/test_asistente.js"
  cp "$RAIZ/scripts/test_asistente.js" "$ASIS_SCRIPT"
  ASIS_OUT="$(cd "$FRONT_TEST_DIR" && \
    ${CHROMIUM_LD_PATH:+env LD_LIBRARY_PATH="$CHROMIUM_LD_PATH"} \
    FUENTE_APP_JS="$RAIZ/frontend/assets/app.js" \
    node "$(basename "$ASIS_SCRIPT")" http://localhost:8899/ 2>&1)"
  echo "$ASIS_OUT" | grep -E "^  (PASS|FAIL)" | tail -3
  AP=$(echo "$ASIS_OUT" | grep -cE "^\s+PASS")
  AF=$(echo "$ASIS_OUT" | grep -cE "^\s+FAIL")
  TOTAL_PASS=$((TOTAL_PASS + AP))
  TOTAL_FAIL=$((TOTAL_FAIL + AF))
  if echo "$ASIS_OUT" | grep -q "TODOS LOS TESTS DEL ASISTENTE PASAN"; then
    echo "  ✔ Asistente de voz — $AP asserts"
  else
    echo "  ✘ Asistente de voz — $AF fallos"
    echo "$ASIS_OUT" | grep -E "^\s+FAIL|ERROR" | head -5
    FALLOS+=("Asistente de voz")
  fi
else
  echo ""
  echo "  (test de frontend omitido: falta Chromium/Playwright)"
fi

banner "Terraform"
TF="terraform"
if [ -n "${TERRAFORM_BIN:-}" ] && [ -x "${TERRAFORM_BIN}" ]; then TF="$TERRAFORM_BIN"; fi
if command -v "$TF" >/dev/null 2>&1; then
  ( cd terraform && "$TF" init -backend=false -input=false >/dev/null 2>&1 && "$TF" fmt -check >/dev/null 2>&1 && "$TF" validate 2>&1 | tail -1 )
  if ( cd terraform && "$TF" validate >/dev/null 2>&1 ); then
    echo "  ✔ Terraform — configuracion valida"
    TOTAL_PASS=$((TOTAL_PASS + 1))
  else
    echo "  ✘ Terraform — configuracion invalida"
    TOTAL_FAIL=$((TOTAL_FAIL + 1))
    FALLOS+=("Terraform")
  fi
else
  echo "  (terraform no instalado: se omite)"
fi

banner "Corpus normativo (RAG)"
NCORPUS=$(ls frontend/../normativa/*.md 2>/dev/null | wc -l)
if [ "$NCORPUS" -ge 4 ]; then
  echo "  ✔ $NCORPUS documentos normativos"
  TOTAL_PASS=$((TOTAL_PASS + NCORPUS))
  # Los importes clave deben estar en el corpus (el RAG los cita)
  if grep -q "2.672,52" normativa/*.md && grep -q "800 euros" normativa/*.md; then
    echo "  ✔ Cifras clave de CASS e IRPF presentes en el corpus"
    TOTAL_PASS=$((TOTAL_PASS + 1))
  else
    echo "  ✘ Faltan cifras clave en el corpus"
    TOTAL_FAIL=$((TOTAL_FAIL + 1))
    FALLOS+=("corpus")
  fi
else
  echo "  ✘ Corpus incompleto ($NCORPUS documentos)"
  TOTAL_FAIL=$((TOTAL_FAIL + 1))
  FALLOS+=("corpus")
fi

banner "Integridad del frontend"
for f in index.html assets/app.js assets/styles.css data/demo_data.json; do
  if [ -f "frontend/$f" ]; then
    TOTAL_PASS=$((TOTAL_PASS + 1))
  else
    echo "  ✘ falta frontend/$f"
    TOTAL_FAIL=$((TOTAL_FAIL + 1))
    FALLOS+=("frontend/$f")
  fi
done
if command -v node >/dev/null 2>&1; then
  if node --check frontend/assets/app.js 2>/dev/null; then
    echo "  ✔ Sintaxis JS valida"
    TOTAL_PASS=$((TOTAL_PASS + 1))
  else
    echo "  ✘ Sintaxis JS invalida"
    node --check frontend/assets/app.js 2>&1 | head -3
    TOTAL_FAIL=$((TOTAL_FAIL + 1))
    FALLOS+=("app.js")
  fi
fi

banner "Idempotencia del despliegue del front"
# Ejecutar deploy_front.sh dos veces no debe duplicar la inyeccion de config.
BACKUP_IDX=$(mktemp)
cp frontend/index.html "$BACKUP_IDX"
D1=$(bash scripts/deploy_front.sh 2>&1 | grep -c "__API_URL__")
D2=$(bash scripts/deploy_front.sh 2>&1 | grep -c "__API_URL__")
N_INJ=$(grep -c "window.__API_URL__" frontend/index.html)
# 0 = modo demo (correcto sin terraform), 1 = modo real. >1 = duplicado.
if [ "$N_INJ" -le 1 ]; then
  if [ "$N_INJ" -eq 1 ]; then
    echo "  ✔ Inyeccion idempotente (1 config tras 2 ejecuciones, modo real)"
  else
    echo "  ✔ Inyeccion idempotente (0 configs, modo demo: correcto sin terraform)"
  fi
  TOTAL_PASS=$((TOTAL_PASS + 1))
else
  echo "  ✘ La inyeccion se duplica ($N_INJ configs)"
  TOTAL_FAIL=$((TOTAL_FAIL + 1))
  FALLOS+=("deploy idempotencia")
fi
cp "$BACKUP_IDX" frontend/index.html
rm -f "$BACKUP_IDX"

banner "Sintaxis Python"
for f in engine/*.py agent/*.py lambda/*.py data/*.py demo*.py; do
  if python3 -m py_compile "$f" 2>/dev/null; then
    TOTAL_PASS=$((TOTAL_PASS + 1))
  else
    echo "  ✘ $f"
    TOTAL_FAIL=$((TOTAL_FAIL + 1))
    FALLOS+=("$f")
  fi
done
echo "  ✔ Todos los ficheros Python compilan"

banner "RESULTADO"
echo "  Asserts correctos: $TOTAL_PASS"
echo "  Fallos:            $TOTAL_FAIL"
if [ ${#FALLOS[@]} -gt 0 ]; then
  echo "  Suites con problemas: ${FALLOS[*]}"
  exit 1
fi
echo ""
echo "  ✔ TODO VERIFICADO"
exit 0
