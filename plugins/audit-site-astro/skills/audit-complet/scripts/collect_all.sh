#!/usr/bin/env bash
# collect_all.sh — Lance TOUTE la collecte d'un audit en une commande.
#
# Usage : bash collect_all.sh https://site.fr [CHEMIN_PROJET] [DOSSIER_AUDIT]
#   CHEMIN_PROJET : racine du repo Astro (optionnel : sans lui, audit « vu de l'extérieur » seulement)
#   DOSSIER_AUDIT : défaut ~/audits-site/<hôte>/<AAAA-MM-JJ> — HORS du dossier servi par le serveur web
# Variables : MAX_PAGES (500), LH_PAGES (5), RUNS (1), BUILD=1 (build d'audit), PSI_API_KEY (option),
#             MIN_FREE_MB (1200), SKIP_LIGHTHOUSE=1, SKIP_PDF=1 (pas de RAPPORT.pdf ; implicite avec SKIP_LIGHTHOUSE=1),
#             CHROME_PATH (Chrome pour le PDF), AUDIT_INSECURE_TLS=1 (tests uniquement : certificat auto-signé),
#             FORCE_PDF=1 (tests uniquement : imprime le PDF même avec SKIP_LIGHTHOUSE=1),
#             DELAI_ETAPE (secondes par étape, défaut 1800 ; crawl : 1800 + 3 × MAX_PAGES ; code : 900 ;
#             lighthouse : 600 + 240 × LH_PAGES × RUNS, soit 1800 par défaut), DELAI_<ÉTAPE> (ex. DELAI_CODE=900,
#             DELAI_RAPPORT_HTML=600 : prioritaire sur DELAI_ETAPE). 0 = pas de délai maximal pour l'étape (ou, avec DELAI_ETAPE=0, pour toutes).
# Une étape qui dépasse son délai est arrêtée (elle et tous ses descendants : TERM, 5 s de grâce, puis KILL) et notée ❌ « délai dépassé ».
# Ctrl-C arrête l'étape en cours et ses processus enfants (Chrome, node, curl), puis la collecte (code 130).
# Fin de COLLECTE.md : « Dernières lignes des étapes en échec ou en avertissement » (15 lignes par étape, clés/jetons masqués).
# Un PDF impossible (Chrome absent, RAM insuffisante) est un avertissement ⚠️ et ne fait pas échouer la collecte.
# Étape « corrections » : écrit <dossier d'audit>/CORRECTIONS/ (voir corrections.py ; CORRECTIONS/.garder = ne pas l'écraser, le nouveau
# dossier est alors CORRECTIONS-<horodatage>/) et note son nom dans data/corrections-dossier.txt, que rapport_html.py et l'étape relisent.
# Dernière étape « historique » : régénère <dossier du site>/index.html (évolution des notes de tous les audits AAAA-MM-JJ du site).
# Les étapes tournent UNE PAR UNE : l'empreinte mémoire reste < ~1 Go (Chrome pendant Lighthouse).
#
# Codes de sortie : 0 = tout est ✅/⚠️/⏭️ ; 1 = au moins une étape ❌ ; 2 = pré-vol en échec : site injoignable
#                   ou page d'accueil en erreur 5xx (rien collecté).
set -u
URL="${1:?usage: collect_all.sh https://site.fr [chemin_projet] [dossier_audit]}"
PROJ="${2:-}"
HOST=$(printf '%s' "$URL" | awk -F/ '{print $3}')
AUDIT="${3:-$HOME/audits-site/$HOST/$(date +%F)}"
DIR="$(cd "$(dirname "$0")" && pwd)"
D="$AUDIT/data"
mkdir -p "$D" "$AUDIT/rapports"
LOG="$D/COLLECTE.md"
FAILS=0
curl() { if [ "${AUDIT_INSECURE_TLS:-}" = "1" ]; then command curl -k "$@"; else command curl "$@"; fi; }
. "$DIR/etapes.sh"
rm -f "$D/.erreurs-etapes.md" "$D"/.delai-*
trap interrompre_collecte INT TERM   # Ctrl-C : arrête l'étape en cours et ses descendants (Chrome, node, curl)

echo "# Collecte — $URL — $(date '+%Y-%m-%d %H:%M')" > "$LOG"
echo >> "$LOG"
echo "| Étape | Statut | Durée | Sortie |" >> "$LOG"
echo "|---|---|---|---|" >> "$LOG"

