#!/usr/bin/env bash
# lighthouse_run.sh — Lance Lighthouse (Chrome headless) en mobile ET desktop sur une liste d'URL,
# puis produit la synthèse via pagespeed.py parse.
#
# Usage : bash lighthouse_run.sh DOSSIER_SORTIE URL [URL…]
#         bash lighthouse_run.sh DOSSIER_SORTIE --file liste_urls.txt
#
# Chrome : utilise CHROME_PATH s'il est défini, sinon Chrome/Chromium installé.
# Serveur sans Chrome :  npx -y @puppeteer/browsers install chrome-headless-shell@stable
#                        puis export CHROME_PATH=<chemin affiché>
# Chaque URL est mesurée RUNS fois (défaut 1 ; mettre RUNS=3 pour lisser la variance, la médiane est gardée).
#
# Garde-fou RAM : un Chrome headless consomme ~0,5 à 1 Go. Avant chaque mesure, le script vérifie la mémoire
# disponible (MIN_FREE_MB, défaut 1200). Si elle manque, il attend jusqu'à 2 min puis s'arrête proprement
# (les mesures déjà faites sont conservées) au lieu de faire swapper ou planter la machine.
# Les mesures sont toujours faites UNE PAR UNE : ne jamais lancer plusieurs lighthouse_run.sh en parallèle.
set -u
OUT="${1:?usage: lighthouse_run.sh DOSSIER_SORTIE URL [URL…] | --file liste.txt}"; shift
DIR="$(cd "$(dirname "$0")" && pwd)"
RUNS="${RUNS:-1}"
mkdir -p "$OUT/lighthouse"

if [ "${1:-}" = "--file" ]; then
  URLS=$(grep -E '^https?://' "$2")
else
  URLS="$*"
fi
[ -z "$URLS" ] && { echo "Aucune URL fournie"; exit 1; }

if [ -z "${CHROME_PATH:-}" ]; then
  for c in "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
           "$(command -v google-chrome 2>/dev/null)" "$(command -v google-chrome-stable 2>/dev/null)" \
           "$(command -v chromium 2>/dev/null)" "$(command -v chromium-browser 2>/dev/null)"; do
    [ -n "$c" ] && [ -x "$c" ] && { export CHROME_PATH="$c"; break; }
  done
fi
if [ -z "${CHROME_PATH:-}" ]; then
  echo "❌ Chrome introuvable. Installer : npx -y @puppeteer/browsers install chrome-headless-shell@stable"
  echo "   puis relancer avec CHROME_PATH=<chemin>. Alternative : pagespeed.py psi avec PSI_API_KEY."
  exit 2
fi
echo "Chrome : $CHROME_PATH"

FLAGS="--headless=new --no-sandbox --disable-gpu --disable-dev-shm-usage --disable-extensions --no-first-run --disable-background-networking --disable-sync --disable-default-apps --mute-audio"
MIN_FREE_MB="${MIN_FREE_MB:-1200}"

free_mb() {  # mémoire disponible sans swapper (Linux : MemAvailable ; macOS : free + inactive + speculative)
  if [ -r /proc/meminfo ]; then
    awk '/MemAvailable/ {print int($2 / 1024)}' /proc/meminfo
  elif command -v vm_stat >/dev/null 2>&1; then
    local ps; ps=$(sysctl -n hw.pagesize 2>/dev/null || echo 4096)
    vm_stat | awk -v ps="$ps" '/Pages free/ {gsub(/\./, "", $3); f=$3} /Pages inactive/ {gsub(/\./, "", $3); i=$3}
                               /Pages speculative/ {gsub(/\./, "", $3); s=$3} END {print int((f + i + s) * ps / 1048576)}'
  else
    echo 99999
  fi
}

wait_for_ram() {  # 0 = ok, 1 = abandon
  local tries=0 avail
  while :; do
    avail=$(free_mb)
    [ "$avail" -ge "$MIN_FREE_MB" ] && return 0
    [ $tries -ge 12 ] && { echo "  ⛔ RAM insuffisante ($avail Mo dispo < $MIN_FREE_MB Mo) — arrêt de Lighthouse pour protéger la machine."
                           echo "     Fermer des applications (navigateurs, IDE, Docker Desktop) puis relancer, ou MIN_FREE_MB=800."; return 1; }
    [ $tries -eq 0 ] && echo "  ⏳ RAM basse ($avail Mo dispo) — attente…"
    tries=$((tries + 1)); sleep 10
  done
}
pkill_orphans() {  # tue les Chrome headless orphelins laissés par un Lighthouse interrompu (seulement ceux de lighthouse)
  pkill -f -- '--headless=new.*--disable-dev-shm-usage' 2>/dev/null || true
}
trap pkill_orphans EXIT INT TERM
echo "RAM disponible au départ : $(free_mb) Mo (seuil $MIN_FREE_MB Mo)"
# lighthouse installé globalement (image Docker) sinon npx
if command -v lighthouse >/dev/null 2>&1; then LH="lighthouse"; else LH="npx -y lighthouse@12"; fi
for url in $URLS; do
  slug=$(printf '%s' "$url" | sed -E 's#https?://##; s#[^A-Za-z0-9]+#_#g; s#_+$##' | cut -c1-80)
  for mode in mobile desktop; do
    extra=""; [ "$mode" = "desktop" ] && extra="--preset=desktop"
    for run in $(seq 1 "$RUNS"); do
      dest="$OUT/lighthouse/${mode}-${slug}-run${run}.json"
      wait_for_ram || break 3
      echo "→ $mode #$run $url"
      $LH "$url" $extra --quiet --output=json --output-path="$dest" \
        --only-categories=performance,accessibility,best-practices,seo \
        --chrome-flags="$FLAGS" --max-wait-for-load=60000 --locale=fr >/dev/null 2>"$dest.log" \
        || echo "  ⚠️ échec (voir $dest.log)"
      [ -s "$dest" ] && rm -f "$dest.log"
    done
    # plusieurs passages : ne garder que le passage médian (score perf) pour la synthèse
    if [ "$RUNS" -gt 1 ]; then
      med=$(for f in "$OUT/lighthouse/${mode}-${slug}"-run*.json; do
              python3 -c "import json,sys;d=json.load(open(sys.argv[1]));print(d['categories']['performance']['score'],sys.argv[1])" "$f" 2>/dev/null
            done | sort -n | awk '{a[NR]=$2} END{print a[int((NR+1)/2)]}')
      for f in "$OUT/lighthouse/${mode}-${slug}"-run*.json; do [ "$f" != "$med" ] && mv "$f" "${f%.json}.json.extra"; done
    fi
  done
done
python3 "$DIR/pagespeed.py" parse --out "$OUT" "$OUT/lighthouse"
