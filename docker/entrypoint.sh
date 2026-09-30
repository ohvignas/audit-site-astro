#!/usr/bin/env bash
# Point d'entrée Docker : docker run … audit-site-astro https://site.fr
set -u
usage() {
  cat <<'TXT'
Audit Site Astro — collecte complète (SEO technique, GEO/IA, performance Lighthouse, HTTP, sécurité, code)

  docker run --rm -v "$PWD/audits:/audits" audit-site-astro https://votre-site.fr

Option — analyser aussi le code (lecture seule) :
  docker run --rm -v "$PWD/audits:/audits" -v /chemin/du/projet:/projet:ro audit-site-astro https://votre-site.fr

Variables : -e MAX_PAGES=500  -e LH_PAGES=5  -e RUNS=3  -e PSI_API_KEY=…  -e SKIP_LIGHTHOUSE=1  -e SKIP_PDF=1
Résultat : ./audits/<domaine>/<date>/RAPPORT-BRUT.md  (+ data/ pour l'agent IA)
TXT
}
case "${1:-}" in ""|-h|--help|help) usage; exit 0;; esac
URL="$1"
case "$URL" in http://*|https://*) ;; *) URL="https://$URL";; esac
PROJ=""
[ -f /projet/package.json ] && PROJ=/projet
HOST=$(printf '%s' "$URL" | awk -F/ '{print $3}')
AUDIT="/audits/$HOST/$(date +%F)"
bash /app/scripts/collect_all.sh "$URL" "$PROJ" "$AUDIT"
code=$?
echo
if [ "$code" = 2 ]; then
  echo "❌ Audit annulé : site injoignable ou page d'accueil en erreur 5xx (voir audits/$HOST/$(date +%F)/data/COLLECTE.md)"
else
  echo "📄 Rapport : audits/$HOST/$(date +%F)/RAPPORT-BRUT.md"
  [ -f "$AUDIT/RAPPORT.html" ] && echo "🌐 Page web : audits/$HOST/$(date +%F)/RAPPORT.html"
  [ -f "$AUDIT/RAPPORT.pdf" ] && echo "📕 PDF : audits/$HOST/$(date +%F)/RAPPORT.pdf"
  [ -f "/audits/$HOST/index.html" ] && echo "📈 Historique : audits/$HOST/index.html"
  echo "🤖 Rapport priorisé avec correctifs : ouvrir le dossier dans Claude Code et lancer /audit-site-astro:audit-complet"
fi
exit $code