prevol() {
  local res code final
  res=$(curl -s -o /dev/null -L --max-redirs 10 --max-time 25 \
        -A "Mozilla/5.0 (compatible; AuditSiteAstro/1.2)" -w '%{http_code}|%{url_effective}' "$URL" 2>/dev/null)
  code=${res%%|*}; final=${res#*|}
  if [ -z "$code" ] || [ "$code" = "000" ]; then
    echo "| pré-vol | ❌ site injoignable (nom de domaine inexistant, certificat invalide, serveur arrêté ou délai dépassé) | | $URL |" >> "$LOG"
    echo "❌ $URL est injoignable : audit annulé. Vérifier l'adresse (https://…), le DNS et le certificat."
    return 2
  fi
  if [ "$code" -ge 500 ]; then
    echo "| pré-vol | ❌ la page d'accueil répond HTTP $code | | $final |" >> "$LOG"
    echo "❌ $URL répond HTTP $code : audit annulé."
    return 2
  fi
  if [ "$code" -ge 400 ]; then
    echo "| pré-vol | ⚠️ HTTP $code (pare-feu ? page protégée ?) — audit poursuivi | | $final |" >> "$LOG"
  else
    echo "| pré-vol | ✅ HTTP $code | | $final |" >> "$LOG"
  fi
  return 0
}

# Validateurs : une étape « réussie » doit aussi avoir produit quelque chose d'exploitable.
valid_aucun() { return 0; }
valid_crawl() {
  python3 -c "import json,sys; d=json.load(open(sys.argv[1])); sys.exit(0 if any(p.get('is_html') and p.get('final_status')==200 for p in d['pages']) else 1)" \
    "$D/crawl/pages.json" 2>/dev/null
}
valid_geo() {
  python3 -c "import json,sys; d=json.load(open(sys.argv[1])); sys.exit(0 if any(p.get('status')==200 for p in d['pages']) else 1)" \
    "$D/geo/geo.json" 2>/dev/null
}
# Étape corrections : le dossier à contrôler est celui que corrections.py a écrit (data/corrections-dossier.txt : une ligne,
# CORRECTIONS ou CORRECTIONS-<horodatage>, sans séparateur), et son index.json doit dater du début de l'étape (STEP_T0) :
# un ancien dossier conservé (.garder, suivi commencé) ou l'index d'une exécution précédente ne valide pas l'étape.
nom_corrections() {  # affiche le nom du dossier désigné par le pointeur, ou rien (code 1) s'il est absent ou invalide
  python3 - "$AUDIT" 2>/dev/null <<'PY'
import os, re, sys
try:
    with open(os.path.join(sys.argv[1], "data", "corrections-dossier.txt"), encoding="utf-8") as f:
        nom = f.read(256)
except (OSError, ValueError):
    sys.exit(1)
nom = nom[:-1] if nom.endswith("\n") else nom
if len(nom) > 64 or not re.fullmatch(r"CORRECTIONS(-[0-9TZ:-]+)?", nom):
    sys.exit(1)
print(nom)
PY
}
sortie_corrections() { echo "$AUDIT/$(nom_corrections || echo '(dossier inconnu)')/LISEZ-MOI.md"; }
valid_corrections() {
  local nom
  nom=$(nom_corrections) || return 1
  # 2 s de tolérance : horodatages à la seconde paire (exFAT/FAT, certains montages réseau)
  python3 -c "import os,sys; sys.exit(0 if os.stat(sys.argv[1]).st_mtime >= float(sys.argv[2]) - 2 else 1)" \
    "$AUDIT/$nom/index.json" "${STEP_T0:-0}" 2>/dev/null
}
valid_perf() {
  python3 -c "import json,sys; d=json.load(open(sys.argv[1])); sys.exit(0 if any(not r.get('erreur') for r in d) else 1)" \
    "$D/perf/pagespeed.json" 2>/dev/null
}

step() {  # $1 nom, $2 sortie principale ("@fonction" : nom de fonction qui l'affiche une fois la commande finie), $3 validateur, reste = commande
  local name="$1" out="$2" check="$3"; shift 3
  local t0; t0=$(date +%s)
  STEP_T0=$t0
  echo "▶ ${name}…"
  local delai; delai=$(delai_etape "$name")
  avec_delai "$delai" "$@" > "$D/.log-${name}.txt" 2>&1
  local code=$?
  case "$out" in @*) out=$("${out#@}");; esac
  local st="✅"
  [ $code -ne 0 ] && st="⚠️ code $code (voir data/.log-${name}.txt)"
  if [ $code -eq 124 ]; then
    st="❌ délai dépassé (${delai} s, voir data/.log-${name}.txt)"
  elif [ -n "$out" ] && [ ! -e "$out" ]; then
    st="❌ sortie absente (voir data/.log-${name}.txt)"
  elif [ -n "$out" ] && [ -f "$out" ] && [ ! -s "$out" ]; then
    st="❌ sortie vide, 0 octet (disque plein ? voir data/.log-${name}.txt)"
  elif ! "$check"; then
    st="❌ résultat vide ou inexploitable (voir data/.log-${name}.txt)"
  fi
  if [ "$st" = "✅" ]; then  # étape réussie mais incomplète (ex. module du crawl désactivé) : ⚠️ avec la raison
    local avert; avert=$(avertissement_etape "$name")
    [ -n "$avert" ] && st="⚠️ $avert"
  fi
  case "$st" in ❌*) FAILS=$((FAILS + 1));; esac
  echo "| ${name} | $st | $(( $(date +%s) - t0 )) s | ${out#$AUDIT/} |" >> "$LOG"
  echo "  $st"
  case "$st" in ✅*) ;; *) extrait_journal "$name";; esac   # remplace le « tail -n 5 » de v2.0.1 : un seul extrait, masqué
}

