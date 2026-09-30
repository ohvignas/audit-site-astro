#!/usr/bin/env python3
"""
rapport_html.py — Page web autonome RAPPORT.html à partir de DOSSIER_AUDIT (données + rapport priorisé).

Usage : python3 rapport_html.py DOSSIER_AUDIT [--sortie FICHIER]     (défaut : DOSSIER_AUDIT/RAPPORT.html)

Un seul fichier HTML : CSS en ligne, SVG en ligne, aucun JavaScript, aucune ressource externe. Lisible hors ligne,
clair/sombre selon le système, imprimable en A4 (c'est aussi la source du PDF). Tout texte issu du site audité
ou des fichiers de données passe par html.escape.

Si DOSSIER_AUDIT/CORRECTIONS/index.json existe (dossier remis à l'agent de code), la page ajoute : un lien « Comment corriger → NN »
sur chaque signal associé à une fiche, une section « Plan de correction » et l'annexe « Guides de correction » (fiches rendues par
markdown_vers_html). Le dossier lu est celui que désigne data/corrections-dossier.txt (CORRECTIONS-<horodatage>/ quand
corrections.py a conservé l'ancien), à défaut CORRECTIONS/. Sans index.json, ou s'il n'a aucune entrée utilisable, la page est identique à celle sans cette fonction.

API : notes_par_domaine(signaux), notes_audit(audit), note_globale(notes), markdown_vers_html(md), charger_corrections(audit),
generer(audit) -> HTML complet.
"""
import argparse
import html
import json
import math
import os
import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import signaux  # noqa: E402
from corrections import cle_jointure  # noqa: E402  (même nettoyage de la clé de jointure que celui de index.json)

# --- Barème (references/notation.md) ---------------------------------------------------------------------------------
POIDS = {"Performance": 20, "SEO technique": 20, "Contenu": 15, "GEO / IA": 15, "Sécurité": 12, "Code": 10, "Accessibilité": 8}
RATTACHE = {"Serveur / HTTP": "Performance", "Bonnes pratiques": "Code"}  # affichés, comptés avec le domaine parent
MALUS = {"critique": 20, "haute": 10, "moyenne": 4, "basse": 1}
LECTURE = {"A": "Excellent, finitions seulement", "B": "Bon, quelques gains nets", "C": "Correct, plusieurs chantiers utiles",
           "D": "Faible, perte de trafic ou de sécurité probable", "E": "Urgent"}
SEV_LIBELLE = {"critique": "Critique", "haute": "Haute", "moyenne": "Moyenne", "basse": "Basse", "info": "Info"}
MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"]
e = html.escape

# --- Feuille de style ------------------------------------------------------------------------------------------------
_CLAIR = {"fond": "#f4f6f9", "carte": "#ffffff", "texte": "#1b2430", "doux": "#546071", "bord": "#dde2e9", "zebre": "#f6f8fb",
          "accent": "#2648c7", "bandeau": "#14213d", "bandeau-texte": "#ffffff", "ok": "#17703f", "ok-fond": "#e4f5ea",
          "critique": "#b42318", "critique-fond": "#fdecea", "haute": "#b4400a", "haute-fond": "#fff0e2",
          "moyenne": "#7a5200", "moyenne-fond": "#fff6d6", "basse": "#1f5fa8", "basse-fond": "#e6f0fb",
          "info": "#4b5563", "info-fond": "#eceff3", "code-fond": "#eef1f5"}
_SOMBRE = {"fond": "#0e131a", "carte": "#161d27", "texte": "#e8ecf2", "doux": "#a5b0be", "bord": "#2a3441", "zebre": "#1a222d",
           "accent": "#8ea8ff", "bandeau": "#0a0f16", "bandeau-texte": "#ffffff", "ok": "#67d896", "ok-fond": "#12301f",
           "critique": "#ff8f86", "critique-fond": "#3a1715", "haute": "#ffa766", "haute-fond": "#3a2211",
           "moyenne": "#f0c24f", "moyenne-fond": "#352a0c", "basse": "#86bcff", "basse-fond": "#14283f",
           "info": "#b3bcc9", "info-fond": "#242d3a", "code-fond": "#212a37"}


def _jeton(d):
    return "".join(f"--{k}:{v};" for k, v in d.items())


