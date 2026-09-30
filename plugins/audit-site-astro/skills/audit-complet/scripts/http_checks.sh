#!/usr/bin/env bash
# http_checks.sh — Contrôles HTTP côté réseau : redirections d'hôte, TTFB (cache / sans cache),
# compression, HTTP/2-3, cache des assets Astro (/_astro/), en-têtes de sécurité, TLS.
#
# Usage : bash http_checks.sh https://exemple.fr [DOSSIER_SORTIE]
# Sortie : DOSSIER_SORTIE/http-checks.md (lisible) — aucune modification du site.
set -u
curl() { command curl ${AUDIT_INSECURE_TLS:+-k} "$@"; }
URL="${1:?usage: http_checks.sh https://site.tld [dossier_sortie]}"
OUT="${2:-.}"
mkdir -p "$OUT"
REPORT="$OUT/http-checks.md"
UA="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36"
HOST=$(printf '%s' "$URL" | awk -F/ '{print $3}')
BARE="${HOST#www.}"
BASE="https://$HOST"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

exec > >(tee "$REPORT") 2>&1

echo "# Contrôles HTTP — $URL"
echo
echo "_$(date '+%Y-%m-%d %H:%M') — curl $(curl --version | head -1 | awk '{print $2}')_"
[ "${AUDIT_INSECURE_TLS:-}" = "1" ] && echo "> ⚠️ TLS non vérifié (mode test AUDIT_INSECURE_TLS=1) : les contrôles de certificat ne sont pas significatifs." && echo
echo

echo "## 1. Variantes d'hôte → URL finale"
echo
echo "| Variante | Code 1er saut | Sauts | URL finale |"
echo "|---|---|---|---|"
# Sous-domaine (ex. beta.site.fr) : pas de variante www attendue
if [ "$(printf '%s' "$BARE" | awk -F. '{print NF}')" -gt 2 ] && [ "$HOST" = "$BARE" ]; then
  VARIANTS="http://$BARE/ https://$BARE/"
else
  VARIANTS="http://$BARE/ http://www.$BARE/ https://$BARE/ https://www.$BARE/"
fi
for v in $VARIANTS; do
  first=$(curl -s -o /dev/null -A "$UA" -w '%{http_code}' --max-time 15 "$v" 2>/dev/null)
  res=$(curl -s -o /dev/null -L -A "$UA" -w '%{num_redirects}|%{url_effective}|%{http_code}' --max-time 20 "$v" 2>/dev/null)
  [ -z "$res" ] && res="—|injoignable (DNS ?)|000"
  echo "| $v | $first | ${res%%|*} | $(echo "$res" | cut -d'|' -f2) ($(echo "$res" | cut -d'|' -f3)) |"
done
echo
echo "> Attendu : toutes les variantes → **une seule** URL https en **1 saut 301/308**. Code 000 = hôte sans DNS (normal si la variante n'est pas utilisée)."
echo

echo "## 2. Temps de réponse (TTFB) — 5 mesures"
echo
echo "| Requête | DNS | Connexion | TLS | **TTFB** | Total | Taille | HTTP |"
echo "|---|---|---|---|---|---|---|---|"
for i in 1 2 3 4 5; do
  curl -s -o /dev/null -A "$UA" -H 'Accept-Encoding: br, gzip' --max-time 30 \
    -w "| normale #$i | %{time_namelookup}s | %{time_connect}s | %{time_appconnect}s | **%{time_starttransfer}s** | %{time_total}s | %{size_download} o | %{http_version} |\n" "$URL"
done
for i in 1 2 3; do
  sep='?'; case "$URL" in *\?*) sep='&';; esac
  curl -s -o /dev/null -A "$UA" -H 'Accept-Encoding: br, gzip' -H 'Cache-Control: no-cache' --max-time 30 \
    -w "| sans cache #$i | %{time_namelookup}s | %{time_connect}s | %{time_appconnect}s | **%{time_starttransfer}s** | %{time_total}s | %{size_download} o | %{http_version} |\n" \
    "${URL}${sep}audit_nocache=$RANDOM$RANDOM"
