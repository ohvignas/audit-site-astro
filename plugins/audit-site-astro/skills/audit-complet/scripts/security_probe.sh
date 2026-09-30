#!/usr/bin/env bash
# security_probe.sh — Recherche NON INTRUSIVE de fichiers exposés par erreur sur SON PROPRE site
# (Astro / Node / Vite / Convex, et restes WordPress éventuels). Simples requêtes GET, aucune attaque.
#
# Usage : bash security_probe.sh https://exemple.fr [DOSSIER_SORTIE]
# À n'utiliser que sur un site dont on est propriétaire ou pour lequel on a une autorisation écrite.
set -u
curl() { if [ "${AUDIT_INSECURE_TLS:-}" = "1" ]; then command curl -k "$@"; else command curl "$@"; fi; }
URL="${1:?usage: security_probe.sh https://site.tld [dossier_sortie]}"
OUT="${2:-.}"
mkdir -p "$OUT"
BASE=$(printf '%s' "$URL" | awk -F/ '{print $1"//"$3}')
UA="Mozilla/5.0 (compatible; AuditSecu/1.0; audit du proprietaire)"
REPORT="$OUT/security-probe.md"
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
exec > >(tee "$REPORT") 2>&1

# Référence : réponse d'une URL qui n'existe pas (pour repérer les « 200 » qui sont en fait la page 404)
curl -s -A "$UA" --max-time 15 -o "$TMP/ref" "$BASE/zz-audit-inexistant-$RANDOM.txt"
REF_SIZE=$(wc -c < "$TMP/ref" | tr -d ' ')

echo "# Sonde d'exposition — $BASE"
echo
echo "_$(date '+%Y-%m-%d %H:%M') — requêtes GET simples, rien n'est modifié._"
echo
echo "| Chemin | HTTP | Taille | Verdict |"
echo "|---|---|---|---|"

check() {  # $1 chemin, $2 motif attendu si réellement exposé, $3 gravité si exposé
  local path="$1" pat="$2" sev="$3"
  local code size verdict
  code=$(curl -s -A "$UA" --max-time 15 -o "$TMP/b" -w '%{http_code}' "$BASE$path")
  size=$(wc -c < "$TMP/b" | tr -d ' ')
  verdict="✅"
  if [ "$code" = "200" ]; then
    if [ -n "$pat" ] && grep -qaiE "$pat" "$TMP/b"; then
      verdict="❌ EXPOSÉ ($sev)"
    elif [ "$size" = "$REF_SIZE" ] || grep -qaiE '<html|<!doctype' "$TMP/b"; then
      verdict="✅ (page HTML générique / 404 déguisée)"
    else
      verdict="⚠️ répond 200 — vérifier le contenu"
    fi
  fi
  echo "| $path | $code | $size | $verdict |"
}

# Secrets et dépôts
check "/.env" "^[A-Z_]+=|CONVEX_|SECRET|API_KEY|TOKEN" "critique"
check "/.env.local" "^[A-Z_]+=" "critique"
check "/.env.production" "^[A-Z_]+=" "critique"
check "/.git/HEAD" "^ref: refs/" "critique"
check "/.git/config" "\[core\]" "critique"
check "/.npmrc" "_authToken|registry" "haute"
check "/.DS_Store" "Bud1" "basse"
# Code source / build
check "/package.json" "\"dependencies\"" "moyenne"
check "/package-lock.json" "\"lockfileVersion\"" "basse"
check "/astro.config.mjs" "defineConfig" "moyenne"
check "/astro.config.ts" "defineConfig" "moyenne"
check "/convex/schema.ts" "defineSchema" "moyenne"
check "/src/pages/index.astro" "---" "moyenne"
check "/dist/server/entry.mjs" "import" "haute"
check "/server/entry.mjs" "import" "haute"
check "/Dockerfile" "FROM " "basse"
check "/docker-compose.yml" "services:" "moyenne"
# Sauvegardes et exports
check "/backup.zip" "" "haute"
check "/backup.sql" "INSERT INTO|CREATE TABLE" "critique"
check "/dump.sql" "INSERT INTO|CREATE TABLE" "critique"
check "/db.sqlite" "SQLite format" "critique"
# Debug / outils de dev
check "/_image?href=https://example.com/x.png" "" "info"
check "/__vite_ping" "" "moyenne"
check "/@vite/client" "import.meta.hot|vite" "haute"
check "/phpinfo.php" "phpinfo\(\)|PHP Version" "haute"
check "/server-status" "Apache Server Status" "moyenne"
check "/.well-known/security.txt" "Contact:" "info"
# Restes WordPress (migrations)
check "/wp-login.php" "wp-submit|user_login" "info"
check "/xmlrpc.php" "XML-RPC" "info"
check "/wp-content/debug.log" "PHP (Warning|Notice|Fatal)" "haute"