CSS = (
    f":root{{{_jeton(_CLAIR)}}}\n"
    f"@media (prefers-color-scheme: dark){{:root{{{_jeton(_SOMBRE)}}}}}\n"
    """
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--fond);color:var(--texte);font:16px/1.6 system-ui,-apple-system,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif}
.page{max-width:1100px;margin:0 auto;padding:0 16px 48px}
.sr{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}
a{color:var(--accent)}
h1,h2,h3,h4,h5,h6{line-height:1.25;margin:1.6em 0 .5em}
h2{font-size:1.65rem;margin-top:0;padding-bottom:.4rem;border-bottom:2px solid var(--accent)}
h3{font-size:1.2rem}
p{margin:.6em 0}
code{background:var(--code-fond);padding:.1em .35em;border-radius:4px;font:.88em ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;overflow-wrap:anywhere}
pre{background:var(--code-fond);padding:12px 14px;border-radius:8px;overflow-x:auto;font-size:.85rem;line-height:1.5}
pre code{background:none;padding:0}
blockquote{margin:1em 0;padding:.2em 1em;border-left:4px solid var(--accent);color:var(--doux)}
hr{border:0;border-top:1px solid var(--bord);margin:2em 0}
.bandeau{background:var(--bandeau);color:var(--bandeau-texte);padding:36px 0 30px}
.bandeau .in{max-width:1100px;margin:0 auto;padding:0 16px}
.bandeau .etiq{font-size:.8rem;letter-spacing:.08em;text-transform:uppercase;opacity:.8;margin:0}
.bandeau h1{margin:.2em 0 .3em;font-size:clamp(1.5rem,4vw,2.3rem);overflow-wrap:anywhere}
.bandeau p{margin:.15em 0;opacity:.9}
.sommaire{display:flex;flex-wrap:wrap;gap:8px 20px;padding:14px 0;margin:0 0 8px;border-bottom:1px solid var(--bord);font-size:.95rem}
section.majeure{padding-top:34px}
.carte{background:var(--carte);border:1px solid var(--bord);border-radius:12px;padding:18px 20px;box-shadow:0 1px 3px rgba(20,30,50,.08)}
.hero{display:grid;grid-template-columns:auto 1fr;gap:26px;align-items:center}
.hero .lecture{font-size:1.1rem;margin:.1em 0}
.hero .lettre{display:inline-grid;place-items:center;width:2.2em;height:2.2em;border-radius:10px;font-weight:700;font-size:1.3rem;margin-right:.5em;vertical-align:middle}
.hero .grand{font-size:2.3rem;font-weight:700;line-height:1.1}
.hero .note-txt{color:var(--doux);font-size:.92rem}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:12px;margin:18px 0 26px}
.kpi{background:var(--carte);border:1px solid var(--bord);border-radius:12px;padding:12px 14px}
.kpi b{display:block;font-size:1.9rem;line-height:1.1}
.ring-fond{stroke:var(--bord)}
.ring-txt{fill:var(--texte);font:700 34px system-ui,sans-serif}
.ring-sous{fill:var(--doux);font:13px system-ui,sans-serif}
.barres{list-style:none;margin:0;padding:0}
.barres li{display:grid;grid-template-columns:minmax(120px,190px) 1fr 3ch;gap:12px;align-items:center;padding:5px 0}
.barres svg{width:100%;height:14px;display:block}
.barres .val{font-weight:700;text-align:right;font-variant-numeric:tabular-nums}
.piste{fill:var(--bord)}
.c-ok{--c:var(--ok);--cf:var(--ok-fond)}.c-critique,.s-critique{--c:var(--critique);--cf:var(--critique-fond)}
.c-haute,.s-haute{--c:var(--haute);--cf:var(--haute-fond)}.c-moyenne,.s-moyenne{--c:var(--moyenne);--cf:var(--moyenne-fond)}
.c-basse,.s-basse{--c:var(--basse);--cf:var(--basse-fond)}.s-info{--c:var(--info);--cf:var(--info-fond)}
.rempli{fill:var(--c)}.ring-val{stroke:var(--c)}
.pastille{display:inline-block;min-width:3em;text-align:center;padding:.1em .55em;border-radius:999px;font-weight:700;font-variant-numeric:tabular-nums;background:var(--cf);color:var(--c);border:1px solid var(--c)}
.hero .lettre{background:var(--cf);color:var(--c);border:2px solid var(--c)}
.chip{display:inline-block;padding:.05em .6em;border-radius:6px;font-size:.78rem;font-weight:700;letter-spacing:.02em;background:var(--cf);color:var(--c);border:1px solid var(--c);white-space:nowrap}
.zero{color:var(--doux)}
.table-wrap{overflow-x:auto;margin:1em 0;border:1px solid var(--bord);border-radius:10px;background:var(--carte)}
table{border-collapse:collapse;width:100%;font-size:.94rem}
th,td{padding:9px 12px;text-align:left;vertical-align:top;border-bottom:1px solid var(--bord)}
thead th{background:var(--code-fond);font-size:.82rem;text-transform:uppercase;letter-spacing:.04em;color:var(--doux);white-space:nowrap}
tbody tr:nth-child(even){background:var(--zebre)}
tbody tr:last-child>*{border-bottom:0}
td.num,th.num{text-align:center;font-variant-numeric:tabular-nums}
td.url{overflow-wrap:anywhere;min-width:180px}
.rapport table{margin:0}
.rapport .table-wrap{margin:1em 0}
.encadre{border:1px dashed var(--accent);border-radius:12px;padding:16px 20px;background:var(--carte)}
.foi{border-left:4px solid var(--ok);background:var(--ok-fond);padding:10px 14px;border-radius:0 8px 8px 0;margin:0 0 18px}
.legende{color:var(--doux);font-size:.88rem}
.cartes{display:grid;gap:16px;margin-top:14px}
.carte h3{margin:0 0 .3em;display:flex;flex-wrap:wrap;gap:8px 12px;align-items:center}
ul.signaux{list-style:none;padding:0;margin:.4em 0 0}
ul.signaux>li{padding:9px 0;border-top:1px solid var(--bord);display:grid;grid-template-columns:auto 1fr;gap:4px 12px}
ul.signaux>li:first-child{border-top:0}
ul.signaux ul{grid-column:2;margin:.2em 0 0;padding-left:1.1em;font-size:.88rem;color:var(--doux)}
.rapport ul,.rapport ol{padding-left:1.4em}
footer{margin-top:44px;padding-top:14px;border-top:1px solid var(--bord);color:var(--doux);font-size:.85rem}
@media (max-width:640px){.hero{grid-template-columns:1fr;justify-items:center;text-align:center}.barres li{grid-template-columns:1fr 3ch}.barres li svg{grid-column:1/-1;grid-row:2}}
@media print{
:root{"""
    + _jeton(_CLAIR)
    + """--bandeau:#ffffff;--bandeau-texte:#14213d}
@page{size:A4;margin:14mm}
html,body{background:#fff}
body{font-size:10.5pt;line-height:1.45}
*{box-shadow:none!important;print-color-adjust:exact;-webkit-print-color-adjust:exact}
.page{max-width:none;padding:0}
.bandeau{margin:0;padding:0 0 12px;border-bottom:3px solid #14213d}
.sommaire{display:none}
section.majeure{padding-top:0;break-before:page}
section.majeure:first-of-type{break-before:auto}
h2,h3,h4{break-after:avoid}
table,.carte,.kpi,.hero,figure,pre,.encadre{break-inside:avoid}
tr{break-inside:avoid}
thead{display:table-header-group}
.table-wrap{overflow:visible}
a{color:inherit;text-decoration:none}
}
"""
)


# --- Notes -----------------------------------------------------------------------------------------------------------
def lettre(note):
    return "A" if note >= 90 else "B" if note >= 75 else "C" if note >= 60 else "D" if note >= 40 else "E"


def _note(cnt):
    return max(0, 100 - sum(MALUS[k] * cnt[k] for k in MALUS))