prevol || { echo; cat "$LOG"; exit 2; }
[ "${AUDIT_INSECURE_TLS:-}" = "1" ] && echo "| mode test | ⚠️ TLS non vérifié (AUDIT_INSECURE_TLS=1) | | |" >> "$LOG"
# Espace disque : un disque plein donne des rapports de 0 octet sans autre erreur visible.
LIBRE_KO=$(df -Pk "$AUDIT" 2>/dev/null | awk 'NR==2 {print $4}')
if [ -n "${LIBRE_KO:-}" ] && [ "$LIBRE_KO" -lt 512000 ] 2>/dev/null; then
  echo "⚠️  Espace disque faible : $((LIBRE_KO / 1024)) Mo libres (500 Mo conseillés) — les rapports risquent d'être vides."
  echo "| disque | ⚠️ $((LIBRE_KO / 1024)) Mo libres (500 Mo conseillés) | | |" >> "$LOG"
fi

step crawl "$D/crawl/pages.json" valid_crawl python3 "$DIR/crawl_site.py" "$URL" --out "$D/crawl" \
     --max-pages "${MAX_PAGES:-500}" --delay 0.3 --check-images 200
# après le crawl : http_checks y lit les routes dynamiques à tester en soft 404
step http "$D/http/http-checks.md" valid_aucun bash "$DIR/http_checks.sh" "$URL" "$D/http" "$D/crawl/pages.json"
step geo "$D/geo/geo.json" valid_geo python3 "$DIR/geo_check.py" "$URL" --out "$D/geo" --crawl "$D/crawl/pages.json" --sample 12
step securite "$D/securite/security-probe.md" valid_aucun bash "$DIR/security_probe.sh" "$URL" "$D/securite"

if [ -s "$D/crawl/pages.json" ]; then
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
else
  printf '%s\n' "$URL" > "$D/lighthouse-urls.txt"
fi
if [ "${SKIP_LIGHTHOUSE:-0}" = "1" ]; then
  echo "| lighthouse | ⏭️ ignoré (SKIP_LIGHTHOUSE=1) | | |" >> "$LOG"
elif [ -n "${PSI_API_KEY:-}" ]; then
  step pagespeed "$D/perf/pagespeed.json" valid_perf python3 "$DIR/pagespeed.py" psi --out "$D/perf" --urls-file "$D/lighthouse-urls.txt"
else
  step lighthouse "$D/perf/pagespeed.json" valid_perf bash "$DIR/lighthouse_run.sh" "$D/perf" --file "$D/lighthouse-urls.txt"
fi

if [ -n "$PROJ" ]; then
  if [ "${BUILD:-0}" = "1" ]; then
    step projet "$D/code/project-checks.md" valid_aucun bash "$DIR/project_checks.sh" "$PROJ" "$D/code" --build
    DIST_ARG="--dist $D/code/build/client/_astro"
    [ -d "$D/code/build/client/_astro" ] || DIST_ARG="--dist $D/code/build/_astro"
  else
    step projet "$D/code/project-checks.md" valid_aucun bash "$DIR/project_checks.sh" "$PROJ" "$D/code"
    DIST_ARG=""
  fi
  # shellcheck disable=SC2086
  step code "$D/code/code-scan.json" valid_aucun python3 "$DIR/astro_scan.py" "$PROJ" --out "$D/code" $DIST_ARG
else
  echo "| projet / code | ⏭️ ignoré (pas de chemin projet) | | |" >> "$LOG"
fi

