"""
El motor de decisiones de MoraBanc, servido en local.

POR QUE EXISTE ESTE
-------------------
La Lambda en AWS es el destino de produccion: es el motor con la
normativa andorrana, ejecutandose en la infraestructura del
hackathon. Pero mientras no haya credenciales de AWS para redesplegar
la Lambda (las del workshop caducan), el VPS sirve el MISMO motor en
local: los mismos ficheros, el mismo Python, los mismos numeros.

No es una maqueta ni una reimplementacion: es el motor de verdad,
corriendo en otro sitio. Cuando la Lambda se redespliegue con el
codigo nuevo, este servidor deja de usarse (el nginx puede dejar de
enrutar a el).

Lo que responde es lo mismo que la Lambda:
    POST /preguntar  {"pregunta": "...", "empresa_id": "...",
                       "saldo_actual": 8500, "renta_neta_anual": 30000,
                       "margen_bruto": 0.7, "actividad": "..."}
    -> {"respuesta": "...", "herramientas": [...]}

Si el motor no puede responder (no hay Bedrock configurado aqui), se
usa el enrutador determinista: las reglas del motor en Python, sin
LLM. Los numeros salen del motor, igual que en AWS.
"""

from __future__ import annotations

import json
import os
import sys
from decimal import Decimal

RAIZ = os.path.dirname(os.path.abspath(__file__))
if RAIZ not in sys.path:
    sys.path.insert(0, RAIZ)

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from agent.bedrock_agent import (
    AgenteFinanciero,
    ContextoEmpresa,
    _detectar_decision_compra,
    ejecutar_tool,
)


# ─────────────────────────────────────────────────────────────────────
# El agente: el mismo de la Lambda, pero en modo determinista (sin
# Bedrock). Los numeros salen del motor; el texto se compone con la
# plantilla que usa el mock del propio motor.
# ─────────────────────────────────────────────────────────────────────


def _respuesta_determinista(ctx: ContextoEmpresa, pregunta: str) -> dict:
    """
    Enruta la pregunta con las mismas reglas del router del motor y
    ejecuta la herramienta. Sin LLM: el texto se arma con el
    resultado de la herramienta, que es donde estan los numeros.
    """
    p = pregunta.lower()

    # 1) Las decisiones de compra (coche, casa, maquinaria, contrato).
    objetivo, importe = _detectar_decision_compra(p)
    if objetivo:
        params: dict = {"objetivo": objetivo, "texto": p}
        if importe is not None:
            params["importe"] = float(importe)
        out = ejecutar_tool("evaluar_compra", ctx, params)
        res = out.get("resultado") or {}
        if "error" not in res:
            partes = [res.get("veredicto", "")]
            for aviso in res.get("avisos", []):
                partes.append(aviso)
            if out.get("regla"):
                partes.append(f"Regla aplicada: {out['regla']}")
            return {
                "respuesta": "\n\n".join(p for p in partes if p),
                "herramientas": [
                    {
                        "tool": "evaluar_compra",
                        "input": params,
                        "resultado": res,
                        "regla": out.get("regla", ""),
                    }
                ],
            }

    # 2) El resto: el router del propio motor.
    agente = AgenteFinanciero(ctx)
    herramientas, resultados = agente._herramienta_determinista(pregunta)
    if resultados:
        nombre, out = resultados[0]
        res = out.get("resultado") or {}
        texto = _texto_de_resultado(nombre, res)
        if out.get("regla"):
            texto += f"\n\nRegla aplicada: {out['regla']}"
        return {
            "respuesta": texto,
            "herramientas": [
                {
                    "tool": nombre,
                    "input": {},
                    "resultado": res,
                    "regla": out.get("regla", ""),
                }
            ],
        }

    return {
        "respuesta": "",
        "herramientas": [],
    }


def _eur(v) -> str:
    """Un importe en formato europeo: 7.055,40 EUR."""
    try:
        return f"{float(v):,.2f}".replace(",", "\x00").replace(".", ",").replace("\x00", ".")
    except (TypeError, ValueError):
        return str(v)