done
echo
echo "> Bon : TTFB < 0,2 s servi par cache/CDN, < 0,8 s en rendu serveur (SSR). Un grand écart normale/sans cache = le cache fonctionne ;"
echo "> aucun écart + TTFB élevé = chaque page est rendue à la volée (SSR sans cache, requêtes backend lentes)."
echo

echo "## 3. En-têtes de la page HTML"
echo
curl -s -D "$TMP/h_html" -o "$TMP/body.html" -A "$UA" -H 'Accept-Encoding: br, gzip' --compressed --max-time 30 "$URL" >/dev/null
echo '```'
grep -viE '^(set-cookie|report-to|nel):' "$TMP/h_html" | tr -d '\r' | sed -n '1,60p'
echo '```'
hv() { grep -i "^$1:" "$2" | head -1 | cut -d: -f2- | tr -d '\r' | sed 's/^ *//'; }
echo
echo "| Contrôle | Valeur | Verdict |"
echo "|---|---|---|"
enc=$(curl -s -o /dev/null -D - -A "$UA" -H 'Accept-Encoding: br, gzip' --max-time 20 "$URL" | grep -i '^content-encoding:' | tr -d '\r' | cut -d: -f2 | sed 's/ //g')
hsize=$(wc -c < "$TMP/body.html" | tr -d ' ')
echo "| Compression HTML | ${enc:-aucune} (HTML décompressé : $((hsize / 1024)) Ko) | $([ -n "$enc" ] && echo ✅ || echo '❌ activer brotli/gzip (proxy, CDN ou middleware)') |"
[ "$hsize" -gt 150000 ] && echo "| Poids HTML | $((hsize / 1024)) Ko | ⚠️ > 150 Ko : SVG inline, JSON d'îlots, CSS inline ? |"
fav=$(grep -oiE '<link[^>]+rel="[^"]*icon[^"]*"[^>]*>' "$TMP/body.html" | head -1)
echo "| Favicon déclaré | $(printf '%s' "${fav:-aucun <link rel=icon>}" | cut -c1-80 | tr '|' '/') | $([ -n "$fav" ] && echo ✅ || echo '⚠️ Google affiche le favicon dans les résultats') |"
cc=$(hv cache-control "$TMP/h_html"); echo "| Cache-Control HTML | ${cc:-absent} | $(echo "$cc" | grep -qiE 'no-store|private' && echo '⚠️ non cacheable (normal si page personnalisée)' || echo 'ℹ️ vérifier la stratégie CDN') |"
alt=$(hv alt-svc "$TMP/h_html"); echo "| HTTP/3 (alt-svc) | ${alt:-non annoncé} | $([ -n "$alt" ] && echo ✅ || echo 'ℹ️ optionnel') |"
srv=$(hv server "$TMP/h_html"); pw=$(hv x-powered-by "$TMP/h_html")
echo "| Server / X-Powered-By | ${srv:-—} / ${pw:-—} | $(echo "$srv$pw" | grep -qE '[0-9]+\.[0-9]+' && echo '⚠️ version exposée' || echo ✅) |"
for h in strict-transport-security content-security-policy x-content-type-options referrer-policy permissions-policy x-frame-options cross-origin-opener-policy; do
  val=$(hv "$h" "$TMP/h_html")
  if [ -n "$val" ]; then v="✅"; else v="❌ absent"; fi
  [ "$h" = "x-frame-options" ] && [ -z "$val" ] && grep -qi 'frame-ancestors' "$TMP/h_html" && v="✅ (frame-ancestors dans la CSP)"
  [ "$h" = "cross-origin-opener-policy" ] && [ -z "$val" ] && v="ℹ️ optionnel"
  short=$(printf '%s' "$val" | cut -c1-90)
  echo "| $h | ${short:-—} | $v |"
done
csp=$(hv content-security-policy "$TMP/h_html")
if [ -n "$csp" ]; then
  echo "$csp" | grep -q "unsafe-eval" && echo "| CSP | contient 'unsafe-eval' | ⚠️ à éviter |"
  echo "$csp" | grep -qE "script-src[^;]*'unsafe-inline'" && ! echo "$csp" | grep -qE "nonce-|sha(256|384)-" && echo "| CSP | script-src 'unsafe-inline' sans nonce/hash | ⚠️ protège peu contre le XSS |"
