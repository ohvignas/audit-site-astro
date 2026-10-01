#!/usr/bin/env bash
# etapes.sh — Fonctions de collect_all.sh (sourcées) : délai maximal d'une étape, arrêt de l'arbre de processus
# (délai dépassé ou Ctrl-C), extrait masqué du journal d'une étape en échec. Bash 3.2 : pas de `timeout`.
# Requiert D (dossier data/ de l'audit).

enfants_de() {  # PID des enfants directs de $1 (Linux : /proc, un seul sed pour tous les processus ; macOS : ps)
  if [ -r /proc/self/stat ]; then
    sed -E 's/^([0-9]+) \(.*\) [A-Za-z] ([0-9]+) .*/\1 \2/' /proc/[0-9]*/stat 2>/dev/null | awk -v p="$1" '$2 == p {print $1}'
  else
    ps -A -o pid= -o ppid= 2>/dev/null | awk -v p="$1" '$2 == p {print $1}'
  fi
}

arbre_de() {  # $1 puis tous ses descendants, chacun gelé (STOP) avant de lister ses enfants : aucun nouveau fork ne s'intercale
  local e
  kill -STOP "$1" 2>/dev/null || return 0
  echo "$1"
  for e in $(enfants_de "$1"); do arbre_de "$e"; done
}

# Pas de groupe de processus : Lighthouse lance Chrome dans sa propre session (chrome-launcher, detached), un kill de groupe le manquerait.
tuer_arbre() {  # $1 racine, $2 délai de grâce en s (défaut 5) : arbre gelé, TERM à tous, CONT, attente, puis KILL aux survivants
  [ -n "${1:-}" ] || return 0
  local pids p n=0 reste
  pids=$(arbre_de "$1")
  for p in $pids; do kill -TERM "$p" 2>/dev/null; done
  for p in $pids; do kill -CONT "$p" 2>/dev/null; done
  while [ "$n" -lt "${2:-5}" ]; do
    reste=""
    for p in $pids; do [ "$p" = "$1" ] && continue; kill -0 "$p" 2>/dev/null && reste=1; done  # la racine peut rester zombie
    [ -z "$reste" ] && break
    sleep 1; n=$((n + 1))
  done
  for p in $pids; do kill -0 "$p" 2>/dev/null && kill -KILL "$p" 2>/dev/null; done
  return 0
}

avec_delai() {  # $1 secondes (0 = sans limite), reste = commande ; code de la commande, ou 124 si le délai est dépassé
  local s="$1"; shift
  case "$s" in ''|*[!0-9]*|????????*) s=1800;; esac
  s=$((10#$s))
  "$@" &
  local pid=$!
  ETAPE_PID=$pid; ETAPE_GARDE=""
  if [ "$s" -gt 0 ]; then
    ( i=0
      while [ "$i" -lt "$s" ]; do sleep 1; kill -0 "$pid" 2>/dev/null || exit 0; i=$((i + 1)); done
      : > "$D/.delai-$pid"
      tuer_arbre "$pid" 5 ) >/dev/null 2>&1 &
    ETAPE_GARDE=$!
  fi
  { wait "$pid"; } 2>/dev/null
  local code=$?
  if [ -n "$ETAPE_GARDE" ]; then
    if [ -f "$D/.delai-$pid" ]; then
      { wait "$ETAPE_GARDE"; } 2>/dev/null   # délai dépassé : le gardien finit son escalade (KILL des survivants)
    else
      tuer_arbre "$ETAPE_GARDE" 0            # le gardien et son « sleep » : aucun processus ne reste après l'étape
      { wait "$ETAPE_GARDE"; } 2>/dev/null
    fi
  fi
  ETAPE_PID=""; ETAPE_GARDE=""
  if [ -f "$D/.delai-$pid" ]; then rm -f "$D/.delai-$pid"; return 124; fi
  return $code
}

interrompre_collecte() {  # piège INT/TERM : les tâches de fond ignorent SIGINT, il faut les arrêter nous-mêmes
  trap '' INT TERM   # un second Ctrl-C ne doit pas interrompre le nettoyage
  echo
  echo "⛔ collecte interrompue : étape en cours arrêtée (processus enfants compris)"
  [ -n "${ETAPE_GARDE:-}" ] && tuer_arbre "$ETAPE_GARDE" 0
  [ -n "${ETAPE_PID:-}" ] && tuer_arbre "$ETAPE_PID" 5   # TERM, 5 s de grâce, puis KILL aux survivants
  rm -f "$D"/.delai-* 2>/dev/null
  exit 130
}

delai_etape() {  # DELAI_<NOM> (majuscules, « - » → « _ »), sinon DELAI_ETAPE, sinon défaut selon l'étape ; 0 = sans limite
  local var defaut=1800 mp="${MAX_PAGES:-500}" lp="${LH_PAGES:-5}" runs="${RUNS:-1}" v
  case "$mp" in ''|*[!0-9]*|????????*) mp=500;; esac
  case "$lp" in ''|*[!0-9]*|????*) lp=5;; esac
  case "$runs" in ''|*[!0-9]*|????*) runs=1;; esac
  mp=$((10#$mp)); lp=$((10#$lp)); runs=$((10#$runs))
  case "$1" in
    code) defaut=900;;
    crawl) defaut=$((1800 + mp * 3));;
    lighthouse) defaut=$((600 + lp * runs * 240));;   # 1800 s avec LH_PAGES=5 et RUNS=1 ; ~240 s par mesure au plus
  esac
  var="DELAI_$(printf '%s' "$1" | LC_ALL=C tr 'a-z-' 'A-Z_')"
  case "$var" in *[!A-Z0-9_]*) var="DELAI_ETAPE";; esac
  eval "v=\"\${$var:-\${DELAI_ETAPE:-}}\""
  case "$v" in ''|*[!0-9]*|????????*) v=$defaut;; esac   # valeur absente ou non numérique : défaut
  printf '%s' "$((10#$v))"
}