def _pct(v) -> str:
    try:
        return f"{float(v):.2f}".replace(".", ",") + " %"
    except (TypeError, ValueError):
        return str(v)


#: Como se cuenta cada resultado: (que dice, como se formatea, que
#: unidad tiene). Sin esto, la respuesta al cliente era un volcado de
#: claves del motor ("tramo: 100%; base_cotizacion: 2.672,52"), que
#: no se lee como una respuesta.
_FORMATO_RESULTADOS: dict[str, list[tuple[str, str, str]]] = {
    "tramo_cass": [
        ("cuota_anual", "Tu CASS de 2026 es de", "eur"),
        ("tramo", "en el tramo", "texto"),
        ("cuota_mensual", "Son", "eur_mes"),
        ("base_cotizacion", "Tu base de cotizacion es de", "eur"),
    ],
    "calcular_irpf": [
        ("cuota_total", "Tu IRPF es de", "eur"),
        ("tipo_efectivo", "El tipo efectivo te queda en", "pct"),
    ],
    "calcular_igi": [
        ("cuota", "Tu IGI es de", "eur"),
        ("tipo", "El tipo aplicable es del", "pct"),
    ],
    "resumen_carga_fiscal": [
        ("cuota_anual_cass", "CASS", "eur_anual"),
        ("cuota_anual_irpf", "IRPF", "eur_anual"),
        ("total_carga_fiscal_anual", "El total", "eur_anual"),
    ],
    "detectar_fugas": [
        ("n_fugas", "Tienes", "fugas"),
        ("recuperable_mensual", "Recuperas", "eur_mes"),
        ("recuperable_anual", "Al año son", "eur"),
    ],
    "proyectar_caja": [
        ("meses", "Tu caja aguanta", "meses"),
        ("saldo_minimo", "El punto mas bajo es de", "eur"),
    ],
    "simular_contratacion": [
        ("coste_anual", "Contratar cuesta", "eur_anual"),
        ("facturacion_adicional", "Necesitas facturar", "eur_anual"),
    ],
    "analizar_tesoreria": [
        ("ingresos", "Ingresos", "eur_anual"),
        ("gastos", "Gastos", "eur_anual"),
        ("flujo_neto", "El flujo neto es de", "eur_anual"),
    ],
}


def _texto_de_resultado(nombre: str, res: dict) -> str:
    """Un texto de asesor, con los numeros en formato europeo."""
    if not isinstance(res, dict):
        return str(res)

    formato = _FORMATO_RESULTADOS.get(nombre)
    if not formato:
        # Sin formato conocido: se(listo los pares clave-valor, pero
        # con las etiquetas en espanol y los numeros en formato
        # europeo.
        return _texto_generico(res)

    frases = []
    for clave, antes, como in formato:
        if clave not in res or res[clave] in (None, ""):
            continue
        valor = res[clave]
        if como == "eur":
            frases.append(f"{antes} {_eur(valor)} EUR.")
        elif como == "eur_mes":
            frases.append(f"{antes} {_eur(valor)} EUR al mes.")
        elif como == "eur_anual":
            frases.append(f"{antes} {_eur(valor)} EUR al año.")
        elif como == "pct":
            v = str(valor)
            if "%" not in v:
                v = f"{v.rstrip('%')} %"
            if frases and not frases[-1].endswith("."):
                frases[-1] = frases[-1] + "."
            frases.append(f"{antes} {v}.")
        elif como == "meses":
            frases.append(f"{antes} {valor} meses.")
        elif como == "fugas":
            frases.append(f"{antes} {valor} fugas en la cuenta.")
        elif como == "texto":
            # La primera letra en mayuscula si empieza la frase, y
            # punto antes si la anterior no lo lleva.
            v = str(valor)
            if v.endswith("%"):
                v = v[:-1].rstrip() + " %"
            if frases and not frases[-1].endswith("."):
                frases[-1] = frases[-1] + "."
            frases.append(f"{antes} {v}.")
        else:
            frases.append(f"{antes} {valor}.")

    if not frases:
        return _texto_generico(res)

    # Cada frase empieza en mayuscula: el texto se lee como una
    # respuesta, no como un volcado de datos.
    capitalizadas = []
    for f in frases:
        f = f.strip()
        if f:
            f = f[0].upper() + f[1:]
        capitalizadas.append(f)
    return " ".join(capitalizadas)


