#!/usr/bin/env python3
"""Publica el front en S3 con los Content-Type correctos.

POR QUE NO BASTA CON "aws s3 sync"
    El CLI de S3 no infiere el Content-Type a partir de la extension: si
    el objeto no existe, lo crea con application/octet-stream. Con eso,
    el navegador NO muestra el .html, lo descarga. Es un fallo silencioso
    que parece un problema de JS y en realidad es una cabecera.

    CloudFront no lo arregla: sirve lo que hay en S3.

QUE HACE ESTE SCRIPT
    Sube cada fichero con su Content-Type y su Cache-Control:

      .html  text/html; charset=utf-8          (max-age 60, se relee)
      .js    application/javascript              (max-age 300, versionado)
      .css   text/css; charset=utf-8            (max-age 300, versionado)
      .json  application/json                    (max-age 300)
      .svg   image/svg+xml                       (max-age 300)
      .png   image/png                           (max-age 300)
      .csv   text/csv; charset=utf-8             (max-age 300)

    Los .html casi sin cache: el front se cambia justo antes de una
    demo y no quiero que un visitante vea la version anterior.

    Usa la API de S3 (boto3 si esta disponible, si no la CLI) para poder
    forzar el metadata de objetos que ya existen.

USO
    python3 scripts/sync_front_s3.py <bucket> [--frontend frontend/]
"""

from __future__ import annotations

import mimetypes
import os
import subprocess
import sys
from pathlib import Path

# Content-Type por extension. Los que mimetypes no deduce bien (o no
# deduce) estan aqui explicitamente.
CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".htm": "text/html; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".mjs": "application/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".ico": "image/x-icon",
    ".csv": "text/csv; charset=utf-8",
    ".txt": "text/plain; charset=utf-8",
    ".pdf": "application/pdf",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
    ".map": "application/json",
}

# El HTML se relee siempre: el front cambia justo antes de una demo.
CACHE_HTML = "no-cache, must-revalidate"
CACHE_OTROS = "max-age=300"

# Lo que NO se publica desde aqui.
EXCLUIDOS = ("generar_demo_data.py", "normativa/", "assets/mb/")


def content_type(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in CONTENT_TYPES:
        return CONTENT_TYPES[ext]
    guessed, _ = mimetypes.guess_type(str(path))
    return guessed or "application/octet-stream"


def cache_control(path: Path) -> str:
    return CACHE_HTML if path.suffix.lower() in (".html", ".htm") else CACHE_OTROS


def ficheros(frontend: Path) -> list[Path]:
    out = []
    for root, dirs, files in os.walk(frontend):
        dirs[:] = [d for d in dirs if d not in (".terraform", "__pycache__", "tests", ".git")]
        for name in files:
            rel = (Path(root) / name).relative_to(frontend)
            posix = rel.as_posix()
            if any(posix.startswith(x) or posix == x for x in EXCLUIDOS):
                continue
            out.append(rel)
    return sorted(out)


def subir(bucket: str, frontend: Path, rel: Path) -> bool:
    """Sube un fichero con su Content-Type. True si se subio."""
    origen = frontend / rel
    ct = content_type(origen)
    cc = cache_control(origen)
    destino = f"s3://{bucket}/{rel.as_posix()}"

    cmd = [
        "aws", "s3api", "copy-object",
        "--bucket", bucket,
        "--key", rel.as_posix(),
        "--copy-source", f"{bucket}/{rel.as_posix()}",
        "--metadata-directive", "REPLACE",
        "--content-type", ct,
        "--cache-control", cc,
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode == 0:
        return True

    # Si el objeto no existe todavia, copy-object falla: se sube.
    r2 = subprocess.run(
        ["aws", "s3", "cp", str(origen), destino,
         "--content-type", ct, "--cache-control", cc, "--no-progress"],
        capture_output=True, text=True,
    )
    return r2.returncode == 0


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        print("uso: sync_front_s3.py <bucket> [--frontend frontend/]", file=sys.stderr)
        return 2
    bucket = args[0]

    frontend = Path("frontend")
    if "--frontend" in sys.argv:
        i = sys.argv.index("--frontend")
        if i + 1 < len(sys.argv):
            frontend = Path(sys.argv[i + 1])

    if not frontend.is_dir():
        print(f"ERROR: no existe {frontend}/", file=sys.stderr)
        return 1

    subs = ficheros(frontend)
    print(f"    {len(subs)} ficheros, con Content-Type explicito")

    fallos = []
    for rel in subs:
        if not subir(bucket, frontend, rel):
            fallos.append(rel.as_posix())

    if fallos:
        print(f"    AVISO: {len(fallos)} ficheros no se pudieron subir:", file=sys.stderr)
        for f in fallos[:5]:
            print(f"      {f}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
