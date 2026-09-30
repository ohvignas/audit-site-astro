#!/usr/bin/env bash
# Lance l'image d'audit sur un cobaye : bash tests/cobaye/auditer.sh casse|propre
set -uo pipefail
V="${1:-}"
case "$V" in
  casse|propre) ;;
  *) echo "usage: auditer.sh casse|propre" >&2; exit 64 ;;
esac
RACINE="$(cd "$(dirname "$0")/../.." && pwd)"
IMAGE="${IMAGE_AUDIT:-audit-site-astro:test}"
mkdir -p "$RACINE/audits-cobaye"
rm -rf "$RACINE/audits-cobaye/$V"   # jamais de données périmées mélangées (V validé ci-dessus)
docker run --rm --network cobaye --memory=2g \
  -e AUDIT_INSECURE_TLS=1 -e MAX_PAGES=200 -e LH_PAGES=4 \
  -v "$RACINE/audits-cobaye:/audits" -v "$RACINE/tests/cobaye/$V:/projet:ro" \
  --entrypoint bash "$IMAGE" /app/scripts/collect_all.sh "https://$V.cobaye.test/" /projet "/audits/$V"
code=$?
echo "Collecte $V terminée (code $code)"
# code 1 = étapes ❌ légitimes (le cobaye cassé) : le verdict vient de score.py.
# code >= 2 (docker 125/126/127, collecte 2 = site injoignable) = panne d'infrastructure : on la remonte.
[ "$code" -ge 2 ] && { echo "❌ collecte $V impossible (code $code)"; exit "$code"; }
exit 0
