#!/usr/bin/env bash
# Lance l'image d'audit sur un cobaye : bash tests/cobaye/auditer.sh casse|propre
set -uo pipefail
V="${1:?usage: auditer.sh casse|propre}"
RACINE="$(cd "$(dirname "$0")/../.." && pwd)"
IMAGE="${IMAGE_AUDIT:-audit-site-astro:test}"
mkdir -p "$RACINE/audits-cobaye"
docker run --rm --network cobaye --memory=2g \
  -e AUDIT_INSECURE_TLS=1 -e MAX_PAGES=200 -e LH_PAGES=4 \
  -v "$RACINE/audits-cobaye:/audits" -v "$RACINE/tests/cobaye/$V:/projet:ro" \
  --entrypoint bash "$IMAGE" /app/scripts/collect_all.sh "https://$V.cobaye.test/" /projet "/audits/$V"
code=$?
echo "Collecte $V terminée (code $code)"
exit 0   # le verdict vient de score.py, pas du code de collecte (le cobaye cassé a des étapes ❌ légitimes)
