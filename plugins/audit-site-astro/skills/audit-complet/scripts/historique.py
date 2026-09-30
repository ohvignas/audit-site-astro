#!/usr/bin/env python3
"""
historique.py — Page index.html : historique des audits d'un site et évolution des notes.

Usage : python3 historique.py DOSSIER_SITE [--sortie FICHIER]     (défaut : DOSSIER_SITE/index.html)
        DOSSIER_SITE contient un sous-dossier AAAA-MM-JJ par audit (avec data/, RAPPORT.html, RAPPORT.pdf…).

Régénérée à chaque audit (dernière étape de collect_all.sh) : elle reflète toujours l'état actuel du dossier.
Garde-fou : refus (code 2, rien n'est écrit) si le fichier de sortie existe sans être une page de cet outil (marqueur
<meta name="generator" content="audit-site-astro historique">), ou si le dossier n'a aucun sous-dossier AAAA-MM-JJ et pas
encore de page historique : ce n'est alors pas un dossier de site (ex. racine d'un projet qui a son propre index.html).
Même règles que RAPPORT.html : un seul fichier, CSS et SVG en ligne, aucun JavaScript, aucune ressource externe,
clair/sombre, imprimable en A4, tout texte dynamique échappé. Liens relatifs vers RAPPORT.html / RAPPORT.pdf de
chaque audit, seulement quand ces fichiers existent.

API : audits(dossier_site) -> liste triée par date de {date, chemin, note_globale, plafonnee, notes, perf_mobile}.
"""
import argparse
import os
import re
import statistics
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rapport_html as rh  # noqa: E402
import signaux  # noqa: E402

e = rh.e
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
MARQUEUR = '<meta name="generator" content="audit-site-astro historique">'

CSS_HISTORIQUE = """
.hero-histo{display:grid;grid-template-columns:auto 1fr;gap:10px 26px;align-items:center;margin-bottom:18px}
.hero-histo .grand{font-size:2.3rem;font-weight:700;line-height:1.1;margin:0}
.hero-histo .lettre{display:inline-grid;place-items:center;width:2.2em;height:2.2em;border-radius:10px;font-weight:700;font-size:1.3rem;margin-right:.5em;vertical-align:middle;background:var(--cf);color:var(--c);border:2px solid var(--c)}
.hero-histo p{margin:.15em 0}
.courbe-wrap{background:var(--carte);border:1px solid var(--bord);border-radius:12px;padding:12px}
.courbe-wrap svg{display:block;width:100%;height:auto}
.grille{stroke:var(--bord);stroke-width:1}
.axe{fill:var(--doux);font:12px system-ui,sans-serif}
.courbe{fill:none;stroke:var(--accent);stroke-width:3;stroke-linejoin:round;stroke-linecap:round}
.pt{stroke:var(--carte);stroke-width:2}
.val-pt{fill:var(--texte);font:700 13px system-ui,sans-serif}
.delta{font-weight:700;white-space:nowrap;font-variant-numeric:tabular-nums}
.delta.hausse{color:var(--ok)}.delta.baisse{color:var(--critique)}.delta.stable,.delta.na{color:var(--doux)}
table.histo th{white-space:normal}
table.histo td.date{white-space:nowrap}
table.histo td.liens{white-space:nowrap}
table.histo td.liens a+a{margin-left:.8em}
.plafond{color:var(--doux);font-size:.8rem}
@media (max-width:640px){.hero-histo{grid-template-columns:1fr}}
@media print{
.hero-histo,.courbe-wrap{break-inside:avoid}
table.histo{font-size:8.5pt}
th,td{padding:5px 6px}
.bandeau{padding-top:0}
section.majeure{break-before:auto;padding-top:18px}
}
"""


# --- Lecture des audits ----------------------------------------------------------------------------------------------
def _date_valide(nom):
    if not _DATE.match(nom):
        return False
    try:
        datetime.strptime(nom, "%Y-%m-%d")
    except ValueError:
        return False
    return True


def _perf_mobile(audit):
    """Médiane (entier) des scores de performance mobile des pages mesurées, ou None."""
    scores = []
    for r in signaux.lighthouse(audit):
        if not isinstance(r, dict) or r.get("strategie") != "mobile":
            continue
        sc = r.get("scores")
        v = sc.get("performance") if isinstance(sc, dict) else None
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            scores.append(v)
    return int(statistics.median(scores) + 0.5) if scores else None