def notes_par_domaine(sigs, audites=()):
    """{domaine: {note, lettre, critique, haute, moyenne, basse, inclut}}.

    Les domaines de RATTACHE sont comptés avec leur parent (« inclut » les liste). `audites` : domaines mesurés
    même sans constat (note 100), pour ne pas les exclure de la moyenne.
    """
    comptes = {}
    inclus = {}
    for s in sigs:
        dom = RATTACHE.get(s["domaine"], s["domaine"])
        if dom != s["domaine"]:
            inclus.setdefault(dom, [])
            if s["domaine"] not in inclus[dom]:
                inclus[dom].append(s["domaine"])
        c = comptes.setdefault(dom, {k: 0 for k in MALUS})
        if s["severite"] in MALUS:
            c[s["severite"]] += 1
    for d in audites:
        comptes.setdefault(d, {k: 0 for k in MALUS})
    ordre = sorted(comptes, key=lambda d: (list(POIDS).index(d) if d in POIDS else 99, d))
    out = {}
    for d in ordre:
        n = _note(comptes[d])
        out[d] = {"note": n, "lettre": lettre(n), **comptes[d], "inclut": inclus.get(d, [])}
    return out


def note_globale(notes):
    """(note, plafonnee) — moyenne pondérée des domaines présents ; None si aucun."""
    pond = [(POIDS[d], v["note"]) for d, v in notes.items() if d in POIDS]
    if not pond:
        return None, False
    g = round(sum(p * n for p, n in pond) / sum(p for p, _ in pond))
    if any(notes.get(d, {}).get("critique") for d in ("Sécurité", "SEO technique")) and g > 49:
        return 49, True
    return g, False


def notes_audit(audit, sigs=None):
    """Notes par domaine d'un dossier d'audit (signaux bruts) ; `sigs` évite de relire les données si déjà collectés.

    Les domaines dont la source de données existe (crawl, geo, securite, code, Lighthouse) comptent même sans constat.
    """
    audit = Path(audit)
    if sigs is None:
        sigs = signaux.collecter(audit)
    d = audit / "data"
    audites = [dom for dom, chemin in (("SEO technique", "crawl"), ("GEO / IA", "geo"), ("Sécurité", "securite"), ("Code", "code")) if (d / chemin).is_dir()]
    if signaux.lighthouse(audit):
        audites += ["Performance", "Accessibilité"]
    return notes_par_domaine(sigs, audites)


# --- Markdown minimal -> HTML ----------------------------------------------------------------------------------------
def _url_propre(u):
    """URL nettoyée des caractères de contrôle et espaces (que les navigateurs ignorent), ou None si elle n'est pas sûre.

    Liste blanche : http(s), mailto, ancre, chemin absolu (pas //hôte), chemin relatif sans « : » avant le premier / ? #.
    """
    c = re.sub(r"[\x00-\x20\x7f]", "", u)
    if not c or "\\" in c or "&#" in c:
        return None
    if re.match(r"^(https?://|mailto:|#|/(?!/)|\.{1,2}/)", c, re.I):
        return c
    if c.startswith("//") or re.match(r"^[^/?#]*:", c):
        return None
    return c


def _lien(x):
    if "\x00" in x.group(2):  # du code en ligne dans l'URL : ce n'est pas un lien
        return x.group(0)
    url = _url_propre(html.unescape(x.group(2)))
    return f'<a href="{e(url)}" rel="noopener">{x.group(1)}</a>' if url else x.group(1)


def _inline(txt):
    """Texte en ligne -> HTML. Les codes en ligne sont mis de côté (jeton \\x00N\\x00) pour que le gras et l'italique les entourent."""
    morceaux = re.split(r"`([^`]+)`", txt.replace("\x00", ""))
    codes, reste = [], []
    for i, m in enumerate(morceaux):
        if i % 2:
            reste.append(f"\x00{len(codes)}\x00")
            codes.append(f"<code>{e(m)}</code>")
        else:
            reste.append(e(m))
    m = "".join(reste)
    m = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", _lien, m)
    m = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", m)
    m = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<em>\1</em>", m)
    return re.sub(r"\x00(\d+)\x00", lambda x: codes[int(x.group(1))], m)


_SEP = re.compile(r"^\s*\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)*\|?\s*$")
_ITEM = re.compile(r"^(\s*)([-*+]|\d+[.)])\s+(.*)$")


def _cellules(ligne):
    """Cellules d'une ligne de tableau ; un « | » dans du code en ligne ou écrit « \\| » ne sépare pas."""
    s = ligne.strip()
    s = s[1:] if s.startswith("|") else s
    s = s[:-1] if s.endswith("|") and not s.endswith("\\|") else s
    cel, cur, code, i = [], [], False, 0
    while i < len(s):
        ch = s[i]
        if ch == "\\" and s[i + 1:i + 2] == "|":
            cur.append("|")
            i += 2
            continue
        if ch == "`" and (code or "`" in s[i + 1:]):
            code = not code
        if ch == "|" and not code:
            cel.append("".join(cur).strip())
            cur = []
        else:
            cur.append(ch)
        i += 1
    cel.append("".join(cur).strip())
    return cel


_CASE = re.compile(r"^\[([ xX])\]\s+(.*)$", re.S)


def _item_html(parts):
    """Contenu d'un <li> : texte (cases à cocher en symboles), puis paragraphes et blocs de code rattachés."""
    m = _CASE.match(parts[0][1])
    premier = ("☑ " if m.group(1) != " " else "☐ ") + _inline(m.group(2)) if m else _inline(parts[0][1])
    return premier + "".join(f"<p>{_inline(t)}</p>" if k == "p" else t for k, t in parts[1:])


def _liste(items):
    """items : [(indent, ordonne, parts, numero)] -> HTML imbriqué ; un <ol> qui ne commence pas à 1 porte `start`."""
    out, pile = [], []  # pile : [(indent, balise)]
    for indent, ordonne, parts, numero in items:
        balise = "ol" if ordonne else "ul"
        while pile and indent < pile[-1][0]:
            out.append(f"</li></{pile.pop()[1]}>")
        if pile and indent == pile[-1][0]:
            out.append("</li>")
        elif not pile or indent > pile[-1][0]:
            debut = f' start="{numero}"' if ordonne and numero not in (None, 1) else ""
            out.append(f"<{balise}{debut}>")
            pile.append((indent, balise))
        out.append(f"<li>{_item_html(parts)}")
    while pile:
        out.append(f"</li></{pile.pop()[1]}>")
    return "".join(out)


