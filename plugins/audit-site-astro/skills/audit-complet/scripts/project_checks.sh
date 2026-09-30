#!/usr/bin/env bash
# project_checks.sh — Santé du projet Astro : versions, dépendances obsolètes, vulnérabilités npm,
# `astro check` (types/diagnostics), build d'audit dans un dossier SÉPARÉ (le dist/ servi n'est jamais touché).
#
# Usage : bash project_checks.sh CHEMIN_PROJET DOSSIER_SORTIE [--build]
#   --build : lance `astro build --outDir DOSSIER_SORTIE/build` (nécessite node_modules installés et les
#             variables d'environnement de build ; rien n'est écrit dans le projet hormis le cache .astro/).
# Sortie : DOSSIER_SORTIE/project-checks.md + fichiers bruts (outdated.json, audit.json, astro-check.txt, build.log)
set -u
PROJ="${1:?usage: project_checks.sh CHEMIN_PROJET DOSSIER_SORTIE [--build]}"
OUT="${2:?dossier de sortie requis}"
BUILD="${3:-}"
mkdir -p "$OUT"
OUT="$(cd "$OUT" && pwd)"
cd "$PROJ" || { echo "Projet introuvable : $PROJ"; exit 1; }
REPORT="$OUT/project-checks.md"
exec > >(tee "$REPORT") 2>&1

if   [ -f pnpm-lock.yaml ]; then PM=pnpm
elif [ -f yarn.lock ]; then PM=yarn
elif [ -f bun.lockb ] || [ -f bun.lock ]; then PM=bun
else PM=npm; fi

echo "# Santé du projet — $(basename "$PWD")"
echo
echo "- Node : $(node -v 2>/dev/null || echo absent) — gestionnaire : $PM $($PM -v 2>/dev/null)"
echo "- Astro installé : $(node -p "require('./node_modules/astro/package.json').version" 2>/dev/null || echo 'node_modules absent')"
echo "- Convex installé : $(node -p "require('./node_modules/convex/package.json').version" 2>/dev/null || echo '—')"
echo "- Git : $(git rev-parse --abbrev-ref HEAD 2>/dev/null) @ $(git rev-parse --short HEAD 2>/dev/null) — $(git status --porcelain 2>/dev/null | wc -l | tr -d ' ') fichier(s) modifié(s) non commité(s)"
NODE_MAJOR=$(node -v 2>/dev/null | sed -E 's/^v([0-9]+).*/\1/')
[ -n "$NODE_MAJOR" ] && [ "$NODE_MAJOR" -lt 20 ] && echo "- ⚠️ Node $NODE_MAJOR : versions récentes d'Astro exigent Node ≥ 20 (LTS conseillée)"
echo

echo "## Dépendances obsolètes"
echo
if [ "$PM" = "npm" ]; then
  npm outdated --json > "$OUT/outdated.json" 2>/dev/null
  python3 - "$OUT/outdated.json" <<'PY'
import json, sys
try:
    d = json.load(open(sys.argv[1]))
except Exception:
    d = {}
if not d:
    print("- ✅ rien d'obsolète (ou node_modules absent)")
rows = []
for name, v in d.items():
    cur, lat = str(v.get("current", "?")), str(v.get("latest", "?"))
    major = cur.split(".")[0] != lat.split(".")[0] if cur[0:1].isdigit() else True
    rows.append((not major, name, cur, v.get("wanted", "?"), lat))
rows.sort()
if rows:
    print("| Paquet | Installé | Compatible | Dernière | Saut majeur |")
    print("|---|---|---|---|---|")
    for minor, n, c, w, l in rows[:60]:
        print(f"| {n} | {c} | {w} | {l} | {'⚠️ oui' if not minor else 'non'} |")
PY
else
  $PM outdated 2>&1 | head -60
fi
echo

echo "## Vulnérabilités connues (dépendances de production)"
echo
if [ "$PM" = "npm" ]; then
  npm audit --omit=dev --json > "$OUT/audit.json" 2>/dev/null
  python3 - "$OUT/audit.json" <<'PY'