def _texto_generico(res: dict) -> str:
    etiquetas = {
        "cuota_anual": "cuota anual",
        "cuota_mensual": "cuota mensual",
        "tramo": "tramo",
        "base_cotizacion": "base de cotizacion",
        "cuota_total": "cuota total",
        "base_imponible": "base imponible",
        "tipo_efectivo": "tipo efectivo",
        "cuota": "cuota",
        "tipo": "tipo",
        "ingresos": "ingresos",
        "gastos": "gastos",
        "flujo_neto": "flujo neto",
        "n_fugas": "fugas detectadas",
        "recuperable_mensual": "recuperable al mes",
        "recuperable_anual": "recuperable al año",
        "meses": "meses de caja",
        "saldo_minimo": "saldo minimo",
        "saldo_final": "saldo final",
    }
    partes = []
    for k, v in res.items():
        if isinstance(v, (dict, list)):
            continue
        if isinstance(v, (int, float, Decimal)) and not isinstance(v, bool):
            partes.append(f"{etiquetas.get(k, k)}: {_eur(v)} EUR")
        elif v not in (None, ""):
            partes.append(f"{etiquetas.get(k, k)}: {v}")
    return "; ".join(partes)


# ─────────────────────────────────────────────────────────────────────
# El servidor HTTP
# ─────────────────────────────────────────────────────────────────────


class Handler(BaseHTTPRequestHandler):
    server_version = "MoraBancMotor/1.0"

    def log_message(self, format, *args):
        pass  # silencio: el access log lo pone nginx

    def _json(self, status: int, body: dict):
        crudo = json.dumps(body, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(crudo)))
        self.end_headers()
        self.wfile.write(crudo)

    def do_GET(self):
        if self.path.rstrip("/") in ("/salud", "/health"):
            self._json(200, {"ok": True, "servicio": "motor-morabanc"})
        else:
            self._json(404, {"error": "no encontrado"})

    def do_POST(self):
        if self.path.rstrip("/") != "/preguntar":
            self._json(404, {"error": "no encontrado"})
            return

        try:
            largo = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            largo = 0

        # Tope: el extracto del cliente puede ser grande, pero no
        # infinito (la Lambda tiene el mismo limite).
        if largo > 6 * 1024 * 1024:
            self._json(413, {"error": "El fichero es demasiado grande (max 6 MB)"})
            return

        try:
            cuerpo = json.loads(self.rfile.read(largo).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            self._json(400, {"error": "El cuerpo no es JSON valido"})
            return

        pregunta = (cuerpo.get("pregunta") or "").strip()
        if not pregunta:
            self._json(400, {"error": "Falta la pregunta"})
            return

        ctx = ContextoEmpresa(
            saldo_actual=Decimal(str(cuerpo.get("saldo_actual") or 0)),
            renta_neta_anual=(
                Decimal(str(cuerpo["renta_neta_anual"]))
                if cuerpo.get("renta_neta_anual") is not None
                else None
            ),
            margen_bruto=(
                Decimal(str(cuerpo["margen_bruto"]))
                if cuerpo.get("margen_bruto") is not None
                else None
            ),
            actividad=cuerpo.get("actividad") or "",
            figura_fiscal=cuerpo.get("figura_fiscal") or "",
        )

        try:
            out = _respuesta_determinista(ctx, pregunta)
        except Exception as e:  # noqa: BLE001
            self._json(500, {"error": f"{type(e).__name__}: {e}"})
            return

        self._json(200, out)


if __name__ == "__main__":
    puerto = int(os.environ.get("PUERTO", "8811"))
    ThreadingHTTPServer(("127.0.0.1", puerto), Handler).serve_forever()
