#!/usr/bin/env python3
"""Crea un indice en una coleccion de OpenSearch Serverless.

POR QUE ESTE SCRIPT
------------------
Al crear la Knowledge Base de Bedrock, el servicio valida el acceso a la
coleccion de vectores PROBANDO el indice "default". Si no existe, la
creacion falla con:

    ValidationException: The knowledge base storage configuration provided
    is invalid... Dependency error document status code: 404, error
    message: no such index [default]

Es decir: la coleccion tiene que tener un indice llamado "default" ANTES
de que se pueda crear la KB.

Lo llama el provisioner "local-exec" del recurso null_resource.indice_default
de terraform/main.tf.

FIRMA
-----
La peticion va firmada con SigV4 para el servicio "aoss". Se usa
opensearch-py (AWSV4SignerAuth), que es la implementacion de referencia.

Firmar a mano con botocore es fragile: la API cambia entre versiones
(add_auth, add_headers, _inject_signature_to_request...) y el resultado es
un 403 dificil de diagnosticar. Con opensearch-py funciona a la primera.

Es idempotente: si el indice ya existe, lo dice y sale con 0.
"""

from __future__ import annotations

import json
import os
import sys

CUERPO = {
    "settings": {
        "index": {
            "knn": True,
            "knn.algo_param.ef_search": 512,
            # 1536 es la dimension del amazon.titan-embed-text-v2:0, que es
            # el modelo de embeddings que usa la KB.
            "knn.algo_param.space_type": "l2",
        }
    }
}


def main() -> int:
    if len(sys.argv) < 2:
        print("uso: crear_indice_opensearch.py <endpoint> [indice]", file=sys.stderr)
        return 2

    endpoint = sys.argv[1].rstrip("/")
    indice = sys.argv[2] if len(sys.argv) > 2 else "default"
    region = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "us-east-1"

    try:
        import boto3
        from opensearchpy import OpenSearch
        from opensearchpy.helpers import AWSV4SignerAuth
    except ImportError as e:  # pragma: no cover
        print(f"faltan dependencias (opensearch-py): {e}", file=sys.stderr)
        return 1

    host = endpoint.replace("https://", "").replace("http://", "").split("/")[0]
    if not host:
        print("endpoint invalido", file=sys.stderr)
        return 1

    credenciales = boto3.Session().get_credentials()
    if credenciales is None:
        print("no hay credenciales AWS en el entorno", file=sys.stderr)
        return 1

    cliente = OpenSearch(
        hosts=[{"host": host, "port": 443}],
        http_compress=True,
        use_ssl=True,
        verify_certs=False,
        ssl_show_warn=False,
        auth=AWSV4SignerAuth(credenciales, "aoss", region),
        timeout=90,
    )

    try:
        cliente.indices.create(index=indice, body=CUERPO)
        print(f"indice {indice} creado")
        return 0
    except Exception as e:  # noqa: BLE001
        cuerpo = getattr(e, "info", None)
        detalle = ""
        if cuerpo:
            try:
                detalle = json.dumps(json.loads(cuerpo))
            except Exception:
                detalle = str(cuerpo)
        # Si ya existe, es un exito: el objetivo es que exista.
        if "resource_already_exists_exception" in (detalle + str(e)):
            print(f"el indice {indice} ya existia")
            return 0
        print(f"no se pudo crear el indice {indice}: {type(e).__name__}: {e}", file=sys.stderr)
        if detalle:
            print(detalle[:900], file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
