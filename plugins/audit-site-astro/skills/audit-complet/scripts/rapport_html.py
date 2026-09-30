#!/usr/bin/env python3
"""
rapport_html.py — Page web autonome RAPPORT.html à partir de DOSSIER_AUDIT (données + rapport priorisé).

Usage : python3 rapport_html.py DOSSIER_AUDIT [--sortie FICHIER]     (défaut : DOSSIER_AUDIT/RAPPORT.html)

Un seul fichier HTML : CSS en ligne, SVG en ligne, aucun JavaScript, aucune ressource externe. Lisible hors ligne,
clair/sombre selon le système, imprimable en A4 (c'est aussi la source du PDF). Tout texte issu du site audité
ou des fichiers de données passe par html.escape.

API : notes_par_domaine(signaux), markdown_vers_html(md), generer(audit) -> HTML complet.
"""
import argparse
import html
import json
import os
import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import signaux  # noqa: E402

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


# --- Markdown minimal -> HTML ----------------------------------------------------------------------------------------
def _url_sure(u):
    return bool(re.match(r"^(https?://|mailto:|#|/|\./|\.\./)", u)) or not re.match(r"^[a-zA-Z][\w+.-]*:", u)


def _inline(txt):
    morceaux = re.split(r"`([^`]+)`", txt)
    out = []
    for i, m in enumerate(morceaux):
        if i % 2:
            out.append(f"<code>{e(m)}</code>")
            continue
        m = e(m)
        m = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)",
                   lambda x: f'<a href="{x.group(2)}" rel="noopener">{x.group(1)}</a>' if _url_sure(html.unescape(x.group(2))) else x.group(1), m)
        m = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", m)
        m = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<em>\1</em>", m)
        out.append(m)
    return "".join(out)


_SEP = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$")
_ITEM = re.compile(r"^(\s*)([-*+]|\d+[.)])\s+(.*)$")


def _cellules(ligne):
    return [c.strip() for c in ligne.strip().strip("|").split("|")]


def _liste(items):
    """items : [(indent, ordonne, texte)] -> HTML imbriqué."""
    out, pile = [], []  # pile : [(indent, balise)]
    for indent, ordonne, texte in items:
        balise = "ol" if ordonne else "ul"
        while pile and indent < pile[-1][0]:
            out.append(f"</li></{pile.pop()[1]}>")
        if pile and indent == pile[-1][0]:
            out.append("</li>")
        elif not pile or indent > pile[-1][0]:
            out.append(f"<{balise}>")
            pile.append((indent, balise))
        out.append(f"<li>{_inline(texte)}")
    while pile:
        out.append(f"</li></{pile.pop()[1]}>")
    return "".join(out)


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
            bloc, i = [], i + 1
            while i < len(lignes) and not lignes[i].lstrip().startswith("```"):
                bloc.append(lignes[i])
                i += 1
            i += 1
            out.append(f"<pre><code>{e(chr(10).join(bloc))}</code></pre>")
        elif re.match(r"^#{1,6}\s", l):
            m = re.match(r"^(#{1,6})\s+(.*?)\s*#*\s*$", l)
            n = min(6, len(m.group(1)) + decalage)
            out.append(f"<h{n}>{_inline(m.group(2))}</h{n}>")
            i += 1
        elif re.match(r"^\s*([-*_])(\s*\1){2,}\s*$", l):
            out.append("<hr>")
            i += 1
        elif "|" in l and i + 1 < len(lignes) and _SEP.match(lignes[i + 1]) and "-" in lignes[i + 1]:
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
            items = []
            while i < len(lignes):
                m = _ITEM.match(lignes[i])
                if m:
                    items.append([len(m.group(1).expandtabs(4)), m.group(2)[0].isdigit(), m.group(3)])
                    i += 1
                elif lignes[i].strip() and lignes[i].startswith((" ", "\t")) and items:  # continuation
                    items[-1][2] += " " + lignes[i].strip()
                    i += 1
                elif not lignes[i].strip() and i + 1 < len(lignes) and _ITEM.match(lignes[i + 1]):
                    i += 1
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


