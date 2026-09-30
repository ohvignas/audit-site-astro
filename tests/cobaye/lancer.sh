#!/usr/bin/env bash
# Démarre les deux cobayes. Prévu pour la CI : ≈ 3 Go de RAM (2 builds Astro + nginx).
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p nginx/certs
if [ ! -f nginx/certs/cobaye.crt ]; then
  openssl req -x509 -newkey rsa:2048 -nodes -days 30 -subj "/CN=cobaye.test" \
    -addext "subjectAltName=DNS:casse.cobaye.test,DNS:propre.cobaye.test" \
    -keyout nginx/certs/cobaye.key -out nginx/certs/cobaye.crt 2>/dev/null
fi
if [ -z "${CI:-}" ]; then
  echo "⚠️ Hors CI : ce script construit 2 sites Astro et lance nginx (≈ 3 Go de RAM). Ctrl+C dans les 5 s pour annuler."
  sleep 5
fi
docker compose up -d --build --wait
docker compose ps