def _bloc_code(lignes, i):
    """Bloc ``` commençant à lignes[i] (éventuellement indenté) -> (<pre><code> échappé, indice suivant). L'indentation d'ouverture est retirée."""
    retrait = len(lignes[i]) - len(lignes[i].lstrip())
    bloc, i = [], i + 1
    while i < len(lignes) and not lignes[i].lstrip().startswith("```"):
        ln = lignes[i]
        bloc.append(ln[min(retrait, len(ln) - len(ln.lstrip())):])
        i += 1
    return f"<pre><code>{e(chr(10).join(bloc))}</code></pre>", i + 1


def markdown_vers_html(md, decalage=0):
    """Sous-ensemble de Markdown (titres, listes, tableaux, gras, code, blocs de code, liens, citations).

    Le HTML brut est échappé. `decalage` descend les niveaux de titres (h1 → h3 avec decalage=2).
    """
    lignes = md.replace("\r\n", "\n").split("\n")
    out, i = [], 0
    while i < len(lignes):
        l = lignes[i]
        if not l.strip():
            i += 1
        elif l.lstrip().startswith("```"):
            bloc, i = _bloc_code(lignes, i)
            out.append(bloc)
        elif re.match(r"^#{1,6}\s", l):
            m = re.match(r"^(#{1,6})\s+(.*?)(?:\s+#+)?\s*$", l)
            n = min(6, len(m.group(1)) + decalage)
            out.append(f"<h{n}>{_inline(m.group(2))}</h{n}>")
            i += 1
        elif re.match(r"^\s*([-*_])(\s*\1){2,}\s*$", l):
            out.append("<hr>")
            i += 1
        elif "|" in l and i + 1 < len(lignes) and _SEP.match(lignes[i + 1]) and len(_cellules(l)) == len(_cellules(lignes[i + 1])):
            tete = _cellules(l)
            i += 2
            corps = []
            while i < len(lignes) and "|" in lignes[i] and lignes[i].strip():
                corps.append(_cellules(lignes[i]))
                i += 1
            th = "".join(f'<th scope="col">{_inline(c)}</th>' for c in tete)
            tr = "".join("<tr>" + "".join(f"<td>{_inline(c)}</td>" for c in r) + "</tr>" for r in corps)
            out.append(f'<div class="table-wrap"><table><thead><tr>{th}</tr></thead><tbody>{tr}</tbody></table></div>')
        elif l.lstrip().startswith(">"):
            bloc = []
            while i < len(lignes) and lignes[i].lstrip().startswith(">"):
                bloc.append(re.sub(r"^\s*>\s?", "", lignes[i]))
                i += 1
            out.append(f"<blockquote>{markdown_vers_html(chr(10).join(bloc), decalage)}</blockquote>")
        elif _ITEM.match(l):
            items, sep = [], False  # item : [indent, ordonne, parts, numero] ; parts : ["t"|"p"|"h", contenu]
            while i < len(lignes):
                ln = lignes[i]
                m = _ITEM.match(ln)
                if m:
                    ordonne = m.group(2)[0].isdigit()
                    items.append([len(m.group(1).expandtabs(4)), ordonne, [["t", m.group(3)]], int(m.group(2)[:-1]) if ordonne else None])
                    i += 1
                elif ln.strip() and ln.startswith((" ", "\t")) and items:
                    parts = items[-1][2]
                    if ln.lstrip().startswith("```"):  # bloc de code rattaché à l'étape courante
                        bloc, i = _bloc_code(lignes, i)
                        parts.append(["h", bloc])
                    else:  # continuation ; après une ligne vide ou un bloc, nouveau paragraphe
                        if sep or parts[-1][0] == "h":
                            parts.append(["p", ln.strip()])
                        else:
                            parts[-1][1] += " " + ln.strip()
                        i += 1
                    sep = False
                elif not ln.strip():
                    j = i
                    while j < len(lignes) and not lignes[j].strip():
                        j += 1
                    if j < len(lignes) and (_ITEM.match(lignes[j]) or (items and lignes[j].startswith((" ", "\t")))):
                        i, sep = j, True
                    else:
                        break
                else:
                    break
            out.append(_liste(items))
        else:
            para = []
            while i < len(lignes) and lignes[i].strip() and not re.match(r"^(#{1,6}\s|\s*```|\s*>)", lignes[i]) and not _ITEM.match(lignes[i]):
                para.append(lignes[i].strip())
                i += 1
            out.append(f"<p>{_inline(' '.join(para))}</p>")
    return "\n".join(out)


# --- Composants HTML -------------------------------------------------------------------------------------------------
def _couleur_note(n):
    return "ok" if n >= 75 else "moyenne" if n >= 40 else "critique"


def _couleur_score(n):
    return "ok" if n >= 90 else "haute" if n >= 50 else "critique"


def chip(sev):
    return f'<span class="chip s-{e(sev)}">{e(SEV_LIBELLE.get(sev, sev))}</span>'


def pastille(n, couleur):
    return f'<span class="pastille c-{couleur}">{e(str(n))}</span>'


def anneau(note, lettre_):
    circ = 2 * 3.14159265 * 52
    plein = circ * note / 100
    return (f'<svg width="150" height="150" viewBox="0 0 120 120" role="img" aria-label="Note globale indicative : {note} sur 100, lettre {lettre_}" '
            f'class="c-{_couleur_note(note)}"><circle class="ring-fond" cx="60" cy="60" r="52" fill="none" stroke-width="11"/>'
            f'<circle class="ring-val" cx="60" cy="60" r="52" fill="none" stroke-width="11" stroke-linecap="round" '
            f'stroke-dasharray="{plein:.1f} {circ:.1f}" transform="rotate(-90 60 60)"/>'
            f'<text class="ring-txt" x="60" y="66" text-anchor="middle">{note}</text>'
            f'<text class="ring-sous" x="60" y="86" text-anchor="middle">/ 100</text></svg>')