echo
echo "## Source maps JavaScript publiques"
echo
curl -s -A "$UA" --max-time 20 "$URL" -o "$TMP/home.html"
js=$(grep -oE '(src|href)="[^"]+\.js"' "$TMP/home.html" | sed -E 's/^(src|href)="//; s/"$//' | awk '!s[$0]++' | head -8)
found=0
for j in $js; do
  case "$j" in http*) full="$j";; /*) full="$BASE$j";; *) full="$BASE/$j";; esac
  case "$full" in "$BASE"*) ;; *) continue;; esac
  mapref=$(curl -s -A "$UA" --max-time 15 "$full" | tail -c 300 | grep -oE 'sourceMappingURL=[^ ]+' | head -1)
  code=$(curl -s -o /dev/null -A "$UA" --max-time 15 -w '%{http_code}' "$full.map")
  if [ "$code" = "200" ] || [ -n "$mapref" ]; then
    echo "- ⚠️ $full → .map HTTP $code ${mapref:+($mapref)} — le code source est lisible (sans gravité si aucun secret, mais à désactiver en prod : vite.build.sourcemap=false)"
    found=1
  fi
done
[ "$found" = "0" ] && echo "- ✅ aucune source map trouvée sur les scripts de la page d'accueil"

echo
echo "## Clés et secrets dans le HTML / JS livrés au navigateur"
echo
for j in $js; do
  case "$j" in http*) full="$j";; /*) full="$BASE$j";; *) full="$BASE/$j";; esac
  case "$full" in "$BASE"*) curl -s -A "$UA" --max-time 15 "$full" >> "$TMP/bundle.js";; esac
done
cat "$TMP/home.html" >> "$TMP/bundle.js"
hits=$(grep -aoE '(sk_live_[A-Za-z0-9]{10,}|sk-[A-Za-z0-9_-]{20,}|sk-ant-[A-Za-z0-9_-]{20,}|AKIA[0-9A-Z]{16}|AIza[0-9A-Za-z_-]{35}|ghp_[A-Za-z0-9]{30,}|xox[baprs]-[A-Za-z0-9-]{10,}|-----BEGIN (RSA |EC )?PRIVATE KEY|CONVEX_DEPLOY_KEY|prod:[a-z0-9-]+\|[A-Za-z0-9=]{20,}|re_[A-Za-z0-9]{20,})' "$TMP/bundle.js" | sort -u | sed -E 's/(.{12}).*/\1…/' | head -20)
if [ -n "$hits" ]; then
  echo "❌ Motifs de secrets trouvés (tronqués) — vérifier et RÉVOQUER la clé si elle est réelle :"
  echo '```'; echo "$hits"; echo '```'
  echo "Note : une clé Google Maps/Firebase (AIza…) peut être publique si elle est restreinte par domaine."
else
  echo "- ✅ aucun motif de clé secrète connu dans le HTML et les scripts de la page d'accueil"
fi

echo
echo "## Méthodes HTTP et CORS"
echo
opt=$(curl -s -o /dev/null -D - -X OPTIONS -A "$UA" --max-time 15 "$URL" | grep -iE '^(allow|access-control-allow-origin):' | tr -d '\r')
echo "- OPTIONS : ${opt:-aucun en-tête Allow/CORS exposé}"
cors=$(curl -s -o /dev/null -D - -H "Origin: https://evil.example" -A "$UA" --max-time 15 "$URL" | grep -i '^access-control-allow-origin:' | tr -d '\r')
[ -n "$cors" ] && echo "- ⚠️ CORS sur la page HTML pour une origine arbitraire : $cors" || echo "- ✅ pas de CORS ouvert sur la page HTML"
