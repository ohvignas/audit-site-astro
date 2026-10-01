#!/usr/bin/env bash
# etapes.sh — Fonctions de collect_all.sh (sourcées) : délai maximal d'une étape, arrêt de l'arbre de processus
# (délai dépassé ou Ctrl-C), extrait masqué du journal d'une étape en échec. Bash 3.2 : pas de `timeout`.
# Requiert D (dossier data/ de l'audit).

enfants_de() {  # PID des enfants directs de $1 (Linux : /proc ; macOS : ps)
  if [ -r /proc/self/stat ]; then
    for f in /proc/[0-9]*/stat; do
      sed -E 's/^([0-9]+) \(.*\) [A-Za-z] ([0-9]+) .*/\1 \2/' "$f" 2>/dev/null
    done | awk -v p="$1" '$2 == p {print $1}'
  else
    ps -A -o pid= -o ppid= 2>/dev/null | awk -v p="$1" '$2 == p {print $1}'
  fi
}

tuer_arbre() {  # TERM au processus $1 et à tous ses descendants (Chrome, node, curl…), du bas vers le haut
  local e
  for e in $(enfants_de "$1"); do tuer_arbre "$e"; done
  kill -TERM "$1" 2>/dev/null
  return 0
}

avec_delai() {  # $1 secondes, reste = commande ; code de la commande, ou 124 si le délai est dépassé
  local s="$1"; shift
  "$@" &
  local pid=$!
  ETAPE_PID=$pid
  ( i=0
    while [ "$i" -lt "$s" ]; do sleep 1; kill -0 "$pid" 2>/dev/null || exit 0; i=$((i + 1)); done
    : > "$D/.delai-$pid"
    tuer_arbre "$pid"; sleep 5; kill -KILL "$pid" 2>/dev/null ) >/dev/null 2>&1 &
  ETAPE_GARDE=$!
  { wait "$pid"; } 2>/dev/null
  local code=$?
  tuer_arbre "$ETAPE_GARDE"          # le gardien et son « sleep » : aucun processus ne reste après l'étape
  { wait "$ETAPE_GARDE"; } 2>/dev/null
  ETAPE_PID=""; ETAPE_GARDE=""
  if [ -f "$D/.delai-$pid" ]; then rm -f "$D/.delai-$pid"; return 124; fi
  return $code
}

interrompre_collecte() {  # piège INT/TERM : les tâches de fond ignorent SIGINT, il faut les arrêter nous-mêmes
  trap - INT TERM
  [ -n "${ETAPE_GARDE:-}" ] && tuer_arbre "$ETAPE_GARDE"
  [ -n "${ETAPE_PID:-}" ] && tuer_arbre "$ETAPE_PID"
  echo
  echo "⛔ collecte interrompue : étape en cours arrêtée (processus enfants compris)"
  exit 130
}

delai_etape() {  # DELAI_<NOM> (majuscules, « - » → « _ »), sinon DELAI_ETAPE, sinon défaut selon l'étape
  local var defaut=1800 mp="${MAX_PAGES:-500}" v
  case "$mp" in ''|*[!0-9]*) mp=500;; esac
  case "$1" in
    code) defaut=900;;
    crawl) defaut=$((1800 + mp * 3));;
  esac
  var="DELAI_$(printf '%s' "$1" | LC_ALL=C tr 'a-z-' 'A-Z_')"
  case "$var" in *[!A-Z0-9_]*) var="DELAI_ETAPE";; esac
  eval "v=\"\${$var:-\${DELAI_ETAPE:-}}\""
  case "$v" in ''|*[!0-9]*) v=$defaut;; esac   # valeur absente ou non numérique : défaut
  printf '%s' "$v"
}

_masquer() { LC_ALL=C sed -E 's/((key|token|apikey|api_key)=)[^&[:space:]]+/\1…/g'; }

extrait_journal() {  # $1 nom d'étape : 15 dernières lignes à l'écran et dans data/.erreurs-etapes.md
  local f="$D/.log-$1.txt"
  [ -s "$f" ] || return 0
  { echo "### $1"; echo; tail -n 15 "$f" | LC_ALL=C cut -c1-240 | _masquer | sed 's/^/    /'; echo; } >> "$D/.erreurs-etapes.md"
  tail -n 15 "$f" | LC_ALL=C cut -c1-240 | _masquer | sed 's/^/    │ /'
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