import json, sys
try:
    d = json.load(open(sys.argv[1]))
except Exception:
    print("- audit impossible (pas de lockfile npm ?)"); sys.exit()
meta = d.get("metadata", {}).get("vulnerabilities", {})
print("- Total : " + ", ".join(f"{k} {v}" for k, v in meta.items() if k != "total" and v) + f" (total {meta.get('total', 0)})")
for name, v in list(d.get("vulnerabilities", {}).items())[:30]:
    if v.get("severity") in ("critical", "high", "moderate"):
        via = [x.get("title", "") for x in v.get("via", []) if isinstance(x, dict)][:1]
        fix = v.get("fixAvailable")
        fixs = "correctif dispo" if fix is True else (f"via {fix.get('name')}@{fix.get('version')}" if isinstance(fix, dict) else "pas de correctif")
        print(f"- **{v['severity']}** {name} {('— ' + via[0]) if via else ''} ({fixs})")
PY
else
  $PM audit --prod 2>&1 | tail -30
fi
echo

echo "## astro check (types et diagnostics)"
echo
if [ -d node_modules/astro ]; then
  npx --no-install astro check > "$OUT/astro-check.txt" 2>&1
  tail -5 "$OUT/astro-check.txt" | sed 's/^/    /'
  errs=$(grep -cE '\berror\b' "$OUT/astro-check.txt" 2>/dev/null); warns=$(grep -cE '\bwarning\b' "$OUT/astro-check.txt" 2>/dev/null)
  echo
  echo "- Lignes d'erreur : ${errs:-0} — avertissements : ${warns:-0} (détail : astro-check.txt)"
  grep -q "@astrojs/check" "$OUT/astro-check.txt" && echo "- ℹ️ @astrojs/check non installé : astro check a demandé à l'installer (ne rien installer sans accord)"
else
  echo "- node_modules absent : lancer \`$PM install\` (ou npm ci) avant pour activer ce contrôle"
fi
echo

if [ "$BUILD" = "--build" ]; then
  echo "## Build d'audit (dans $OUT/build)"
  echo
  if [ -d node_modules/astro ]; then
    start=$(date +%s)
    npx --no-install astro build --outDir "$OUT/build" > "$OUT/build.log" 2>&1
    code=$?
    echo "- Code de sortie : $code — durée : $(( $(date +%s) - start )) s"
    w=$(grep -ciE 'warn' "$OUT/build.log"); echo "- Avertissements dans le log : $w"
    grep -iE 'warn|error' "$OUT/build.log" | sort | uniq -c | sort -rn | head -15 | sed 's/^/    /'
    if [ -d "$OUT/build" ]; then
      echo
      echo "- Pages prérendues (HTML) : $(find "$OUT/build" -name '*.html' | wc -l | tr -d ' ')"
      echo "- Poids des assets client : $(du -sh "$OUT/build/client" 2>/dev/null | cut -f1 || du -sh "$OUT/build" | cut -f1)"
      echo "- Images les plus lourdes du build :"
      find "$OUT/build" -type f \( -name '*.jpg' -o -name '*.jpeg' -o -name '*.png' -o -name '*.webp' -o -name '*.avif' -o -name '*.gif' \) -size +150k -exec ls -lh {} \; 2>/dev/null \
        | awk '{print "    - " $5 " " $9}' | sed "s#$OUT/build/##" | sort -k2 -rh | head -10
    fi
  else
    echo "- node_modules absent : build impossible"
  fi
  echo
fi

echo "## Images sources lourdes (public/ et src/)"
echo
find public src -type f \( -iname '*.jpg' -o -iname '*.jpeg' -o -iname '*.png' -o -iname '*.gif' -o -iname '*.webp' \) -size +200k -exec ls -lh {} \; 2>/dev/null \
  | awk '{print "- " $5 " " $9}' | head -20
echo
echo "> Les images de public/ ne passent PAS par l'optimisation d'Astro : les déplacer dans src/assets et utiliser <Image>."