# Sorties à chemin fixe : effacées avant l'étape, pour qu'un échec ne soit pas masqué par le fichier d'une exécution précédente.
rm -f "$AUDIT/RAPPORT-BRUT.md"
step rapport-brut "$AUDIT/RAPPORT-BRUT.md" valid_aucun python3 "$DIR/rapport_brut.py" "$AUDIT"
# Dossier CORRECTIONS/ (LISEZ-MOI, plan, une fiche par correction) à remettre tel quel à un agent de code ; un échec compte comme les autres étapes.
if [ -n "$PROJ" ]; then
  step corrections "@sortie_corrections" valid_corrections python3 "$DIR/corrections.py" "$AUDIT" --projet "$PROJ"
else
  step corrections "@sortie_corrections" valid_corrections python3 "$DIR/corrections.py" "$AUDIT"
fi
# Ancien dossier conservé (.garder ou suivi commencé) : le signaler à l'écran (step range stderr dans un log) et dans COLLECTE.md.
NOM_CORR=""
valid_corrections && NOM_CORR=$(nom_corrections)  # STEP_T0 = début de l'étape corrections : un pointeur périmé ne déclenche rien
case "$NOM_CORR" in
  CORRECTIONS-*)
    grep -E '^\[(attention|info)\]' "$D/.log-corrections.txt" 2>/dev/null | sed 's/^/  ⚠️  /'
    echo "| corrections (dossier conservé) | ⚠️ l'ancien CORRECTIONS/ est conservé : donner $NOM_CORR/ à l'agent de code | | $NOM_CORR/ |" >> "$LOG"
    ;;
esac
rm -f "$AUDIT/RAPPORT.html"
step rapport-html "$AUDIT/RAPPORT.html" valid_aucun python3 "$DIR/rapport_html.py" "$AUDIT"
pdf_step() {  # cas particuliers de rapport_pdf.sh : Chrome absent (2) / RAM insuffisante (3) = avertissement
  local out="$AUDIT/RAPPORT.pdf" t0 code st
  t0=$(date +%s)
  echo "▶ pdf…"
  avec_delai "$(delai_etape pdf)" bash "$DIR/rapport_pdf.sh" "$AUDIT" > "$D/.log-pdf.txt" 2>&1
  code=$?
  case $code in
    0) if [ -s "$out" ] && head -c 5 "$out" | grep -q '%PDF-'; then st="✅"
       else st="❌ résultat vide ou inexploitable (voir data/.log-pdf.txt)"; fi;;
    2) st="⚠️ PDF non généré : Chrome introuvable (CHROME_PATH)";;
    3) st="⚠️ PDF non généré : RAM insuffisante";;
    124) st="❌ impression PDF : délai dépassé ($(delai_etape pdf) s, voir data/.log-pdf.txt)";;
    *) st="❌ impression PDF échouée, code $code (voir data/.log-pdf.txt)";;
  esac
  case "$st" in ❌*) FAILS=$((FAILS + 1));; esac
  echo "| pdf | $st | $(( $(date +%s) - t0 )) s | RAPPORT.pdf |" >> "$LOG"
  echo "  $st"
  case "$st" in ❌*) extrait_journal pdf;; esac
}
if [ "${SKIP_PDF:-0}" = "1" ] || { [ "${SKIP_LIGHTHOUSE:-0}" = "1" ] && [ "${FORCE_PDF:-0}" != "1" ]; }; then
  echo "| pdf | ⏭️ ignoré (SKIP_PDF=1 ou SKIP_LIGHTHOUSE=1) | | |" >> "$LOG"
else
  pdf_step
fi
# Historique du site (dossier parent) : toujours en dernier, il reprend le RAPPORT.html/.pdf qu'on vient de produire.
# Seulement pour un dossier d'audit daté AAAA-MM-JJ (sinon le parent n'est pas un dossier de site : rien n'y est écrit).
case "$(basename "$AUDIT")" in
  [0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9])
    step historique "$(dirname "$AUDIT")/index.html" valid_aucun python3 "$DIR/historique.py" "$(dirname "$AUDIT")";;
  *) echo "| historique | ⏭️ ignoré (dossier d'audit non daté AAAA-MM-JJ) | | |" >> "$LOG";;
esac
echo >> "$LOG"
echo "Dossier d'audit : \`$AUDIT\`" >> "$LOG"
# Section finale de COLLECTE.md (dernière : le fichier se termine par elle). À l'écran les extraits ont déjà été affichés sous chaque
# étape : le récapitulatif final ne la répète pas.
if [ -s "$D/.erreurs-etapes.md" ]; then
  { echo; echo "## Dernières lignes des étapes en échec ou en avertissement"; echo; cat "$D/.erreurs-etapes.md"; } >> "$LOG"
fi
echo
sed '/^## Dernières lignes des étapes en échec ou en avertissement$/,$d' "$LOG"
[ "$FAILS" -gt 0 ] && exit 1
exit 0
