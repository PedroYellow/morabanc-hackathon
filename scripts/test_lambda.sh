#!/usr/bin/env bash
# Test de la Lambda empaquetada: construye el zip igual que Terraform y
# ejecuta el handler con eventos reales, como haria AWS.
set -euo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ZIP="${1:-/tmp/motor.zip}"
DEST="${LAMBDA_TEST_DEST:-/tmp/lambda_test}"
export RAIZ_PROYECTO="$RAIZ"

echo "==> Construyendo el zip de la Lambda (mismos excludes que terraform/main.tf)"
rm -f "$ZIP"
python3 - "$RAIZ" "$ZIP" <<'PY'
import os, re, sys, zipfile
raiz, zip_path = sys.argv[1], sys.argv[2]

# Leemos los excludes DIRECTAMENTE de terraform/main.tf (archive_file "motor").
# Si el dia 7 alguien cambia los excludes en Terraform, este test los hereda
# en vez de quedarse con una copia desincronizada que ya no valida nada.
tf = open(os.path.join(raiz, "terraform", "main.tf"), encoding="utf-8").read()
bloque = re.search(
    r'data\s+"archive_file"\s+"motor"\s*\{(.*?)\n\}', tf, re.S)
if not bloque:
    print("ERROR: no se encontro el bloque archive_file \"motor\" en terraform/main.tf",
          file=sys.stderr)
    sys.exit(1)
excl_list = re.findall(r'"([^"]+)"', re.search(r'excludes\s*=\s*\[(.*?)\]', bloque.group(1), re.S).group(1))
excl = set(excl_list)

with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
    for root, dirs, files in os.walk(raiz):
        dirs[:] = [d for d in dirs if d not in excl]
        for f in files:
            if f in excl or f.startswith(".") or f.endswith((".pyc", ".md", ".html", ".json")):
                continue
            fp = os.path.join(root, f)
            z.write(fp, os.path.relpath(fp, raiz))
print(f"   zip: {zip_path}")
print(f"   excludes heredados de terraform/main.tf: {sorted(excl)}")
PY

echo "==> Extrayendo y ejecutando tests del handler"
rm -rf "$DEST"
mkdir -p "$DEST"
python3 -c "import zipfile; zipfile.ZipFile('$ZIP').extractall('$DEST')"

cd "$DEST"
BEDROCK_MOCK=1 ENVIRONMENT=test PYTHONPATH="$DEST" python3 - <<'PY'
import sys, os, json, importlib, re
sys.path.insert(0, os.path.abspath("."))

fallos = []
def check(nombre, ok, extra=""):
    print(f"   {'PASS' if ok else 'FAIL'}  {nombre}{(' -> ' + extra) if extra else ''}")
    if not ok:
        fallos.append(nombre)

# IMPORTANTE: se importa EXACTAMENTE como lo hace AWS Lambda, es decir
# con el valor de "handler" en terraform/main.tf -> "lambda.handler.lambda_handler".
# Si el path del handler en Terraform no coincide con la estructura del zip,
# la Lambda falla en la PRIMERA invocacion con ModuleNotFoundError, y este
# test es lo que lo detecta antes del dia del hackathon.
try:
    h = importlib.import_module("lambda.handler")
    check("import como AWS: lambda.handler", True)
except Exception as e:
    check("import como AWS: lambda.handler", False, f"{type(e).__name__}: {e}")
    print("FALLOS: el handler de Terraform no coincide con la estructura del zip")
    sys.exit(1)

check("la funcion lambda_handler existe", hasattr(h, "lambda_handler"))
check("lambda/__init__.py esta en el zip",
      os.path.isfile(os.path.join(os.path.dirname(os.path.abspath(__file__)), "lambda", "__init__.py"))
      or os.path.isfile("lambda/__init__.py"))

# El "handler" de Terraform debe coincidir con el modulo que acabamos de
# importar. Si alguien cambia uno y no el otro, la Lambda falla en AWS con
# ModuleNotFoundError y aqui no se entera nadie.
try:
    tf = open(os.path.join(os.environ["RAIZ_PROYECTO"], "terraform", "main.tf"),
              encoding="utf-8").read()
    handlers = re.findall(r'handler\s*=\s*"([^"]+)"', tf)
    mod_tf = handlers[0].rsplit(".", 1)[0] if handlers else ""
    check("el handler de Terraform coincide con el import real", mod_tf == "lambda.handler",
          f'terraform dice "{mod_tf}", el import real es "lambda.handler"')
except Exception as e:
    check("el handler de Terraform coincide con el import real", False, str(e))

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