fi
echo

echo "## 4. Cache et compression des ressources statiques"
echo
echo "| Ressource | Cache-Control | Encodage | Verdict |"
echo "|---|---|---|---|"
grep -oE '(src|href)="[^"]+\.(js|css|woff2?|webp|avif|png|jpe?g|svg)(\?[^"]*)?"' "$TMP/body.html" \
  | sed -E 's/^(src|href)="//; s/"$//' | awk '!seen[$0]++' | head -12 | while read -r a; do
  case "$a" in http*) full="$a";; //*) full="https:$a";; /*) full="$BASE$a";; *) full="$BASE/$a";; esac
  h=$(curl -s -o /dev/null -D - -A "$UA" -H 'Accept-Encoding: br, gzip' --max-time 20 "$full")
  acc=$(printf '%s' "$h" | grep -i '^cache-control:' | head -1 | cut -d: -f2- | tr -d '\r' | sed 's/^ *//')
  aen=$(printf '%s' "$h" | grep -i '^content-encoding:' | head -1 | cut -d: -f2 | tr -d '\r ')
  code=$(printf '%s' "$h" | head -1 | awk '{print $2}')
  verdict="✅"
  if [ "$code" != "200" ]; then verdict="❌ HTTP $code"
  elif printf '%s' "$full" | grep -q '/_astro/' && ! printf '%s' "$acc" | grep -qi 'immutable\|max-age=3[0-9]\{7\}'; then verdict="⚠️ asset hashé Astro : viser max-age=31536000, immutable"
  elif ! printf '%s' "$acc" | grep -qi 'max-age=[1-9]'; then verdict="⚠️ pas de cache navigateur"
  fi
  case "$full" in *.js|*.css|*.svg) [ -z "$aen" ] && verdict="$verdict ; ⚠️ non compressé";; esac
  echo "| $(printf '%s' "$full" | sed "s#$BASE##" | cut -c1-70) | ${acc:-absent} | ${aen:-—} | $verdict |"
done
echo

echo "## 4 bis. Images optimisées par Astro (/_image) et image LCP"
echo
IMGS=$(grep -oE '/_image\?[^" ]+' "$TMP/body.html" | sed 's/&amp;/\&/g' | awk '!s[$0]++' | head -3)
if [ -z "$IMGS" ]; then
  echo "- Aucune URL /_image dans la page : images prérendues au build (idéal) ou non optimisées par Astro (voir code-scan)."
