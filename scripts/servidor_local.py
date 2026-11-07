#!/usr/bin/env python3
"""Servidor local del front CON proxy a /api.

Por que no vale un "python3 -m http.server"
--------------------------------------------
El front llama a CFG.apiUrl + "/preguntar". En produccion CFG.apiUrl es
"/api" y hay un proxy de nginx que reenvia a API Gateway (y pone la
API key, que no viaja al navegador).

Con un http.server pelado, POST /api/preguntar devuelve 501 y el test
del front falla. Este servidor hace lo mismo que el proxy de nginx:

    /api/*  ->  https://<api-gateway>/...   (con x-api-key)
    /*      ->  los ficheros del front

Asi el test del front ejercita la IA REAL, no un mock: es el mismo
camino que en produccion.

Uso:
    python3 scripts/servidor_local.py --puerto 8899 --api-url https://xxx/ --api-key KEY

Si no se pasan --api-url/--api-key, busca la configuracion en el output
de Terraform (frontend_url_config) y, si no hay, sirve el front sin
proxy (el front cae en modo demo).
"""

from __future__ import annotations

import argparse
import http.server
import json
import os
import shutil
import ssl
import subprocess
import sys
import urllib.error
import urllib.request

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONT = os.path.join(RAIZ, "frontend")

API_URL = ""
API_KEY = ""


class ProxyHandler(http.server.SimpleHTTPRequestHandler):
    """Sirve el front y hace de proxy para /api."""

    def __init__(self, *a, **kw):
        super().__init__(*a, directory=FRONT, **kw)

    def log_message(self, format, *args):  # silencioso  # noqa: A002
        pass

    # --- el proxy ------------------------------------------------------
    def _proxy(self):
        if not API_URL:
            self.send_error(503, "Sin API configurada: el front va en modo demo.")
            return

        path = self.path[len("/api"):] or "/"
        destino = API_URL.rstrip("/") + path

        longitud = int(self.headers.get("Content-Length") or 0)
        cuerpo = self.rfile.read(longitud) if longitud else None

        peticion = urllib.request.Request(destino, data=cuerpo, method=self.command)
        peticion.add_header("Content-Type", self.headers.get("Content-Type", "application/json"))
        if API_KEY:
            # La clave va aqui, en el servidor: nunca viaja al navegador.
            peticion.add_header("x-api-key", API_KEY)

        try:
            with urllib.request.urlopen(peticion, timeout=90) as r:
                datos = r.read()
                self.send_response(r.status)
                ctype = r.headers.get("Content-Type", "application/json")
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(datos)))
                self.end_headers()
                self.wfile.write(datos)
        except urllib.error.HTTPError as e:
            datos = e.read()
            self.send_response(e.code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(datos)))
            self.end_headers()
            self.wfile.write(datos)
        except Exception as e:  # noqa: BLE001
            msg = json.dumps({"error": f"Proxy error: {type(e).__name__}: {e}"}).encode()
            self.send_response(502)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(msg)))
            self.end_headers()
            self.wfile.write(msg)

    def _es_api(self):
        return self.path.startswith("/api")

    def do_GET(self):
        if self._es_api():
            self._proxy()
        else:
            super().do_GET()

    def do_POST(self):
        if self._es_api():
            self._proxy()
        else:
            self.send_error(405, "Method Not Allowed")

    def do_PUT(self):
        self._proxy() if self._es_api() else self.send_error(405, "Method Not Allowed")

    def do_DELETE(self):
        self._proxy() if self._es_api() else self.send_error(405, "Method Not Allowed")


def config_de_terraform():
    """Lee la config de la API del output de Terraform (si esta disponible).

    El output "frontend_url_config" es sensitive: Terraform lo devuelve
    como un STRING JSON dentro del JSON, asi que hay que desempaquetar dos
    veces.
    """
    tf = shutil.which("terraform") or "/data/cache/scratch/tfbin/terraform"
    if not os.path.exists(tf):
        return "", ""
    try:
        r = subprocess.run(
            [tf, "-chdir", os.path.join(RAIZ, "terraform"), "output", "-json",
             "frontend_url_config"],
            capture_output=True, text=True, timeout=90,
        )
        if r.returncode != 0 or not r.stdout.strip():
            return "", ""
        cfg = json.loads(r.stdout)
        if isinstance(cfg, str):
            cfg = json.loads(cfg)
        if not isinstance(cfg, dict):
            return "", ""
        return cfg.get("api_url") or "", cfg.get("api_key") or ""
    except Exception:  # noqa: BLE001
        return "", ""


def main():
    global API_URL, API_KEY

    ap = argparse.ArgumentParser()
    ap.add_argument("--puerto", type=int, default=8899)
    ap.add_argument("--api-url", default="")
    ap.add_argument("--api-key", default="")
    args = ap.parse_args()

    API_URL = args.api_url
    API_KEY = args.api_key

    if not API_URL:
        API_URL, API_KEY = config_de_terraform()

    servidor = http.server.ThreadingHTTPServer(("127.0.0.1", args.puerto), ProxyHandler)
    if API_URL:
        print(f"  servidor local en http://localhost:{args.puerto}/  (proxy /api -> {API_URL})")
    else:
        print(f"  servidor local en http://localhost:{args.puerto}/  (modo demo: sin API)")
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
