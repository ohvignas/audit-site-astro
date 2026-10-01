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
  -e AUDIT_IMAGE_DISTANTE=http://images.cobaye.test/cobaye.png \
  -e AUDIT_LIENS_PRIVES=1 \
  -v "$RACINE/audits-cobaye:/audits" -v "$RACINE/tests/cobaye/$V:/projet:ro" \
  --entrypoint bash "$IMAGE" /app/scripts/collect_all.sh "https://$V.cobaye.test/" /projet "/audits/$V"
code=$?
echo "Collecte $V terminée (code $code)"
# Seul le code 0 passe. Code 1 = au moins une étape ❌ (sortie absente ou inexploitable) : cela ne doit
# arriver sur aucun des deux jumeaux, sinon la mesure est faussée (un propre en panne « ressemble » à un propre sans faux positif).
# Codes 2 (site injoignable ou accueil en 5xx) et docker 125/126/127 = panne d'infrastructure. Dans tous les cas on remonte le code.
[ "$code" -ne 0 ] && { echo "❌ collecte $V incomplète (code $code)"; exit "$code"; }
exit 0