def _lire_audit(chemin, date):
    try:
        notes = rh.notes_audit(chemin)
        glob, plafonnee = rh.note_globale(notes)
    except Exception as exc:  # données illisibles : l'audit reste listé, sans note
        print(f"⚠️ {date} : notes non calculables ({exc})", file=sys.stderr)
        notes, glob, plafonnee = {}, None, False
    try:
        perf = _perf_mobile(chemin)
    except Exception:
        perf = None
    return {"date": date, "chemin": chemin, "note_globale": glob, "plafonnee": plafonnee, "notes": notes, "perf_mobile": perf}


def audits(dossier_site):
    """Audits de DOSSIER_SITE : sous-dossiers AAAA-MM-JJ contenant data/, triés par date croissante."""
    site = Path(dossier_site)
    if not site.is_dir():
        return []
    trouves = []
    for p in site.iterdir():
        if _date_valide(p.name) and p.is_dir() and (p / "data").is_dir():
            trouves.append(p)
    return [_lire_audit(p, p.name) for p in sorted(trouves, key=lambda p: p.name)]


# --- Rendu -----------------------------------------------------------------------------------------------------------
def _date_longue(iso):
    a, m, j = iso.split("-")
    return f"{int(j)} {rh.MOIS[int(m) - 1]} {a}"


def _date_courte(iso):
    a, m, j = iso.split("-")
    return f"{j}/{m}/{a}"


def _ecarts(liste):
    """Écart de note globale avec l'audit précédent qui en a une, par index (None si indisponible)."""
    out, prec = [], None
    for a in liste:
        n = a["note_globale"]
        out.append(None if n is None or prec is None else n - prec)
        if n is not None:
            prec = n
    return out


def delta_html(ecart, premier=False):
    if ecart is None:
        return f'<span class="delta na">{"premier audit" if premier else "—"}</span>'
    if ecart > 0:
        return f'<span class="delta hausse">▲ +{ecart} pt{"s" if ecart > 1 else ""}</span>'
    if ecart < 0:
        return f'<span class="delta baisse">▼ −{-ecart} pt{"s" if ecart < -1 else ""}</span>'
    return '<span class="delta stable">= 0 pt</span>'


def _premier_avec_note(liste, i):
    return all(a["note_globale"] is None for a in liste[:i])


