#!/usr/bin/env python3
"""contenu_demo.py — Contenu de démonstration resté en ligne : lorem ipsum, « à remplacer par… », restes des gabarits Astro
(blog, basics, Starlight), coordonnées fictives. Lu dans le title, les descriptions (meta, og:, twitter:), le texte visible
(hors code/pre) et les liens mailto:/tel:. Module du diffuseur html_observateurs (T3).

Faux positifs écartés : texte de <code>, <pre>, <kbd>, <samp>, <q>, <cite>, scripts et éléments masqués ; expression citée
(« … », “ … ”, „ … “, ‘ … ’, ' … ' ou " … " dans le bloc courant : un guillemet d'un autre bloc ne compte pas) ; motifs en
expressions entières et assez longues pour qu'un article ou une page sur le « lorem ipsum » (le terme seul) ne soit pas signalé ;
valeurs par défaut d'un gabarit lues sur la valeur ENTIÈRE du title ou de la description, jamais en sous-chaîne ; « Your name »
seul (étiquette de formulaire) ignoré, seul « © … Your name » compte ; « example.com » en texte volontairement absent (légitime
dans un article technique), seul un lien mailto: vers cette adresse est signalé. Le texte est découpé en blocs (\\n) aux balises de
bloc : un motif ne peut pas se former à cheval sur deux paragraphes."""
import re

import html_observateurs as ho

NOM = "contenu_demo"
MOTIFS = (
    # le terme seul (« le lorem ipsum est un faux texte ») est légitime ; le passage de gabarit et ses mots de queue ne le sont pas
    ("lorem ipsum", re.compile(r"\blorem ipsum dolor\b|\bdolor sit amet\b|\bconsectetur adipisi?cing\b|\badipisicing elit\b|\bsed do eiusmod\b"
                               r"|\bincididunt ut labore\b|\bad minim veniam\b|\bvitae ultricies leo\b", re.I)),
    ("texte à remplacer", re.compile(r"\bà remplacer par (?:(?:la|le|les) v[oô]tres?"
                                     r"|(?:votre|vos) (?:propre|texte|contenu|titre|logo|nom|slogan|description|adresse|image|photo|coordonnées|entreprise)\b"
                                     r"|(?:du|le|un) vrai (?:texte|contenu|titre|nom)\b|le contenu (?:réel|final|définitif))"
                                     r"|[\[(]\s*à remplacer\s*[\])]|\bremplacez[- ]moi\b"
                                     r"|\breplace (?:this (?:text|content|paragraph)|me\b|with your (?:own )?(?:text|content))", re.I)),
    ("page de démonstration", re.compile(r"\bpage de d[ée]monstration (?:livr[ée]e|fournie|du th[èe]me|de ce th[èe]me|par d[ée]faut|g[ée]n[ée]r[ée]e)\b"
                                         r"|\bdemo page (?:shipped|provided|included|that comes) with\b"
                                         r"|\bcontenu de d[ée]monstration\b|\b(?:texte|contenu) (?:factice|de remplissage)\b", re.I)),
    ("gabarit de démarrage", re.compile(r"\bWelcome to Astro\b|\bTo get started, open the directory\b|\bAstro Starter Kit\b"
                                        r"|\bofficial Astro blog starter template\b|\bCongrats on setting up a new Starlight project\b"
                                        r"|\bGuides lead a user through a specific task\b|^(?:\W{0,6}\s)?Hello, Astronaut!$", re.I | re.M)),
    ("coordonnées fictives", re.compile(r"\b(?:your|votre) (?:company|name|tagline|entreprise|slogan) (?:here|ici)\b|\bjohn\.doe@"
                                        r"|(?:©|\(c\))\s*(?:\d{4}\s*)?(?:your (?:name|company|brand)|votre (?:nom|entreprise|soci[ée]t[ée])"
                                        r"|company name|nom de (?:l'entreprise|la soci[ée]t[ée]))\b", re.I)),
)
BLOCS = {"p", "div", "li", "ul", "ol", "dd", "dt", "h1", "h2", "h3", "h4", "h5", "h6", "td", "th", "tr", "section", "article",
         "nav", "header", "footer", "main", "aside", "blockquote", "figcaption", "summary", "br", "hr"}  # ni pre ni code : exclus ailleurs