def barres(notes):
    li = []
    for d, v in notes.items():
        n = v["note"]
        li.append(f'<li><span>{e(d)}</span><svg class="c-{_couleur_note(n)}" viewBox="0 0 100 14" preserveAspectRatio="none" role="img" '
                  f'aria-label="{e(d)} : {n} sur 100"><rect class="piste" x="0" y="0" width="100" height="14" rx="4"/>'
                  f'<rect class="rempli" x="0" y="0" width="{n}" height="14" rx="4"/></svg><span class="val">{n}</span></li>')
    return f'<ul class="barres">{"".join(li)}</ul>'


def _cnt(n):
    return f'<td class="num{" zero" if not n else ""}">{n}</td>'


def table_domaines(notes):
    lignes = []
    for d, v in notes.items():
        nom = e(d) + (f' <span class="legende">(inclut {e(", ".join(v["inclut"]))})</span>' if v["inclut"] else "")
        lignes.append(f'<tr><th scope="row">{nom}</th><td class="num">{pastille(v["note"], _couleur_note(v["note"]))}</td>'
                      f'<td class="num">{v["lettre"]}</td>{_cnt(v["critique"])}{_cnt(v["haute"])}{_cnt(v["moyenne"])}{_cnt(v["basse"])}'
                      f'<td class="num">{POIDS.get(d, "—")}</td></tr>')
    tete = "".join(('<th scope="col" class="num">%s</th>' if i else '<th scope="col">%s</th>') % t for i, t in
                   enumerate(["Domaine", "Note", "Lettre", "Critique", "Haute", "Moyenne", "Basse", "Poids"]))
    return (f'<div class="table-wrap"><table><caption class="sr">Note indicative par domaine et nombre de signaux par sévérité</caption>'
            f'<thead><tr>{tete}</tr></thead><tbody>{"".join(lignes)}</tbody></table></div>')


def _dict(x):
    return x if isinstance(x, dict) else {}