def courbe_svg(liste):
    """Courbe SVG de la note globale (0-100) dans le temps ; points espacés régulièrement, un par audit noté."""
    pts = [a for a in liste if a["note_globale"] is not None]
    if not pts:
        return '<p class="encadre">Aucune note globale calculable pour ces audits.</p>'
    W, H, gauche, droite, haut, bas = 720, 290, 46, 28, 30, 50
    lw, lh = W - gauche - droite, H - haut - bas
    n = len(pts)
    coords = []
    for i, a in enumerate(pts):
        x = gauche + (lw * i / (n - 1) if n > 1 else lw / 2)
        y = haut + lh * (1 - a["note_globale"] / 100)
        coords.append((x, y))
    out = []
    for v in (0, 25, 50, 75, 100):
        y = haut + lh * (1 - v / 100)
        out.append(f'<line class="grille" x1="{gauche}" y1="{y:.1f}" x2="{W - droite}" y2="{y:.1f}"/>'
                   f'<text class="axe" x="{gauche - 8}" y="{y + 4:.1f}" text-anchor="end">{v}</text>')
    if n > 1:
        out.append('<polyline class="courbe" points="' + " ".join(f"{x:.1f},{y:.1f}" for x, y in coords) + '"/>')
    pas = max(1, -(-n // 8))  # au plus ~8 dates en abscisse ; la dernière est toujours affichée
    for i, (a, (x, y)) in enumerate(zip(pts, coords)):
        note = a["note_globale"]
        out.append(f'<circle class="pt rempli c-{rh._couleur_note(note)}" cx="{x:.1f}" cy="{y:.1f}" r="6">'
                   f'<title>{e(a["date"])} : {note}/100</title></circle>')
        if n <= 24:
            ly = y - 12 if y - 12 > haut - 8 else y + 22
            out.append(f'<text class="val-pt" x="{x:.1f}" y="{ly:.1f}" text-anchor="middle">{note}</text>')
        if (n - 1 - i) % pas == 0:
            out.append(f'<text class="axe" x="{x:.1f}" y="{H - bas + 22}" text-anchor="middle">{_date_courte(a["date"])}</text>')
    if n > 1:
        resume = (f"Note globale : {pts[0]['note_globale']} le {pts[0]['date']}, {pts[-1]['note_globale']} le {pts[-1]['date']}, "
                  f"{n} audits")
    else:
        resume = f"Note globale : {pts[0]['note_globale']} le {pts[0]['date']}, un seul audit"
    return (f'<div class="courbe-wrap"><svg viewBox="0 0 {W} {H}" role="img" aria-label="{e(resume)}">'
            f'<title>Évolution de la note globale indicative (0 à 100)</title>{"".join(out)}</svg></div>')


def _liens(site, a):
    liens = []
    for fichier, libelle in (("RAPPORT.html", "Page web"), ("RAPPORT.pdf", "PDF")):
        if (a["chemin"] / fichier).is_file():
            liens.append(f'<a href="{e(a["date"])}/{fichier}">{libelle}</a>')
    return " ".join(liens) if liens else '<span class="zero">—</span>'


def _cellule_note(v):
    if v is None:
        return '<td class="num zero">—</td>'
    n = v["note"]
    return f'<td class="num">{rh.pastille(n, rh._couleur_note(n))}</td>'


def tableau(site, liste, ecarts):
    domaines = sorted({d for a in liste for d in a["notes"]}, key=lambda d: (list(rh.POIDS).index(d) if d in rh.POIDS else 99, d))
    tete = ['<th scope="col">Date</th>', '<th scope="col" class="num">Note globale</th>', '<th scope="col">Évolution</th>']
    tete += [f'<th scope="col" class="num">{e(d)}</th>' for d in domaines]
    tete += ['<th scope="col" class="num">Perf. mobile</th>', '<th scope="col">Rapports</th>']
    lignes = []
    for i in range(len(liste) - 1, -1, -1):  # le plus récent d'abord
        a, n = liste[i], liste[i]["note_globale"]
        if n is None:
            glob = '<td class="num zero">—</td>'
        else:
            plaf = ' <span class="plafond">(plafonnée)</span>' if a["plafonnee"] else ""
            glob = f'<td class="num">{rh.pastille(n, rh._couleur_note(n))} {rh.lettre(n)}{plaf}</td>'
        perf = a["perf_mobile"]
        perf_td = '<td class="num zero">—</td>' if perf is None else f'<td class="num">{rh.pastille(perf, rh._couleur_score(perf))}</td>'
        premier = _premier_avec_note(liste, i)
        cellules = "".join(_cellule_note(a["notes"].get(d)) for d in domaines)
        lignes.append(f'<tr><th scope="row" class="date"><time datetime="{e(a["date"])}">{e(_date_longue(a["date"]))}</time></th>{glob}'
                      f'<td>{delta_html(ecarts[i], premier and n is not None)}</td>{cellules}{perf_td}<td class="liens">{_liens(site, a)}</td></tr>')
    return (f'<div class="table-wrap"><table class="histo"><caption class="sr">Historique des audits, du plus récent au plus ancien</caption>'
            f'<thead><tr>{"".join(tete)}</tr></thead><tbody>{"".join(lignes)}</tbody></table></div>')


def generer(dossier_site):
    site = Path(dossier_site)
    hote = site.resolve().name
    liste = audits(site)
    titre = f"Historique des audits — {hote}"
    if not liste:
        corps = ('<div class="encadre"><p><strong>Aucun audit pour le moment.</strong> Les audits apparaissent ici dès qu\'un dossier '
                 '<code>AAAA-MM-JJ</code> contenant <code>data/</code> existe dans ce dossier.</p></div>')
        sous = "Aucun audit"
    else:
        ecarts = _ecarts(liste)
        dernier = liste[-1]
        n = dernier["note_globale"]
        if n is None:
            hero = '<div class="carte"><p>Dernier audit sans note globale calculable.</p></div>'
        else:
            lt = rh.lettre(n)
            premier_audit = sum(1 for a in liste if a["note_globale"] is not None) == 1
            vs_prec = " par rapport à l'audit précédent" if ecarts[-1] is not None else ""
            hero = (f'<div class="carte hero-histo c-{rh._couleur_note(n)}"><div><p class="grand"><span class="lettre">{lt}</span>{n}/100</p></div>'
                    f'<div><p>Dernier audit : <strong>{e(_date_longue(dernier["date"]))}</strong> · {delta_html(ecarts[-1], premier_audit)}'
                    f'{vs_prec}</p>'
                    f'<p class="legende">Note globale indicative (signaux automatiques) ; {e(rh.LECTURE[lt])}.</p></div></div>')
        corps = (f'<section class="majeure" id="evolution"><h2>Évolution de la note globale</h2>{hero}{courbe_svg(liste)}</section>'
                 f'<section class="majeure" id="audits"><h2>Audits</h2>{tableau(site, liste, ecarts)}'
                 f'<p class="legende">Notes indicatives calculées sur les signaux automatiques de chaque audit (barème : 100 − 20 × critiques − 10 × hautes − 4 × moyennes − 1 × basse). '
                 f'Le score de performance mobile est la médiane des pages mesurées par Lighthouse. Les notes du rapport priorisé, quand il existe, font foi dans chaque RAPPORT.html.</p></section>')
        premiere, derniere = liste[0]["date"], liste[-1]["date"]
        sous = (f"{len(liste)} audit{'s' if len(liste) > 1 else ''}" +
                (f", du {_date_longue(premiere)} au {_date_longue(derniere)}" if len(liste) > 1 else f", le {_date_longue(derniere)}"))
    if not liste:
        corps = f'<section class="majeure">{corps}</section>'
    return (f'<!doctype html>\n<html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<meta name="color-scheme" content="light dark">{MARQUEUR}<title>{e(titre)}</title><style>{rh.CSS}{CSS_HISTORIQUE}</style></head><body>'
            f'<header class="bandeau"><div class="in"><p class="etiq">Suivi des audits</p><h1>{e(titre)}</h1><p>{e(sous)}</p>'
            f'<p>Page régénérée à chaque audit (audit-site-astro {e(rh.version_plugin())})</p></div></header>'
            f'<div class="page"><main>{corps}</main>'
            f'<footer>Un dossier AAAA-MM-JJ par audit ; liens relatifs, la page fonctionne hors ligne depuis ce dossier.</footer></div></body></html>\n')


def est_page_historique(chemin):
    """True si le fichier est une page produite par historique.py (marqueur, ou en-tête des versions sans marqueur)."""
    try:
        debut = Path(chemin).read_text(encoding="utf-8", errors="replace")[:20000]
    except OSError:
        return False
    return MARQUEUR in debut or ('<p class="etiq">Suivi des audits</p>' in debut and "(audit-site-astro " in debut)


def a_des_audits_dates(dossier_site):
    try:
        return any(p.is_dir() and _DATE.match(p.name) for p in Path(dossier_site).iterdir())
    except OSError:
        return False


class Refus(Exception):
    """Écriture refusée : la cible n'est pas une page historique, ou le dossier n'est pas un dossier de site."""


def ecrire(dossier_site, cible=None):
    cible = Path(cible) if cible else Path(dossier_site) / "index.html"
    if cible.exists() and not est_page_historique(cible):
        raise Refus(f"{cible} existe et n'est pas une page historique d'audit-site-astro : il n'est pas remplacé. "
                    "Passer le dossier du SITE (celui qui contient les dossiers d'audit AAAA-MM-JJ), ou --sortie vers un autre fichier.")
    if not cible.exists() and not a_des_audits_dates(dossier_site):
        raise Refus(f"{dossier_site} ne contient aucun dossier d'audit AAAA-MM-JJ : ce n'est pas un dossier de site, rien n'est écrit.")
    tmp = cible.with_name(cible.name + ".tmp")
    tmp.write_text(generer(dossier_site), encoding="utf-8")
    os.replace(tmp, cible)
    return cible


def main():
    ap = argparse.ArgumentParser(description="Génère index.html : historique des audits d'un site")
    ap.add_argument("site", help="DOSSIER_SITE (ex. ~/audits-site/beta.exemple.fr)")
    ap.add_argument("--sortie", help="fichier de sortie (défaut : DOSSIER_SITE/index.html)")
    a = ap.parse_args()
    if not Path(a.site).is_dir():
        print(f"❌ Dossier de site introuvable : {a.site}", file=sys.stderr)
        sys.exit(2)
    try:
        print(ecrire(a.site, a.sortie))
    except Refus as err:
        print(f"❌ {err}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
