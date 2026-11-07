#!/usr/bin/env bash
# Test de la Lambda empaquetada: construye el zip igual que Terraform y
# ejecuta el handler con eventos reales, como haria AWS.
set -euo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ZIP="${1:-/tmp/motor.zip}"
DEST="${LAMBDA_TEST_DEST:-/tmp/lambda_test}"
export RAIZ_PROYECTO="$RAIZ"

echo "==> Construyendo el zip de la Lambda"
rm -f "$ZIP"
python3 - "$RAIZ" "$ZIP" <<'PY'
import os, sys, zipfile
raiz, zip_path = sys.argv[1], sys.argv[2]
excl = {"__pycache__", ".pytest_cache", ".build", "terraform", "data", "tests", ".git"}
with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
    for root, dirs, files in os.walk(raiz):
        dirs[:] = [d for d in dirs if d not in excl]
        for f in files:
            if f.endswith((".pyc", ".md", ".html")) or f.startswith("."):
                continue
            fp = os.path.join(root, f)
            z.write(fp, os.path.relpath(fp, raiz))
print("   zip:", zip_path)
PY

echo "==> Extrayendo y ejecutando tests del handler"
rm -rf "$DEST"
mkdir -p "$DEST"
python3 -c "import zipfile; zipfile.ZipFile('$ZIP').extractall('$DEST')"

cd "$DEST"
BEDROCK_MOCK=1 ENVIRONMENT=test python3 - <<'PY'
import sys, os, json, importlib.util
sys.path.insert(0, os.path.abspath("."))
spec = importlib.util.spec_from_file_location("handler", "lambda/handler.py")
h = importlib.util.module_from_spec(spec)
spec.loader.exec_module(h)
print("   handler importado OK")

fallos = []
def check(nombre, ok, extra=""):
    print(f"   {'PASS' if ok else 'FAIL'}  {nombre}{(' -> ' + extra) if extra else ''}")
    if not ok:
        fallos.append(nombre)

r = h.lambda_handler({"rawPath": "/salud", "requestContext": {"http": {"method": "GET"}}}, None)
check("GET /salud -> 200", r["statusCode"] == 200, r["body"][:60])

csv = open(os.path.join(os.environ["RAIZ_PROYECTO"], "data", "demo_freelancer_contratar.csv"), encoding="utf-8").read()
ev = {"rawPath": "/preguntar", "requestContext": {"http": {"method": "POST"}},
      "body": json.dumps({"pregunta": "¿Cuánto se me está escapando cada mes?",
                          "empresa_id": "e1", "extracto_csv": csv,
                          "saldo_actual": 3200, "renta_neta_anual": 28000,
                          "margen_bruto": 0.70})}
r2 = h.lambda_handler(ev, None)
b = json.loads(r2["body"])
check("POST /preguntar -> 200", r2["statusCode"] == 200, str(r2["statusCode"]))
check("devuelve herramientas", len(b.get("herramientas", [])) > 0,
      ",".join(x["tool"] for x in b.get("herramientas", [])))
check("la respuesta no esta vacia", len(b.get("respuesta", "")) > 50)

r3 = h.lambda_handler({"rawPath": "/preguntar", "requestContext": {"http": {"method": "POST"}},
                       "body": json.dumps({})}, None)
check("sin pregunta -> 400", r3["statusCode"] == 400, r3["body"])

r4 = h.lambda_handler({"rawPath": "/preguntar", "requestContext": {"http": {"method": "POST"}},
                       "body": "{no json"}, None)
check("JSON invalido -> 400", r4["statusCode"] == 400, r4["body"])

r5 = h.lambda_handler({"rawPath": "/preguntar", "requestContext": {"http": {"method": "OPTIONS"}}}, None)
check("OPTIONS -> 204", r5["statusCode"] == 204, str(r5["statusCode"]))

r6 = h.lambda_handler({"rawPath": "/preguntar", "requestContext": {"http": {"method": "POST"}},
                       "body": json.dumps({"pregunta": "¿Puedo contratar a 2400 euros?"})}, None)
check("pregunta sin extracto -> 200 (no crashea)", r6["statusCode"] == 200, str(r6["statusCode"]))

print()
if fallos:
    print(f"FALLOS: {len(fallos)} -> {fallos}")
    sys.exit(1)
print("LA LAMBDA FUNCIONA")
PY