# Valeur ENTIÈRE d'un title / d'une description laissée par défaut par un gabarit (blog et basics d'Astro, Starlight, AstroWind)
CHAMP_EXACT = {
    "titre": re.compile(r"(?:astro (?:basics|blog)|(?:.+ \| )?my docs|coming soon|under construction|site en construction"
                        r"|bient[ôo]t disponible)\W*$", re.I),
    "description": re.compile(r"(?:welcome to my website!?|astro description|get started building your docs site with starlight\.?"
                              r"|a guide in my new starlight docs site\.?"
                              r"|\W*suitable for startups, small business, sass websites, professional portfolios, marketing websites,"
                              r" landing pages (?:&|and) blogs\.?)$", re.I),
}
FAUX_CONTACT = re.compile(r"^(?:mailto:)?[^@\s]+@(?:example\.(?:com|org|net)|domain\.(?:com|fr)|yourdomain\.\w+|votre-?domaine\.\w+|email\.com)\b"
                          r"|^tel:\W*(?:\+?1\W*)?(?:\(?555\)?\W*(?:01\d\d|\d{3}\W*\d{4})|0?123456789|\+?33\W*1\W*23\W*45\W*67\W*89"
                          r"|01\W*23\W*45\W*67\W*89)", re.I)
EXCLUS = ("code", "pre", "kbd", "samp", "q", "cite")
DESCRIPTIONS = ("description", "og:description", "og:title", "twitter:description", "twitter:title")
OUVRANTS_SIMPLES = "'‘„‚‹"


def cite(texte, debut):
    """Vrai si l'occurrence en `debut` est dans une citation ouverte avant elle, dans son bloc : « … », “ … ” ou " … " (parité des
    guillemets droits), ou juste après un guillemet ouvrant simple (' ‘ „ ‚ ‹)."""
    avant = texte[:debut]
    avant = avant[avant.rfind("\n") + 1:]  # un guillemet d'un autre bloc ne compte pas
    if avant.rstrip() and avant.rstrip()[-1] in OUVRANTS_SIMPLES:
        return True
    return (avant.rfind("«") > avant.rfind("»") or avant.rfind("“") > avant.rfind("”")
            or avant.count('"') % 2 == 1)


def premiere_occurrence(rx, texte):
    for m in rx.finditer(texte):
        if not cite(texte, m.start()):
            return m
    return None


class Observateur(ho.Observateur):
    def __init__(self, entetes, url):
        super().__init__(entetes, url)
        self.sources = {"titre": [], "description": [], "texte": []}
        self._titre = False
        self._coupure = False
        self.faux_contacts = []

    def debut(self, noeud, pile):
        t, a = noeud["tag"], noeud["a"]
        if t in BLOCS:
            self._coupure = True
        if t == "a" and not noeud["masque"] and FAUX_CONTACT.match((a.get("href") or "").strip()):
            self.faux_contacts.append(a["href"].strip())
        if t == "title" and not ho.dans(pile, "svg"):
            self._titre = True
        elif t == "meta" and not noeud["masque"] and (a.get("name") or a.get("property") or "").lower() in DESCRIPTIONS:
            self.sources["description"].append(a.get("content", ""))

    def fin(self, noeud, pile):
        if noeud["tag"] in BLOCS:
            self._coupure = True
        if noeud["tag"] == "title":
            self._titre = False

    def texte(self, donnees, pile):
        if self._titre:
            self.sources["titre"].append(donnees)
        elif ho.visible(pile) and not ho.dans(pile, *EXCLUS):
            if self._coupure:
                self.sources["texte"].append("\n")
                self._coupure = False
            self.sources["texte"].append(donnees)

    def resultat(self):
        out = []
        valeurs = {"titre": [" ".join(" ".join(self.sources["titre"]).split())],
                   "description": [" ".join(v.split()) for v in self.sources["description"]]}
        for ou in ("titre", "description"):
            for v in valeurs[ou]:
                if v and CHAMP_EXACT[ou].match(v):
                    out.append({"signature": "valeur par défaut du gabarit ({0}) : « {1} »".format(ou, v[:80]), "n": 1,
                                "motif": "gabarit de démarrage", "ou": ou})
                    break
        if self.faux_contacts:
            out.append({"signature": "coordonnées fictives (lien) : « {0} »".format(self.faux_contacts[0][:60]), "n": 1,
                        "motif": "coordonnées fictives", "ou": "texte"})
        for ou in ("titre", "description", "texte"):
            brut = " ".join(self.sources[ou]) if ou != "description" else "\n".join(self.sources[ou])
            t = "\n".join(" ".join(ligne.split()) for ligne in brut.split("\n"))
            for motif, rx in MOTIFS:
                m = premiere_occurrence(rx, t)
                if m:
                    extrait = t[max(0, m.start() - 20):m.end() + 30].replace("\n", " ")
                    out.append({"signature": "{0} ({1}) : « {2} »".format(motif, ou, extrait), "n": 1, "motif": motif, "ou": ou})
        return {"motifs": out}


def issues(pages, add, ctx):
    ho.ajouter_groupes(add, "contenu_demo", "Contenu de démonstration resté en ligne (lorem ipsum, « à remplacer », gabarit de démarrage)",
                       "moyenne", ho.collecter_groupes(pages, NOM, "motifs"), "Contenu")
