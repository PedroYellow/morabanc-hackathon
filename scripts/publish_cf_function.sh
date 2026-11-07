#!/usr/bin/env bash
# Publica la CloudFront Function si ha quedado en stage DEVELOPMENT.
#
# POR QUE HACE FALTA
#     Terraform NO publica las CloudFront Functions: las crea y las
#     modifica en stage DEVELOPMENT, y ahi no se ejecutan. Cada
#     "terraform apply" deja la funcion sin publicar, y sin publicar la
#     API responde 403 porque no llega la x-api-key al authorizer.
#
#     Este script se ejecuta tras cada apply (scripts/deploy_front.sh)
#     y tambien de forma periodica, por si otro apply lo revierte.
set -u

source /data/cache/scratch/aws_env.sh 2>/dev/null || true
export PATH="$PATH:/data/cache/scratch/awscli/bin:/data/cache/scratch/awscli/v2/current"

FN="mora-inject-api-key"

etag=$(aws cloudfront describe-function --name "$FN" --query ETag --output text 2>/dev/null || echo "")
if [ -z "$etag" ] || [ "$etag" = "None" ]; then
  echo "publish-cf-function: no se pudo leer el ETag de $FN"
  exit 0
fi

# Si ya esta LIVE y con el ETag actual, no hay nada que hacer.
stage=$(aws cloudfront describe-function --name "$FN" \
          --query 'FunctionSummary.FunctionMetadata.Stage' --output text 2>/dev/null || echo "")
if [ "$stage" = "LIVE" ]; then
  echo "publish-cf-function: $FN ya esta LIVE"
  exit 0
fi

aws cloudfront publish-function --name "$FN" --if-match "$etag" >/dev/null 2>&1
if [ $? -eq 0 ]; then
  echo "publish-cf-function: $FN publicada (LIVE)"
else
  echo "publish-cf-function: no se pudo publicar $FN"
fi