def _nombre(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _score_td(v):
    if not _nombre(v):
        return '<td class="num zero">—</td>'
    return f'<td class="num">{pastille(round(v), _couleur_score(v))}</td>'


def _metrique_td(m):
    m = _dict(m)
    txt = e(str(m.get("affiche", "—")))
    sc = m.get("score")
    cls = f' class="pastille c-{_couleur_score(sc * 100)}"' if _nombre(sc) else ""
    return f'<td class="num"><span{cls}>{txt}</span></td>' if cls else f'<td class="num">{txt}</td>'


def section_lighthouse(audit):
    runs = [r for r in signaux.lighthouse(audit) if isinstance(r, dict)]
    if not runs:
        return '<p class="encadre">Aucune mesure Lighthouse disponible (étape « lighthouse » non exécutée ou en échec).</p>'
    mode = {"mobile": "Mobile", "desktop": "Ordinateur"}
    lignes = []
    for r in runs:
        sc, m = _dict(r.get("scores")), _dict(r.get("metriques"))
        lignes.append(f'<tr><th scope="row" class="url">{e(str(r.get("url", "")))}</th><td>{e(mode.get(r.get("strategie"), str(r.get("strategie", "—"))))}</td>'
                      + "".join(_score_td(sc.get(k)) for k in ("performance", "accessibility", "best-practices", "seo"))
                      + "".join(_metrique_td(m.get(k)) for k in ("LCP", "CLS", "TBT")) + "</tr>")
    tete = "".join(f'<th scope="col">{t}</th>' for t in ["Page", "Mode", "Perf.", "Access.", "Bonnes prat.", "SEO", "LCP", "CLS", "TBT"])
    out = ['<p class="legende">Scores Lighthouse (labo) : '
           f'{pastille("≥ 90", "ok")} bon · {pastille("50-89", "haute")} à améliorer · {pastille("< 50", "critique")} faible. '
           'Ils varient de ±5 à 10 points d’un passage à l’autre : ne pas conclure sur un écart plus petit.</p>',
           f'<div class="table-wrap"><table><caption class="sr">Scores Lighthouse par page et par mode</caption><thead><tr>{tete}</tr></thead>'
           f'<tbody>{"".join(lignes)}</tbody></table></div>']
    terrain = []
    for r in runs:
        for cle, port in (("terrain_page", "Page"), ("terrain_origine", "Origine")):
            fd = r.get(cle)
            if fd and isinstance(fd, dict):
                terrain.append((r, port, fd))
    if terrain:
        cols = []
        for _, _, fd in terrain:
            cols += [k for k, v in fd.items() if isinstance(v, dict) and k not in cols]
        lg = []
        for r, port, fd in terrain:
            cel = ""
            for c in cols:
                v = fd.get(c)
                if isinstance(v, dict):
                    couleur = {"bon": "ok", "à améliorer": "haute", "mauvais": "critique"}.get(v.get("verdict"), "basse")
                    cel += f'<td class="num">{e(str(v.get("p75", "—")))} <span class="chip s-{"info" if couleur == "basse" else couleur}">{e(str(v.get("verdict", "")))}</span></td>'
                else:
                    cel += '<td class="num zero">—</td>'
            lg.append(f'<tr><th scope="row" class="url">{e(str(r.get("url", "")))}</th><td>{e(str(r.get("strategie", "")))}</td><td>{port}</td>{cel}</tr>')
        th = "".join(f'<th scope="col">{e(t)}</th>' for t in ["Page", "Mode", "Périmètre"] + cols)
        out += ['<h3>Données terrain (CrUX, p75 des visiteurs réels sur 28 jours)</h3>',
                f'<div class="table-wrap"><table><thead><tr>{th}</tr></thead><tbody>{"".join(lg)}</tbody></table></div>']
    else:
        out.append('<p class="legende">Pas de données terrain (CrUX) : trafic Chrome insuffisant ou mesure locale ; se fier au labo et mesurer en RUM.</p>')
    return "".join(out)


def _li_signal(s, liens=None):
    ex = f'<ul>{"".join(f"<li><code>{e(str(x))}</code></li>" for x in s["exemples"])}</ul>' if s["exemples"] else ""
    return f'<li>{chip(s["severite"])}<span>{e(s["texte"])}{_lien_corriger(s, liens)}</span>{ex}</li>'


def section_signaux(sigs, liens=None):
    if not sigs:
        return "<p>Aucun signal automatique.</p>"
    top = "".join(f'<tr><td class="num">{i}</td><td>{chip(s["severite"])}</td><td>{e(s["domaine"])}</td><td>{e(s["texte"])}{_lien_corriger(s, liens)}</td></tr>'
                  for i, s in enumerate(sigs[:15], 1))
    tete = "".join(f'<th scope="col">{t}</th>' for t in ["#", "Sévérité", "Domaine", "Constat"])
    out = [f'<h3>Top {min(15, len(sigs))} des signaux</h3>',
           f'<div class="table-wrap"><table><caption class="sr">Signaux les plus graves</caption><thead><tr>{tete}</tr></thead><tbody>{top}</tbody></table></div>',
           '<h3>Tous les signaux par domaine</h3><div class="cartes">']
    doms = []
    for s in sorted(sigs, key=lambda s: (list(POIDS).index(s["domaine"]) if s["domaine"] in POIDS else 50 + (s["domaine"] in RATTACHE), s["domaine"])):
        if s["domaine"] not in doms:
            doms.append(s["domaine"])
    for d in doms:
        ss = [s for s in sigs if s["domaine"] == d]
        cnt = "".join(f'{chip(k)} <span class="legende">×{sum(1 for s in ss if s["severite"] == k)}</span> ' for k in signaux.ORDRE if any(s["severite"] == k for s in ss))
        out.append(f'<article class="carte"><h3>{e(d)} <small>{cnt}</small></h3><ul class="signaux">{"".join(_li_signal(s, liens) for s in ss)}</ul></article>')
    return "".join(out) + "</div>"


def liste_fichiers(audit):
    d = Path(audit) / "data"
    if not d.is_dir():
        return "<p>Aucun fichier de données.</p>"
    lg = "".join(f'<tr><th scope="row"><code>{e(p.relative_to(audit).as_posix())}</code></th><td class="num">{max(1, round(p.stat().st_size / 1024))} Ko</td></tr>'
                 for p in sorted(d.rglob("*")) if p.is_file() and p.name != "COLLECTE.md")
    return ('<div class="table-wrap"><table><caption class="sr">Fichiers de données</caption><thead><tr><th scope="col">Fichier</th>'
            f'<th scope="col" class="num">Taille</th></tr></thead><tbody>{lg}</tbody></table></div>')


# --- Dossier CORRECTIONS/ : plan de correction et guides en annexe ---------------------------------------------------
_NUM = re.compile(r"[0-9]{2,3}")
_FICHIER = re.compile(r"[0-9]{2,3}-[a-z0-9-]+\.md")  # nom simple : ni séparateur de chemin, ni « .. »
_FRONTMATTER = re.compile(r"\A---[ \t]*\n.*?\n---[ \t]*(\n|\Z)", re.S)
TAILLE_MAX_FICHE = 512 * 1024
MENTION_CORRECTIONS = "Le dossier CORRECTIONS/ contient ces mêmes fiches, à donner à votre agent de code."
_DOSSIER_CORRECTIONS = re.compile(r"CORRECTIONS(-[0-9TZ:-]+)?")  # même motif que corrections.py : nom simple, sans séparateur
POINTEUR_CORRECTIONS = "data/corrections-dossier.txt"

# Ajouté à la feuille de style seulement quand le dossier CORRECTIONS/ est exploitable (sinon la page reste inchangée).
CSS_CORRECTIONS = """
.corriger{display:block;font-size:.88rem;margin-top:.15em}
.fiche{margin-top:2em;padding-top:1em;border-top:2px solid var(--bord)}
.fiche .fiche-num{margin:0;color:var(--doux);font-size:.85rem;font-weight:700;letter-spacing:.04em;text-transform:uppercase}
.fiche h3{margin-top:.3em}
@media print{
.fiche{break-before:page;margin-top:0;padding-top:0;border-top:0}
.fiche pre{white-space:pre-wrap;overflow-wrap:anywhere;overflow:visible;break-inside:auto}
.fiche .table-wrap{overflow:visible}
}
"""


def _avertir(msg):
    print(f"rapport_html : CORRECTIONS/ — {msg}", file=sys.stderr)


def _texte(v):
    return v if isinstance(v, str) else ("" if v is None else str(v))


def _signaux_index(v):
    """Couples (source, cle) valides d'une entrée d'index."""
    return [(_texte(x.get("source")), cle_jointure(_texte(x.get("cle")))) for x in (v if isinstance(v, list) else [])
            if isinstance(x, dict) and _texte(x.get("source")) and cle_jointure(_texte(x.get("cle")))]


def nom_dossier_corrections(audit):
    """Nom du dossier de corrections à lire : celui de data/corrections-dossier.txt s'il est valide (une seule ligne, motif
    CORRECTIONS ou CORRECTIONS-<horodatage>, 64 caractères au plus, aucun séparateur), sinon « CORRECTIONS »."""
    try:
        with open(Path(audit) / POINTEUR_CORRECTIONS, "rb") as f:
            brut = f.read(256)
        texte = brut.decode("utf-8")
    except (OSError, UnicodeDecodeError, ValueError):
        return "CORRECTIONS"
    if texte.endswith("\n"):
        texte = texte[:-1]
    if len(texte) <= 64 and _DOSSIER_CORRECTIONS.fullmatch(texte):  # 64 : bien au-dessus d'un horodatage, sous la limite des noms de fichier
        return texte
    _avertir(f"data/corrections-dossier.txt invalide ({texte[:40]!r}), dossier CORRECTIONS/ utilisé")
    return "CORRECTIONS"


def charger_corrections(audit):
    """Corrections décrites par DOSSIER_AUDIT/CORRECTIONS/index.json, ou None si la page doit rester inchangée.
    Le dossier lu est celui que désigne data/corrections-dossier.txt (CORRECTIONS-<horodatage>/ si l'ancien a été conservé).

    Renvoie {"corrections": [{num, titre, domaine, severite, effort, cles, corps}], "sans_fiche": [texte]} trié par numéro.
    Tout ce qui est invalide (JSON, version, entrée, nom de fichier, fiche absente ou illisible) est ignoré avec un
    avertissement sur stderr ; sans aucune correction utilisable, renvoie None.
    """
    nom_dossier = nom_dossier_corrections(audit)
    dossier = Path(audit) / nom_dossier
    index = dossier / "index.json"
    try:
        refuse = nom_dossier != "CORRECTIONS" and (dossier.is_symlink() or not index.is_file())
    except OSError:
        refuse = True
    if refuse:
        _avertir(f"{nom_dossier}/ absent ou non exploitable, section ignorée")
        return None
    if not index.is_file():
        return None
    try:
        data = json.loads(index.read_text(encoding="utf-8"))
    except (OSError, ValueError, RecursionError) as ex:
        _avertir(f"index.json illisible ({ex.__class__.__name__}), section ignorée")
        return None
    if not isinstance(data, dict) or data.get("version") != 1 or not isinstance(data.get("corrections"), list):
        _avertir("index.json invalide ou de version non gérée (attendu : version 1), section ignorée")
        return None
    racine = dossier.resolve()
    corrections, vus = [], set()
    for brut in data["corrections"]:
        if not isinstance(brut, dict):
            _avertir("entrée de correction invalide, ignorée")
            continue
        num, nom = brut.get("num"), brut.get("fichier")
        if not isinstance(num, str) or not _NUM.fullmatch(num) or num in vus:
            _avertir(f"numéro de correction invalide ou en double ({num!r}), ignoré")
            continue
        if not isinstance(nom, str) or not _FICHIER.fullmatch(nom):
            _avertir(f"correction {num} : nom de fichier refusé ({nom!r}), ignorée")
            continue
        chemin = dossier / nom
        try:
            if chemin.is_symlink() or chemin.resolve().parent != racine:
                raise OSError("hors du dossier")
            if chemin.stat().st_size > TAILLE_MAX_FICHE:
                _avertir(f"correction {num} : fiche {nom} trop volumineuse (> {TAILLE_MAX_FICHE // 1024} Ko), ignorée")
                continue
            md = chemin.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            _avertir(f"correction {num} : fiche {nom} absente ou illisible, ignorée")
            continue
        vus.add(num)
        corrections.append({"num": num, "titre": _texte(brut.get("titre")) or _texte(brut.get("id")) or f"Correction {num}",
                            "domaine": _texte(brut.get("domaine")), "severite": _texte(brut.get("severite")),
                            "effort": _texte(brut.get("effort")), "cles": _signaux_index(brut.get("signaux")),
                            "corps": _FRONTMATTER.sub("", md.replace("\r\n", "\n"), count=1)})
    if not corrections:
        return None
    corrections.sort(key=lambda c: (int(c["num"]), c["num"]))
    sans = data.get("sans_fiche")
    sans = [_texte(x.get("texte")) for x in sans if isinstance(x, dict) and _texte(x.get("texte"))] if isinstance(sans, list) else []
    return {"corrections": corrections, "sans_fiche": sans, "dossier": nom_dossier}


def mention_corrections(corr):
    """MENTION_CORRECTIONS avec le nom du dossier réellement lu (CORRECTIONS/ ou CORRECTIONS-<horodatage>/)."""
    nom = corr.get("dossier") or "CORRECTIONS"
    return MENTION_CORRECTIONS.replace("CORRECTIONS/", nom + "/", 1)


def liens_signaux(corr):
    """{(source, cle): [numéros triés]} — un signal correspond à une correction si (source, cle) figure dans ses signaux."""
    liens = {}
    for c in corr["corrections"]:
        for k in c["cles"]:
            if c["num"] not in liens.setdefault(k, []):
                liens[k].append(c["num"])
    return liens


def _lien_corriger(s, liens):
    nums = (liens or {}).get((_texte(s.get("source")), cle_jointure(_texte(s.get("cle")))))
    if not nums:
        return ""
    return ('<span class="corriger">Comment corriger → '
            + ", ".join(f'<a href="#correction-{e(n)}">{e(n)}</a>' for n in nums) + "</span>")


def section_plan(corr):
    lignes = []
    for c in corr["corrections"]:
        sev = c["severite"] if c["severite"] in SEV_LIBELLE else "info"
        ancre = f"#correction-{e(c['num'])}"
        lignes.append(f'<tr><td class="num"><a href="{ancre}">{e(c["num"])}</a></td><td>{e(c["titre"])}</td><td>{e(c["domaine"])}</td>'
                      f'<td>{chip(sev)}</td><td class="num">{e(c["effort"]) or "—"}</td><td><a href="{ancre}">Voir le guide</a></td></tr>')
    tete = "".join(('<th scope="col" class="num">%s</th>' if t in ("N°", "Effort") else '<th scope="col">%s</th>') % t
                   for t in ["N°", "Correction", "Domaine", "Sévérité", "Effort", "Guide"])
    sans = ""
    if corr["sans_fiche"]:
        sans = ('<h3>Constats sans guide dédié</h3><ul>' + "".join(f"<li>{e(t)}</li>" for t in corr["sans_fiche"]) + "</ul>")
    return (f'<p>{e(mention_corrections(corr))} Chaque guide est reproduit en fin de rapport, dans l’annexe « Guides de correction ».</p>'
            f'<div class="table-wrap"><table><caption class="sr">Plan de correction : guides, domaine, sévérité et effort</caption>'
            f'<thead><tr>{tete}</tr></thead><tbody>{"".join(lignes)}</tbody></table></div>{sans}')


def section_guides(corr):
    sommaire = "".join(f'<li><a href="#correction-{e(c["num"])}">{e(c["num"])} — {e(c["titre"])}</a></li>' for c in corr["corrections"])
    fiches = []
    for c in corr["corrections"]:
        titre = "" if c["corps"].lstrip().startswith("#") else f'<h3>{e(c["titre"])}</h3>'
        fiches.append(f'<article class="fiche rapport" id="correction-{e(c["num"])}"><p class="fiche-num">Guide {e(c["num"])}</p>'
                      f'{titre}{markdown_vers_html(c["corps"], decalage=2)}</article>')
    return f'<p>{e(mention_corrections(corr))}</p><ol>{sommaire}</ol>{"".join(fiches)}'


# --- Page ------------------------------------------------------------------------------------------------------------
def version_plugin():
    try:
        p = Path(__file__).resolve().parents[3] / ".claude-plugin/plugin.json"
        return str(json.loads(p.read_text(encoding="utf-8")).get("version") or "dev")
    except Exception:
        return "dev"


def date_audit(audit, collecte):
    for texte in (Path(audit).resolve().name, collecte.splitlines()[0] if collecte else ""):
        m = re.search(r"(\d{4})-(\d{2})-(\d{2})", texte)
        if m and 1 <= int(m.group(2)) <= 12:
            return f"{int(m.group(3))} {MOIS[int(m.group(2)) - 1]} {m.group(1)}"
    t = date.today()
    return f"{t.day} {MOIS[t.month - 1]} {t.year}"


def _lu(p):
    try:
        return Path(p).read_text(encoding="utf-8")
    except Exception:
        return ""


def generer(audit):
    audit = Path(audit)
    sigs = signaux.collecter(audit)
    meta = signaux.meta_crawl(audit)
    site = str(meta.get("start_url") or audit.resolve().name)
    collecte = _lu(audit / "data/COLLECTE.md")
    priorise = _lu(audit / "RAPPORT-AUDIT.md")
    notes = notes_audit(audit, sigs)
    glob, plafonnee = note_globale(notes)
    ver = version_plugin()
    total = {k: sum(1 for s in sigs if s["severite"] == k) for k in MALUS}
    corr = charger_corrections(audit)
    liens = liens_signaux(corr) if corr else None

    if glob is None:
        hero = '<div class="carte"><p>Aucun domaine évalué automatiquement : voir le rapport priorisé.</p></div>'
    else:
        lt = lettre(glob)
        cap = ('<p class="note-txt">Note plafonnée à 49/100 : au moins un constat critique en sécurité ou en SEO technique.</p>' if plafonnee else "")
        hero = (f'<div class="carte hero c-{_couleur_note(glob)}">{anneau(glob, lt)}<div>'
                f'<p class="note-txt">Note globale indicative (signaux automatiques)</p>'
                f'<p class="grand"><span class="lettre">{lt}</span>{glob}/100</p><p class="lecture">{e(LECTURE[lt])}</p>{cap}'
                f'<p class="note-txt">Moyenne pondérée des domaines évalués ({e(", ".join(notes))}), poids de la grille de notation. '
                f'Le contenu éditorial et les jugements qualitatifs relèvent du rapport priorisé.</p></div></div>')
    kpis = "".join(f'<div class="kpi s-{k}"><b>{v}</b>{chip(k)}</div>' for k, v in total.items())
    if priorise:
        foi = '<p class="foi"><strong>Notes du rapport priorisé : elles font foi.</strong> Les notes de la synthèse ci-dessus sont des indications calculées sur les signaux bruts.</p>'
        corps = f'<div class="rapport">{markdown_vers_html(priorise, decalage=2)}</div>'
    else:
        foi = ""
        corps = ('<div class="encadre"><p><strong>Rapport priorisé non encore rédigé.</strong> Lancer le skill <code>audit-complet</code> '
                 'dans Claude Code ou Cursor pour obtenir les constats dédoublonnés, hiérarchisés, avec les correctifs adaptés au code.</p></div>')

    sections = [
        ("synthese", "Synthèse", f'{hero}<div class="kpis">{kpis}</div><h3>Note par domaine</h3><div class="carte">{barres(notes)}</div>{table_domaines(notes)}'),
        ("lighthouse", "Lighthouse", section_lighthouse(audit)),
        ("priorise", "Rapport priorisé", foi + corps),
        ("signaux", "Signaux détectés", section_signaux(sigs, liens)),
        ("annexes", "Annexes", f'<h3>Statut de la collecte</h3><div class="rapport">{markdown_vers_html(collecte, decalage=3) if collecte else "<p>Pas de fichier COLLECTE.md.</p>"}</div>'
                              f'<h3>Fichiers de données</h3>{liste_fichiers(audit)}'),
    ]
    if corr:
        sections.insert(1, ("plan-correction", "Plan de correction", section_plan(corr)))
        sections.append(("guides", "Guides de correction", section_guides(corr)))
    nav = "".join(f'<a href="#{i}">{t}</a>' for i, t, _ in sections)
    corps_page = "".join(f'<section class="majeure" id="{i}"><h2>{t}</h2>{c}</section>' for i, t, c in sections)
    css = CSS + (CSS_CORRECTIONS if corr else "")
    vtxt = f"v{e(ver)}" if ver != "dev" else "(version de développement)"
    return (f'<!doctype html>\n<html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<meta name="color-scheme" content="light dark"><title>Audit — {e(site)}</title><style>{css}</style></head><body>'
            f'<header class="bandeau"><div class="in"><p class="etiq">Audit de site web</p><h1>Audit du site — {e(site)}</h1>'
            f'<p>{e(date_audit(audit, collecte))}</p><p>Rapport généré par audit-site-astro {vtxt}</p></div></header><div class="page">'
            f'<nav class="sommaire" aria-label="Sommaire">{nav}</nav><main>{corps_page}</main>'
            f'<footer>Notes indicatives calculées sur les signaux automatiques (barème : 100 − 20 × critiques − 10 × hautes − 4 × moyennes − 1 × basse).</footer>'
            f'</div></body></html>\n')


def main():
    ap = argparse.ArgumentParser(description="Génère RAPPORT.html à partir d'un dossier d'audit")
    ap.add_argument("audit", help="DOSSIER_AUDIT")
    ap.add_argument("--sortie", help="fichier de sortie (défaut : DOSSIER_AUDIT/RAPPORT.html)")
    a = ap.parse_args()
    cible = Path(a.sortie) if a.sortie else Path(a.audit) / "RAPPORT.html"
    cible.write_text(generer(Path(a.audit)), encoding="utf-8")
    print(cible)


if __name__ == "__main__":
    main()