# Extrait masqué (UTF-8 sûr) : 15 dernières lignes, coupées à 240 CARACTÈRES, secrets masqués au même passage.
_extrait_py() {
  python3 - "$1" <<'PY' 2>/dev/null
import re, sys
from collections import deque
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
MOT = r"(?:key|token|secret|passw(?:or)?d|signature|credential|auth|sig)"
REGLES = (
    (re.compile(r"(?i)(\bauthorization[\"']?\s*[:=]\s*(?:bearer\s+|basic\s+)?[\"']?)[^\s&\"',;]+"), r"\1…"),
    (re.compile(r"(?i)(\b[\w-]*" + MOT + r"\b[\"']?\s*[:=]\s*(?:bearer\s+)?[\"']?)[^\s&\"',;]+"), r"\1…"),
    (re.compile(r"(?i)(\bbearer\s+)[^\s\"']+"), r"\1…"),
    (re.compile(r"(://[^/\s:@]+:)[^@\s/]+@"), r"\1…@"),
    (re.compile(r"(sk_live_|sk-ant-|sk-|AKIA|AIza|ghp_|xox[baprs]-|npm_)[A-Za-z0-9_|=-]{4,}"), r"\1…"),
)
with open(sys.argv[1], encoding="utf-8", errors="replace") as f:
    for ligne in deque(f, 15):
        ligne = ligne.rstrip("\r\n")[:2000]
        for rx, rep in REGLES:
            ligne = rx.sub(rep, ligne)
        print(ligne[:240])
PY
}

extrait_journal() {  # $1 nom d'étape : 15 dernières lignes à l'écran et dans data/.erreurs-etapes.md (même calcul, une seule fois)
  local f="$D/.log-$1.txt" ex
  [ -s "$f" ] || return 0
  ex=$(_extrait_py "$f")
  [ -n "$ex" ] || return 0
  { echo "### $1"; echo; printf '%s\n' "$ex" | sed 's/^/    /'; echo; } >> "$D/.erreurs-etapes.md"
  printf '%s\n' "$ex" | sed 's/^/    │ /'
}

avertissement_etape() {  # $1 nom d'étape ; affiche la raison d'un ⚠️ alors que l'étape a réussi (rien sinon) ; code 0
  [ "$1" = "crawl" ] || return 0
  local noms=""
  # modules du crawl en erreur : constat « modules_en_erreur » de issues.json (exemples = noms des modules)…
  noms=$(python3 -c "
import json, sys
try:
    e = json.load(open(sys.argv[1], encoding='utf-8')).get('modules_en_erreur')
    print(', '.join(str(x) for x in e.get('examples', []))) if isinstance(e, dict) else None
except Exception:
    pass" "$D/crawl/issues.json" 2>/dev/null)
  # … ou, à défaut (issues.json absent), lignes « ⚠️ module <nom> désactivé » du journal du crawl
  if [ -z "$noms" ] && [ -f "$D/.log-crawl.txt" ]; then
    noms=$(grep -E '^⚠️ module [A-Za-z0-9_]+ désactivé' "$D/.log-crawl.txt" 2>/dev/null | awk '{print $3}' | sort -u | paste -sd, - | sed 's/,/, /g')
  fi
  [ -n "$noms" ] && echo "modules du crawl désactivés : $noms (contrôles manquants, voir data/crawl/summary.md)"
  return 0
}
