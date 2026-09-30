#!/usr/bin/env bash
# collect_all.sh — Lance TOUTE la collecte d'un audit en une commande, tolérante aux erreurs.
#
# Usage : bash collect_all.sh https://site.fr [CHEMIN_PROJET] [DOSSIER_AUDIT]
#   CHEMIN_PROJET : racine du repo Astro (optionnel : sans lui, audit « vu de l'extérieur » seulement)
#   DOSSIER_AUDIT : défaut ~/audits-site/<hôte>/<AAAA-MM-JJ> — HORS du dossier servi par le serveur web
# Variables : MAX_PAGES (500), LH_PAGES (5), RUNS (1), BUILD=1 pour le build d'audit, PSI_API_KEY (option),
#             MIN_FREE_MB (1200 : RAM minimale avant chaque Chrome)
# Les étapes tournent UNE PAR UNE (jamais en parallèle) : l'empreinte mémoire reste < ~1 Go (Chrome pendant Lighthouse).
#
# Produit DOSSIER_AUDIT/data/* + DOSSIER_AUDIT/data/COLLECTE.md (statut de chaque étape).
set -u
URL="${1:?usage: collect_all.sh https://site.fr [chemin_projet] [dossier_audit]}"
PROJ="${2:-}"
HOST=$(printf '%s' "$URL" | awk -F/ '{print $3}')
AUDIT="${3:-$HOME/audits-site/$HOST/$(date +%F)}"
DIR="$(cd "$(dirname "$0")" && pwd)"
D="$AUDIT/data"
mkdir -p "$D" "$AUDIT/rapports"
LOG="$D/COLLECTE.md"
echo "# Collecte — $URL — $(date '+%Y-%m-%d %H:%M')" > "$LOG"
echo >> "$LOG"
echo "| Étape | Statut | Durée | Sortie |" >> "$LOG"
echo "|---|---|---|---|" >> "$LOG"

step() {  # $1 nom, $2 sortie principale, reste = commande
  local name="$1" out="$2"; shift 2
  local t0=$(date +%s)
  echo "▶ $name…"
  "$@" > "$D/.log-$name.txt" 2>&1
  local code=$?
  local st="✅"; [ $code -ne 0 ] && st="⚠️ code $code (voir data/.log-$name.txt)"
  [ -n "$out" ] && [ ! -e "$out" ] && st="❌ sortie absente (voir data/.log-$name.txt)"
  echo "| $name | $st | $(( $(date +%s) - t0 )) s | ${out#$AUDIT/} |" >> "$LOG"
  echo "  $st"
}

step http "$D/http/http-checks.md" bash "$DIR/http_checks.sh" "$URL" "$D/http"
step crawl "$D/crawl/pages.json" python3 "$DIR/crawl_site.py" "$URL" --out "$D/crawl" \
     --max-pages "${MAX_PAGES:-500}" --delay 0.3 --check-images 200
step geo "$D/geo/geo.json" python3 "$DIR/geo_check.py" "$URL" --out "$D/geo" --crawl "$D/crawl/pages.json" --sample 12
step securite "$D/securite/security-probe.md" bash "$DIR/security_probe.sh" "$URL" "$D/securite"

# Pages Lighthouse : accueil + pages indexables les plus liées de gabarits différents
python3 - "$D/crawl/pages.json" "$URL" "${LH_PAGES:-5}" > "$D/lighthouse-urls.txt" <<'PY'
import json, sys
from urllib.parse import urlparse
home, n = sys.argv[2], int(sys.argv[3])
try:
    pages = json.load(open(sys.argv[1]))["pages"]
except Exception:
    print(home); sys.exit()
idx = sorted((p for p in pages if p.get("indexable")), key=lambda p: -(p.get("inlinks") or 0))
out, segs = [pages[0]["url"] if pages else home], set()
for p in idx:
    seg = urlparse(p["url"]).path.strip("/").split("/")[0]
    if seg and seg not in segs and p["url"] not in out:
        out.append(p["url"]); segs.add(seg)
    if len(out) >= n:
        break
print("\n".join(out))
PY
if [ -n "${PSI_API_KEY:-}" ]; then
  step pagespeed "$D/perf/pagespeed.json" python3 "$DIR/pagespeed.py" psi --out "$D/perf" --urls-file "$D/lighthouse-urls.txt"
else
  step lighthouse "$D/perf/pagespeed.json" bash "$DIR/lighthouse_run.sh" "$D/perf" --file "$D/lighthouse-urls.txt"
fi

if [ -n "$PROJ" ]; then
  if [ "${BUILD:-0}" = "1" ]; then
    step projet "$D/code/project-checks.md" bash "$DIR/project_checks.sh" "$PROJ" "$D/code" --build
    DIST_ARG="--dist $D/code/build/client/_astro"
    [ -d "$D/code/build/client/_astro" ] || DIST_ARG="--dist $D/code/build/_astro"
  else
    step projet "$D/code/project-checks.md" bash "$DIR/project_checks.sh" "$PROJ" "$D/code"
    DIST_ARG=""
  fi
  # shellcheck disable=SC2086
  step code "$D/code/code-scan.json" python3 "$DIR/astro_scan.py" "$PROJ" --out "$D/code" $DIST_ARG
else
  echo "| projet / code | ⏭️ ignoré (pas de chemin projet) | | |" >> "$LOG"
fi

python3 "$DIR/rapport_brut.py" "$AUDIT" 2>/dev/null && echo "| rapport brut | ✅ | | RAPPORT-BRUT.md |" >> "$LOG"
echo >> "$LOG"
echo "Dossier d'audit : \`$AUDIT\`" >> "$LOG"
echo
cat "$LOG"