def _score_td(v):
    if not isinstance(v, (int, float)):
        return '<td class="num zero">—</td>'
    return f'<td class="num">{pastille(round(v), _couleur_score(v))}</td>'


def _metrique_td(m):
    m = m or {}
    txt = e(str(m.get("affiche", "—")))
    sc = m.get("score")
    cls = f' class="pastille c-{_couleur_score(sc * 100)}"' if isinstance(sc, (int, float)) else ""
    return f'<td class="num"><span{cls}>{txt}</span></td>' if cls else f'<td class="num">{txt}</td>'


def section_lighthouse(audit):
    runs = signaux.lighthouse(audit)
    if not runs:
        return '<p class="encadre">Aucune mesure Lighthouse disponible (étape « lighthouse » non exécutée ou en échec).</p>'
    mode = {"mobile": "Mobile", "desktop": "Ordinateur"}
    lignes = []
    for r in runs:
        sc, m = r.get("scores", {}), r.get("metriques", {})
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
            if fd:
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


def _li_signal(s):
    ex = f'<ul>{"".join(f"<li><code>{e(str(x))}</code></li>" for x in s["exemples"])}</ul>' if s["exemples"] else ""
    return f'<li>{chip(s["severite"])}<span>{e(s["texte"])}</span>{ex}</li>'


def section_signaux(sigs):
    if not sigs:
        return "<p>Aucun signal automatique.</p>"
    top = "".join(f'<tr><td class="num">{i}</td><td>{chip(s["severite"])}</td><td>{e(s["domaine"])}</td><td>{e(s["texte"])}</td></tr>'
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
        out.append(f'<article class="carte"><h3>{e(d)} <small>{cnt}</small></h3><ul class="signaux">{"".join(_li_signal(s) for s in ss)}</ul></article>')
    return "".join(out) + "</div>"


def liste_fichiers(audit):
    d = Path(audit) / "data"
    if not d.is_dir():
        return "<p>Aucun fichier de données.</p>"
    lg = "".join(f'<tr><th scope="row"><code>{e(p.relative_to(audit).as_posix())}</code></th><td class="num">{max(1, round(p.stat().st_size / 1024))} Ko</td></tr>'
                 for p in sorted(d.rglob("*")) if p.is_file() and p.name != "COLLECTE.md")
    return ('<div class="table-wrap"><table><caption class="sr">Fichiers de données</caption><thead><tr><th scope="col">Fichier</th>'
            f'<th scope="col" class="num">Taille</th></tr></thead><tbody>{lg}</tbody></table></div>')


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
    d = audit / "data"
    audites = [dom for dom, chemin in (("SEO technique", "crawl"), ("GEO / IA", "geo"), ("Sécurité", "securite"), ("Code", "code")) if (d / chemin).is_dir()]
    if signaux.lighthouse(audit):
        audites += ["Performance", "Accessibilité"]
    notes = notes_par_domaine(sigs, audites)
    glob, plafonnee = note_globale(notes)
    ver = version_plugin()
    total = {k: sum(1 for s in sigs if s["severite"] == k) for k in MALUS}

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
        ("signaux", "Signaux détectés", section_signaux(sigs)),
        ("annexes", "Annexes", f'<h3>Statut de la collecte</h3><div class="rapport">{markdown_vers_html(collecte, decalage=3) if collecte else "<p>Pas de fichier COLLECTE.md.</p>"}</div>'
                              f'<h3>Fichiers de données</h3>{liste_fichiers(audit)}'),
    ]
    nav = "".join(f'<a href="#{i}">{t}</a>' for i, t, _ in sections)
    corps_page = "".join(f'<section class="majeure" id="{i}"><h2>{t}</h2>{c}</section>' for i, t, c in sections)
    vtxt = f"v{e(ver)}" if ver != "dev" else "(version de développement)"
    return (f'<!doctype html>\n<html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<meta name="color-scheme" content="light dark"><title>Audit — {e(site)}</title><style>{CSS}</style></head><body>'
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