else
  echo "| Image | Appel 1 (TTFB) | Appel 2 (TTFB) | Taille | Format | Cache-Control | Verdict |"
  echo "|---|---|---|---|---|---|---|"
  for u in $IMGS; do
    r1=$(curl -s -o /dev/null -A "$UA" -w '%{time_starttransfer}|%{size_download}|%{content_type}' --max-time 30 "$BASE$u")
    r2=$(curl -s -o /dev/null -D "$TMP/h_img" -A "$UA" -w '%{time_starttransfer}' --max-time 30 "$BASE$u")
    t1=${r1%%|*}; rest=${r1#*|}; sz=${rest%%|*}; ct=${rest#*|}
    icc=$(hv cache-control "$TMP/h_img")
    v="✅"
    awk -v a="$t1" -v b="$r2" 'BEGIN{exit !(a>0.3 && b>0.3)}' && v="⚠️ transformée à chaque requête (pas de cache serveur) : prérendre la page ou cacher /_image au proxy/CDN"
    [ "$sz" -gt 250000 ] 2>/dev/null && v="$v ; ⚠️ > 250 Ko"
    echo "| $(printf '%s' "$u" | cut -c1-60)… | ${t1}s | ${r2}s | $((sz / 1024)) Ko | ${ct#image/} | ${icc:-absent} | $v |"
  done
fi
grep -oE '<img[^>]*fetchpriority="high"[^>]*>' "$TMP/body.html" > "$TMP/prio.txt"
nprio=$(wc -l < "$TMP/prio.txt" | tr -d ' ')
echo
if [ "$nprio" -eq 0 ]; then
  echo "- ⚠️ Aucune image avec fetchpriority=\"high\" : si l'élément LCP est une image, elle n'est pas priorisée (prop \`priority\` d'<Image>)."
else
  echo "**Images en priorité haute : $nprio** $([ "$nprio" -gt 1 ] && echo '— ⚠️ une seule devrait l'"'"'être (l'"'"'image LCP) : sinon elles se disputent la bande passante')"
  echo
  echo "| # | Source | Optimisée par Astro | srcset | decoding | Verdict |"
  echo "|---|---|---|---|---|---|"
  i=0
  while IFS= read -r tag; do
    i=$((i + 1)); [ $i -gt 6 ] && break
    src=$(printf '%s' "$tag" | grep -oE ' src="[^"]+"' | head -1 | cut -d'"' -f2 | sed 's/&amp;/\&/g')
    opt=$(printf '%s' "$src" | grep -q '/_image\|/_astro/' && echo oui || echo "non (brute)")
    ss=$(printf '%s' "$tag" | grep -q 'srcset=' && echo oui || echo non)
    dec=$(printf '%s' "$tag" | grep -oE 'decoding="[^"]+"' | cut -d'"' -f2)
    v=""
    [ "$opt" != "oui" ] && v="⚠️ fichier original servi tel quel (autoriser le domaine dans image.remotePatterns et passer par <Image>)"
    [ "$ss" = "non" ] && v="$v ⚠️ pas de srcset"
    [ "$dec" = "async" ] && v="$v ℹ️ prop \`priority\` → decoding=sync"
    echo "| $i | $(printf '%s' "$src" | cut -c1-70) | $opt | $ss | ${dec:-—} | ${v:-✅} |"
  done < "$TMP/prio.txt"
fi
echo
echo "## 5. TLS / certificat"
echo
if command -v openssl >/dev/null; then
  cert=$(echo | openssl s_client -servername "$HOST" -connect "$HOST:443" 2>/dev/null | openssl x509 -noout -enddate -issuer 2>/dev/null)
  echo '```'; echo "${cert:-certificat illisible}"; echo '```'
  end=$(printf '%s' "$cert" | grep notAfter | cut -d= -f2)
  if [ -n "$end" ]; then
    endts=$(date -j -f "%b %e %T %Y %Z" "$end" +%s 2>/dev/null || date -d "$end" +%s 2>/dev/null)
    [ -n "$endts" ] && echo "- Expiration dans **$(( (endts - $(date +%s)) / 86400 )) jours** (renouvellement automatique attendu < 30 j)."
  fi
fi
for v in 1.3 1.2; do
  if curl -s -o /dev/null --max-time 10 --tlsv$v --tls-max $v "https://$HOST/" 2>/dev/null; then echo "- TLS $v : ✅ accepté"; else echo "- TLS $v : non accepté"; fi
done
for v in 1.0 1.1; do
  if curl -s -o /dev/null --max-time 10 --tlsv$v --tls-max $v "https://$HOST/" 2>/dev/null; then echo "- TLS $v : ⚠️ encore accepté (obsolète)"; else echo "- TLS $v : ✅ refusé (ou non testable avec ce curl)"; fi
done
echo

echo "## 6. Fichiers techniques"
echo
echo "| Fichier | HTTP | Content-Type |"
echo "|---|---|---|"
for f in robots.txt sitemap.xml sitemap-index.xml sitemap-0.xml llms.txt llms-full.txt favicon.ico favicon.svg manifest.webmanifest site.webmanifest .well-known/security.txt 404-page-inexistante-audit; do
  r=$(curl -s -o /dev/null -A "$UA" --max-time 15 -w '%{http_code}|%{content_type}' "$BASE/$f")
  echo "| /$f | ${r%%|*} | ${r#*|} |"
done
echo
echo "> La dernière ligne doit renvoyer **404** (une page inexistante en 200 = soft 404, fréquent en SSR Astro si la route dynamique ne fixe pas Astro.response.status)."
