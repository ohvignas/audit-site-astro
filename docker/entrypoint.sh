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
Résultat : ./audits/<domaine>/<date>/RAPPORT-BRUT.md  (+ data/ pour l'agent IA, + CORRECTIONS/ à remettre à un agent de code)
TXT
}
case "${1:-}" in ""|-h|--help|help) usage; exit 0;; esac
URL="$1"
case "$URL" in http://*|https://*) ;; *) URL="https://$URL";; esac
PROJ=""
[ -f /projet/package.json ] && PROJ=/projet
HOST=$(printf '%s' "$URL" | awk -F/ '{print $3}')
AUDIT="/audits/$HOST/$(date +%F)"
export AUDIT_DANS_DOCKER=1  # corrections.py : commande de relance au format « docker run » (les chemins du conteneur sont inutilisables sur l'hôte)
bash /app/scripts/collect_all.sh "$URL" "$PROJ" "$AUDIT"
code=$?
echo
if [ "$code" = 2 ]; then
  echo "❌ Audit annulé : site injoignable ou page d'accueil en erreur 5xx (voir audits/$HOST/$(date +%F)/data/COLLECTE.md)"
else
  echo "📄 Rapport : audits/$HOST/$(date +%F)/RAPPORT-BRUT.md"
  [ -f "$AUDIT/RAPPORT.html" ] && echo "🌐 Page web : audits/$HOST/$(date +%F)/RAPPORT.html"
  [ -f "$AUDIT/RAPPORT.pdf" ] && echo "📕 PDF : audits/$HOST/$(date +%F)/RAPPORT.pdf"
  # CORRECTIONS/ ou, si un suivi y est commencé (ou .garder), CORRECTIONS-<horodatage>/.
  # Le nom réellement écrit est dans data/corrections-dossier.txt (validé) ; à défaut, on retombe sur le tri alphabétique.
  CORR=""
  P=$(head -n 1 "$AUDIT/data/corrections-dossier.txt" 2>/dev/null | head -c 64)
  if printf '%s\n' "$P" | grep -Eq '^CORRECTIONS(-[0-9TZ:-]+)?$' && [ -f "$AUDIT/$P/LISEZ-MOI.md" ]; then CORR="$P"; fi
  [ -z "$CORR" ] && for c in "$AUDIT"/CORRECTIONS*/; do [ -f "${c}LISEZ-MOI.md" ] && CORR=$(basename "$c"); done
  [ -n "$CORR" ] && echo "🛠️ Corrections : audits/$HOST/$(date +%F)/$CORR/"
  [ -f "/audits/$HOST/index.html" ] && echo "📈 Historique : audits/$HOST/index.html"
  echo "🤖 Rapport priorisé avec correctifs : ouvrir le dossier dans Claude Code et lancer /audit-site-astro:audit-complet"
fi
exit $code
