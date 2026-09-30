#!/usr/bin/env bash
# rapport_pdf.sh — Imprime DOSSIER_AUDIT/RAPPORT.html en DOSSIER_AUDIT/RAPPORT.pdf (A4) avec Chrome headless.
# Usage : bash rapport_pdf.sh DOSSIER_AUDIT
# Codes : 0 ok, 1 échec d'impression, 2 Chrome introuvable, 3 RAM insuffisante (MIN_FREE_MB, défaut 800).
# Variables : CHROME_PATH (binaire Chrome/Chromium), MIN_FREE_MB,
#             AUDIT_NO_CHROME_DISCOVERY=1 (tests uniquement : désactive la recherche automatique de Chrome).
set -u
AUDIT="${1:?usage: rapport_pdf.sh DOSSIER_AUDIT}"
HTML="$AUDIT/RAPPORT.html"
PDF="$AUDIT/RAPPORT.pdf"
DIR="$(cd "$(dirname "$0")" && pwd)"

if [ ! -f "$HTML" ]; then
  python3 "$DIR/rapport_html.py" "$AUDIT" || { echo "❌ RAPPORT.html absent et impossible à générer"; exit 1; }
fi

if [ -z "${CHROME_PATH:-}" ] && [ "${AUDIT_NO_CHROME_DISCOVERY:-0}" != "1" ]; then
  for c in "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
           "$(command -v chromium 2>/dev/null || true)" "$(command -v chromium-browser 2>/dev/null || true)" \
           "$(command -v google-chrome 2>/dev/null || true)" "$(command -v google-chrome-stable 2>/dev/null || true)"; do
    if [ -n "$c" ] && [ -x "$c" ]; then CHROME_PATH="$c"; break; fi
  done
fi
if [ -z "${CHROME_PATH:-}" ] || [ ! -x "$CHROME_PATH" ]; then
  echo "❌ Chrome introuvable (définir CHROME_PATH)"; exit 2
fi

free_mb() {
  if [ -r /proc/meminfo ]; then awk '/MemAvailable/ {print int($2 / 1024)}' /proc/meminfo
  elif command -v vm_stat >/dev/null 2>&1; then
    local ps; ps=$(sysctl -n hw.pagesize 2>/dev/null || echo 4096)
    vm_stat | awk -v ps="$ps" '/Pages free/ {gsub(/\./, "", $3); f=$3} /Pages inactive/ {gsub(/\./, "", $3); i=$3}
                               /Pages speculative/ {gsub(/\./, "", $3); s=$3} END {print int((f + i + s) * ps / 1048576)}'
  else echo 99999; fi
}
LIBRE=$(free_mb)
if [ "${LIBRE:-0}" -lt "${MIN_FREE_MB:-800}" ]; then
  echo "⛔ RAM insuffisante pour imprimer le PDF (${LIBRE:-0} Mo libres)"; exit 3
fi

# URL file:// correctement encodée (le dossier peut contenir des espaces : « Application Support »).
URL=$(python3 -c "import pathlib,sys;print(pathlib.Path(sys.argv[1]).resolve().as_uri())" "$HTML") \
  || { echo "❌ impossible de construire l'URL de $HTML"; exit 1; }

PROFIL=$(mktemp -d)
ERR="$PROFIL/chrome.err"
trap 'rm -rf "$PROFIL"' EXIT
rm -f "$PDF"   # ne jamais valider un PDF périmé
"$CHROME_PATH" --headless=new --no-sandbox --disable-gpu --disable-dev-shm-usage --disable-extensions \
  --no-first-run --user-data-dir="$PROFIL" --no-pdf-header-footer --print-to-pdf="$PDF" \
  "$URL" >/dev/null 2>"$ERR"
code=$?
if [ -s "$PDF" ] && head -c 5 "$PDF" | grep -q '%PDF-'; then echo "✅ $PDF"; exit 0; fi
echo "❌ impression PDF échouée (Chrome : code $code, $CHROME_PATH)"
[ -s "$ERR" ] && tail -n 5 "$ERR"
exit 1
