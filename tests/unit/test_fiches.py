import json
import pathlib
import re
import subprocess
import sys
import tempfile
import unittest

RACINE = pathlib.Path(__file__).resolve().parents[2]
SCRIPTS = RACINE / "plugins/audit-site-astro/skills/audit-complet/scripts"
FICHES_REELLES = RACINE / "plugins/audit-site-astro/skills/audit-complet/references/fiches"
FIXTURE_FICHES = RACINE / "tests/unit/fixtures/fiches"
FIXTURE_AUDIT = RACINE / "tests/unit/fixtures/audit-exemple"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import extraction_detecteurs as extraction  # noqa: E402
import fiches  # noqa: E402
import geo_check  # noqa: E402
import signaux  # noqa: E402


def sig(source, cle):
    return {"severite": "haute", "domaine": "x", "texte": cle, "exemples": [], "source": source, "cle": cle}


class TestParseur(unittest.TestCase):
    def test_scalaires_listes_et_commentaires(self):
        meta, corps = fiches.parse_frontmatter(
            '---\nid: a-b\ntitre: "Un \\"titre\\" : ok"   # note\neffort: S # note\nvide: []\n'
            'liste:   # note\n  # commentaire\n  - "x:1"\n  - http://ex.fr/#ancre\n  - \'y\'\n---\n\n# Corps\n')
        self.assertEqual(meta["id"], "a-b")
        self.assertEqual(meta["titre"], 'Un "titre" : ok')
        self.assertEqual(meta["effort"], "S")
        self.assertEqual(meta["vide"], [])
        self.assertEqual(meta["liste"], ["x:1", "http://ex.fr/#ancre", "y"])
        self.assertEqual(corps, "# Corps\n")

    def test_antislash_echappe(self):
        meta, _ = fiches.parse_frontmatter('---\ndeclencheurs:\n  - "http:a\\\\.b \\\\| c"\n---\n')
        self.assertEqual(meta["declencheurs"], ["http:a\\.b \\| c"])
        re.compile(fiches.declencheur(meta["declencheurs"][0])[1])

    def test_liste_en_ligne_et_apostrophes(self):
        meta, _ = fiches.parse_frontmatter("---\na: [x, \"y z\", 'l''a']\nb: 'it''s'\n---\n")
        self.assertEqual(meta["a"], ["x", "y z", "l'a"])
        self.assertEqual(meta["b"], "it's")

    def test_liste_vide_sans_element(self):
        meta, _ = fiches.parse_frontmatter("---\ndeclencheurs:\nid: x\n---\n")
        self.assertEqual(meta["declencheurs"], [])
        self.assertEqual(meta["id"], "x")

    def test_erreurs(self):
        for mauvais in ("pas de frontmatter", "---\nid: x\n", '---\nt: "non fermé\n---\n', '---\nt: "a\\.b"\n---\n',
                        "---\nid: x\nid: y\n---\n", "---\n   - orphelin\n---\n", '---\nt: "a" b\n---\n'):
            with self.assertRaises(ValueError, msg=mauvais):
                fiches.parse_frontmatter(mauvais)


class TestChargement(unittest.TestCase):
    def setUp(self):
        self.f = fiches.charger_fiches(FIXTURE_FICHES)
        self.par_id = {x["id"]: x for x in self.f}

    def test_ignore_les_fichiers_a_tiret_bas(self):
        self.assertEqual(sorted(self.par_id), ["a11y-manuel", "geo-vide", "seo-exact", "serveur-regex"])
        self.assertEqual([x["id"] for x in self.f], sorted(self.par_id))

    def test_champs_corps_et_chemin(self):
        x = self.par_id["seo-exact"]
        self.assertEqual(x["titre"], 'Titre avec "guillemets" et deux-points : ok')
        self.assertEqual(x["versions_astro"], ">=5.10")
        self.assertEqual(x["declencheurs"], ["crawl:http_4xx", "crawl:http_5xx"])
        self.assertEqual(len(x["sources"]), 2)
        self.assertTrue(x["corps"].startswith("# Titre du corps"))
        self.assertNotIn("---", x["corps"].splitlines()[0])
        self.assertEqual(x["chemin"].name, "seo-exact.md")

    def test_regex_avec_antislashs(self):
        d = self.par_id["serveur-regex"]["declencheurs"]
        self.assertIn("securite:/\\.env \\| 200", d)
        self.assertIn("code:Routes SSR dynamiques sans gestion", d)

    def test_fichier_malforme_nomme_dans_l_erreur(self):
        with tempfile.TemporaryDirectory() as t:
            pathlib.Path(t, "casse.md").write_text("pas de frontmatter", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "casse.md"):
                fiches.charger_fiches(t)


class TestValidationDuContrat(unittest.TestCase):
    """charger_fiches valide chaque fiche : ValueError nommant le fichier (et le déclencheur fautif)."""

    def _charger(self, fichiers):
        with tempfile.TemporaryDirectory() as t:
            for nom, contenu in fichiers.items():
                pathlib.Path(t, nom).write_text(contenu, encoding="utf-8")
            return fiches.charger_fiches(t)

    @staticmethod
    def _fiche(ident, *declencheurs):
        decl = "".join(f'  - "{d}"\n' for d in declencheurs)
        return f"---\nid: {ident}\ntitre: t\ndeclencheurs:\n{decl}sources: []\n---\n# corps\n"

    def test_fiche_valide(self):
        r = self._charger({"a-b.md": self._fiche("a-b", "crawl:x", "code:(a|b)", "manuel:sujet")})
        self.assertEqual([x["id"] for x in r], ["a-b"])

    def test_regex_invalide(self):
        with self.assertRaises(ValueError) as c:
            self._charger({"a-b.md": self._fiche("a-b", "crawl:ok", "code:(oups")})
        self.assertIn("a-b.md", str(c.exception))
        self.assertIn("code:(oups", str(c.exception))

    def test_prefixe_inconnu(self):
        with self.assertRaises(ValueError) as c:
            self._charger({"a-b.md": self._fiche("a-b", "inconnu:x")})
        self.assertIn("a-b.md", str(c.exception))
        self.assertIn("inconnu:x", str(c.exception))

    def test_id_manquant(self):
        with self.assertRaisesRegex(ValueError, r"a-b\.md : clé « id » absente"):
            self._charger({"a-b.md": "---\ntitre: t\ndeclencheurs: []\n---\n"})

    def test_id_different_du_nom_de_fichier(self):
        with self.assertRaisesRegex(ValueError, r"a-b\.md : id « autre »"):
            self._charger({"a-b.md": self._fiche("autre")})

    def test_id_en_double(self):
        # id = nom de fichier et noms uniques => un id en double est toujours rejeté (au plus tard comme « différent du nom de fichier »)
        with self.assertRaisesRegex(ValueError, r"c-d\.md : id « a-b »"):
            self._charger({"a-b.md": self._fiche("a-b"), "c-d.md": self._fiche("a-b")})

    def test_associer_ne_leve_jamais_sur_une_base_chargee(self):
        r = self._charger({"a-b.md": self._fiche("a-b", "code:(a|b)", "crawl:x", "manuel:m"), "c-d.md": self._fiche("c-d")})
        retenues, sans = fiches.associer([sig("code", "a"), sig("crawl", "y"), {"source": "geo", "cle": None}], r)
        self.assertEqual(list(retenues), ["a-b"])
        self.assertEqual(len(sans), 2)

    def test_bom_utf8_toleree_et_cle_scalaire_vide(self):
        r = self._charger({"a-b.md": "\ufeff---\nid: a-b\ntitre:\ndeclencheurs: []\n---\n"})
        self.assertEqual(r[0]["titre"], "")


class TestAssociation(unittest.TestCase):
    def setUp(self):
        self.f = fiches.charger_fiches(FIXTURE_FICHES)

    def test_crawl_egalite_exacte(self):
        r, sans = fiches.associer([sig("crawl", "http_4xx"), sig("crawl", "http_4xx_bis"), sig("crawl", "xhttp_4xx")], self.f)
        self.assertEqual([s["cle"] for s in r["seo-exact"]], ["http_4xx"])
        self.assertEqual([s["cle"] for s in sans], ["http_4xx_bis", "xhttp_4xx"])

    def test_regex_insensible_a_la_casse_sur_la_bonne_source(self):
        s_http = sig("http", "| Compression HTML | aucune (HTML décompressé : 42 Ko) | ❌ activer |")
        s_sec = sig("securite", "| /.env | 200 | ❌ |")
        s_geo = sig("geo", "robots.txt bloque PERPLEXITYBOT")
        s_code = sig("code", "Routes SSR dynamiques sans gestion du cache")
        s_lh = sig("lighthouse", "uses-text-compression Activer la compression du texte")
        s_projet = sig("projet", "| Dépendances obsolètes | ⚠️ |")
        r, sans = fiches.associer([s_http, s_sec, s_geo, s_code, s_lh, s_projet], self.f)
        self.assertEqual(sans, [])
        self.assertEqual(len(r["serveur-regex"]), 6)

    def test_source_differente_ne_correspond_pas(self):
        # même texte que le motif http:, mais signal de source « code »
        r, sans = fiches.associer([sig("code", "| Compression HTML | aucune | ❌ |")], self.f)
        self.assertEqual(r, {})
        self.assertEqual(len(sans), 1)

    def test_signal_multi_fiches(self):
        # http_4xx retient seo-exact (exact) ET serveur-regex (autre déclencheur crawl:http_4xx)
        r, sans = fiches.associer([sig("crawl", "http_4xx")], self.f)
        self.assertEqual(sorted(r), ["seo-exact", "serveur-regex"])
        self.assertEqual(sans, [])

    def test_ordre_deterministe(self):
        signaux_ = [sig("crawl", "http_5xx"), sig("crawl", "http_4xx"), sig("lighthouse", "focus-visible")]
        r1, _ = fiches.associer(signaux_, self.f)
        r2, _ = fiches.associer(signaux_, list(reversed(self.f)))
        self.assertEqual(list(r1), list(r2))
        self.assertEqual(list(r1), sorted(r1))
        self.assertEqual([s["cle"] for s in r1["seo-exact"]], ["http_5xx", "http_4xx"])

    def test_fiche_sans_declencheur_jamais_retenue(self):
        r, _ = fiches.associer([sig("geo", "vide"), sig("crawl", "geo-vide"), sig("code", "")], self.f)
        self.assertNotIn("geo-vide", r)
        self.assertEqual([x["id"] for x in fiches.fiches_sans_detection(self.f)], ["geo-vide"])

    def test_manuel_jamais_associe_automatiquement(self):
        r, sans = fiches.associer([sig("crawl", "focus-visible"), sig("code", "focus-visible"), sig("geo", "focus-visible")], self.f)
        self.assertEqual(r, {})
        self.assertEqual(len(sans), 3)
        self.assertEqual([x["id"] for x in fiches.fiches_manuelles(self.f)], ["a11y-manuel"])
        # ses autres déclencheurs (lighthouse:focus) restent actifs
        r, _ = fiches.associer([sig("lighthouse", "focus-traps")], self.f)
        self.assertEqual(list(r), ["a11y-manuel"])

    def test_signal_sans_fiche(self):
        r, sans = fiches.associer([sig("crawl", "inconnu"), sig("projet", "rien")], self.f)
        self.assertEqual(r, {})
        self.assertEqual([s["cle"] for s in sans], ["inconnu", "rien"])

    def test_declencheur_invalide(self):
        for mauvais in ("inconnu:x", "crawl:", "crawl", ":x"):
            with self.assertRaises(ValueError, msg=mauvais):
                fiches.declencheur(mauvais)


def _titres(corps):
    """Titres « ## » du corps, hors blocs de code."""
    en_code, out = False, []
    for ligne in corps.splitlines():
        if ligne.lstrip().startswith(("```", "~~~")):
            en_code = not en_code
        elif not en_code and ligne.startswith("## "):
            out.append(ligne[3:].strip())
    return out


class TestBaseReelle(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.f = fiches.charger_fiches(FICHES_REELLES)

    def test_toutes_les_fiches_se_chargent(self):
        self.assertEqual(len(self.f), len(list(FICHES_REELLES.glob("[!_]*.md"))))
        self.assertGreaterEqual(len(self.f), 142)
        self.assertEqual(len({x["id"] for x in self.f}), len(self.f), "ids en double")

    def test_metadonnees(self):
        for x in self.f:
            with self.subTest(fiche=x["chemin"].name):
                self.assertEqual(x["id"], x["chemin"].stem, "id différent du nom de fichier")
                self.assertRegex(x["id"], r"^[a-z0-9]+(-[a-z0-9]+)+$")
                self.assertIn(x["id"].split("-")[0], fiches.PREFIXES_ID)
                self.assertTrue(x.get("titre"))
                self.assertIn(x.get("domaine"), fiches.DOMAINES)
                self.assertIn(x.get("severite_type"), fiches.SEVERITES)
                self.assertIn(x.get("effort"), fiches.EFFORTS)
                self.assertIsInstance(x["sources"], list)
                self.assertTrue(all(isinstance(s, str) and s.startswith("http") for s in x["sources"]), x["sources"])

    def test_declencheurs_valides(self):
        for x in self.f:
            with self.subTest(fiche=x["id"]):
                for d in x["declencheurs"]:
                    self.assertIsInstance(d, str)
                    prefixe, motif = fiches.declencheur(d)  # préfixe connu, motif non vide
                    if prefixe not in ("crawl", fiches.PREFIXE_MANUEL):
                        re.compile(motif, re.I)

    def test_sections_du_modele_dans_l_ordre(self):
        for x in self.f:
            with self.subTest(fiche=x["id"]):
                titres = _titres(x["corps"])
                pos = []
                for s in fiches.SECTIONS:
                    self.assertIn(s, titres, f"section manquante : ## {s}")
                    pos.append(titres.index(s))
                self.assertEqual(pos, sorted(pos), f"sections dans le désordre : {titres}")

    def test_manuelles_et_sans_detection(self):
        # fiches volontairement sans détection automatique (conseils, pas de signal mesurable) : liste attendue à tenir à jour
        attendues = {"geo-bing-webmaster-indexnow", "geo-mesure-visibilite-ia"}
        self.assertEqual({x["id"] for x in fiches.fiches_sans_detection(self.f)}, attendues)
        self.assertTrue(fiches.fiches_manuelles(self.f))
        for x in fiches.fiches_manuelles(self.f):
            self.assertTrue(any(d.startswith("manuel:") for d in x["declencheurs"]))




def _lire(nom):
    return (SCRIPTS / nom).read_text(encoding="utf-8")


class TestCouverture(unittest.TestCase):
    """Chaque détecteur de l'outil doit être couvert par au moins une fiche.

    Les échantillons extraits du source des détecteurs doivent être reconnus par au moins un déclencheur de leur source.
    LACUNES_CONNUES liste, par famille, les échantillons qu'aucune fiche ne reconnaît aujourd'hui (vrais trous, à trancher par
    le contrôleur : nouvelle fiche ou déclencheur élargi). Le test les affiche ; il échoue pour tout NOUVEAU trou, et aussi si
    une lacune connue est désormais couverte (la retirer de la liste)."""

    # famille -> échantillons (chaînes exactes) sans fiche. Vide = aucun trou constaté.
    LACUNES_CONNUES = {
        "geo": [],
        "http": [],
        # La sonde marque « ❌ EXPOSÉ (info) » un /.well-known/security.txt qui répond 200 avec « Contact: » : c'est le fichier
        # souhaité (fiche secu-security-txt), pas une exposition. Faux positif de la sonde (à corriger dans security_probe.sh,
        # ou à absorber par un déclencheur) : sans fiche aujourd'hui, le signal « haute » serait orphelin.
        "securite": ["| /.well-known/security.txt | 200 | 1234 | ❌ EXPOSÉ (info) |"],
        "astro_scan": [],
    }
    # Messages d'astro_scan.py qui signalent un problème d'entrée (projet introuvable), pas un défaut du site : pas de fiche voulue.
    ASTRO_SANS_FICHE_VOULU = [
        "package.json introuvable — est-ce bien la racine du projet Astro ?",
        "astro.config.* introuvable",
        "Dossier src/ introuvable",
    ]
    # Signaux de la fixture audit-exemple qui ne ressemblent à aucune sortie réelle de l'outil (clés d'issue de crawl inventées,
    # constats/titres Lighthouse reformulés, ligne de sonde au format simplifié) : aucune fiche ne peut les reconnaître.
    # Artefacts de la fixture, pas des trous de détecteurs ; les détecteurs réels sont couverts par les tests ci-dessous.
    FIXTURE_SYNTHETIQUES = [
        "code: Image d'en-tête non optimisée (<img> au lieu de <Image>)",
        "code: Balise canonical absente du layout",
        "crawl: liens_casses",
        "crawl: title_manquant",
        "crawl: h1_multiples",
        "securite: | /.git/config | ❌ EXPOSÉ (critique) |",
        "lighthouse: Les liens n'ont pas de nom discernable",
        "lighthouse: Le contraste des couleurs est insuffisant",
        "geo: llms.txt absent : les assistants IA n'ont pas de résumé du site",
        "geo: Aucune donnée structurée Organization sur la page d'accueil",
    ]

    @classmethod
    def setUpClass(cls):
        cls.f = fiches.charger_fiches(FICHES_REELLES)

    def _trous(self, sigs):
        _, sans = fiches.associer(sigs, self.f)
        return [f"{s['source']}: {s['cle'][:160]}" for s in sans]

    def _verifier(self, famille, source, echantillons):
        """Échantillons (chaînes) d'une source -> aucun trou hors LACUNES_CONNUES, et aucune lacune connue périmée."""
        self.assertTrue(echantillons, f"aucun échantillon extrait pour {famille}")
        _, sans = fiches.associer([sig(source, e) for e in echantillons], self.f)
        trous = sorted({s["cle"] for s in sans})
        connues = self.LACUNES_CONNUES[famille]
        if connues:
            sys.stderr.write(f"\n[LACUNES_CONNUES {famille}] {len(connues)} échantillon(s) sans fiche :\n"
                             + "".join(f"  - {c}\n" for c in connues))
        nouveaux = [c for c in trous if c not in connues]
        perimees = [c for c in connues if c not in trous]
        self.assertEqual(nouveaux, [], f"{famille} : échantillons sans fiche (nouveaux trous) : {nouveaux}")
        self.assertEqual(perimees, [], f"{famille} : lacunes connues désormais couvertes, à retirer de LACUNES_CONNUES : {perimees}")

    # (a) crawl ------------------------------------------------------------------------------------------------------------

    def test_cles_du_crawl(self):
        cles = extraction.cles_crawl(_lire("crawl_site.py"))
        self.assertGreaterEqual(len(cles), 55, f"extraction des clés du crawl dégradée : {sorted(cles)}")
        trous = self._trous([sig("crawl", k) for k in sorted(cles)])
        self.assertEqual(trous, [], f"clés d'issue du crawl sans fiche : {trous}")

    # (b) astro_scan -------------------------------------------------------------------------------------------------------

    def _constats_du_scan(self, variante):
        with tempfile.TemporaryDirectory() as t:
            subprocess.run([sys.executable, str(SCRIPTS / "astro_scan.py"), str(RACINE / "tests/cobaye" / variante), "--out", t],
                           check=True, capture_output=True, timeout=180)
            rapport = json.loads(pathlib.Path(t, "code-scan.json").read_text(encoding="utf-8"))
        return [c["constat"] for c in rapport["constats"]]

    def test_constats_du_scan_sur_le_cobaye(self):
        constats = self._constats_du_scan("casse") + self._constats_du_scan("propre")
        self.assertGreater(len(constats), 20)
        trous = sorted(set(self._trous([sig("code", c) for c in constats])))
        self.assertEqual(trous, [], f"constats astro_scan.py (cobaye casse/propre) sans fiche : {trous}")

    def test_messages_du_source_d_astro_scan(self):
        appels = extraction.appels(_lire("astro_scan.py"), "add", 2)
        self.assertGreaterEqual(len(appels), 60, "extraction des add(...) d'astro_scan.py dégradée")
        echantillons = sorted({m for msgs in appels for m in msgs} - set(self.ASTRO_SANS_FICHE_VOULU))
        self._verifier("astro_scan", "code", echantillons)

    # (c) fixture ----------------------------------------------------------------------------------------------------------

    def test_signaux_de_la_fixture(self):
        trous = [t for t in self._trous(signaux.collecter(FIXTURE_AUDIT)) if t not in self.FIXTURE_SYNTHETIQUES]
        self.assertEqual(trous, [], f"signaux de la fixture audit-exemple sans fiche : {trous}")

    # (d) geo_check.py -----------------------------------------------------------------------------------------------------

    def test_messages_de_geo_check(self):
        base = {
            "row['signal']": ["HTTP 403", "cf-mitigated: challenge", "page de challenge / blocage WAF", "contenu réduit (120 vs 5000 octets)"],
            "p['url']": ["https://exemple.fr/page"], "', '.join(p['limites_extraits'])": ["nosnippet, max-snippet:0"],
            "names[:6]": ["['Illith', 'ILLITH SAS']"], "len(micro)": ["2"], "p['champs_manquants']": ["['author', 'dateModified']"],
            "q": ["1"], "len(ok_pages)": ["5"], "k.replace('_', ' ')": ["a propos", "contact", "mentions legales", "confidentialite"],
        }
        echantillons = set()
        for token, _ua, role, _fam in geo_check.AI_BOTS:  # un environnement par robot : le motif dépend du jeton
            env = dict(base, **{"row['bot']": [token], "row['role']": [role]})
            for msgs in extraction.appels(_lire("geo_check.py"), "sig", 1, env):
                echantillons.update(msgs)
        # combinaisons impossibles produites par la conditionnelle « obligatoire en France » (réservée à mentions_legales)
        echantillons = sorted(e for e in echantillons if ("obligatoire" in e) == ("mentions legales" in e) or "introuvable" not in e)
        self.assertGreater(len(echantillons), 40)
        self._verifier("geo", "geo", echantillons)

    # (d) http_checks.sh et security_probe.sh --------------------------------------------------------------------------------

    def _via_collecte(self, sous_dossier, fichier, lignes):
        """Passe les lignes par signaux.collecter (comme un vrai audit). Retourne (cles des signaux, lignes non signalées)."""
        with tempfile.TemporaryDirectory() as t:
            d = pathlib.Path(t, "data", sous_dossier)
            d.mkdir(parents=True)
            (d / fichier).write_text("\n".join(lignes) + "\n", encoding="utf-8")
            cles = [s["cle"] for s in signaux.collecter(t)]
        return cles, sorted(l for l in lignes if l.strip() not in cles)

    def _declencheurs_sans_echantillon(self, source, lignes):
        """Déclencheurs `source:` qu'aucune des lignes produites (signalées ou non) ne reconnaît : information, pas une assertion.
        Ce sont surtout des lignes de tableau sans ❌/⚠️ (ex. /robots.txt en 404, `TLS 1.2 : non accepté`, `Expiration dans`) que
        `signaux.collecter` ne transforme volontairement pas en signaux."""
        sigs = [sig(source, l.strip()) for l in lignes]
        return sorted(f"{f['id']}: {d}" for f in self.f for d in f["declencheurs"]
                      if d.startswith(source + ":") and not any(fiches.correspond(d, s) for s in sigs))

    def test_lignes_de_http_checks(self):
        src = extraction.echantillons_shell(_lire("http_checks.sh"), exclure_valeurs={
            # ❌ absent est écrasé par « ℹ️ optionnel » pour cet en-tête : pas de signal
            "h": ("cross-origin-opener-policy",)})
        self.assertGreater(len(src), 20)
        signales, non_signales = self._via_collecte("http", "http-checks.md", src)
        # tous les avertissements produits, y compris les puces / citations / lignes en gras, deviennent des signaux, sauf l'avis
        # du mode test TLS (« mode test AUDIT_INSECURE_TLS=1 »), qui n'est pas un constat sur le site
        self.assertEqual([l for l in non_signales if "AUDIT_INSECURE_TLS" not in l], [],
                         "lignes ❌/⚠️ de http_checks.sh ignorées par signaux.collecter")
        for morceau in ("TLS 1.0 : ⚠️ encore accepté", "TLS 1.1 : ⚠️ encore accepté",
                        "⚠️ Aucune image avec fetchpriority", "une seule devrait"):
            self.assertTrue(any(morceau in c for c in signales), f"pas de signal pour « {morceau} »")
        self._verifier("http", "http", signales)
        sans = self._declencheurs_sans_echantillon("http", src)
        sys.stderr.write(f"\n[http] {len(sans)} déclencheur(s) http: sans ligne ❌/⚠️ produite par http_checks.sh (informatif) :\n"
                         + "".join(f"  - {s}\n" for s in sans))

    def test_lignes_de_security_probe(self):
        src = _lire("security_probe.sh")
        checks = extraction.lignes_check(src)
        self.assertGreaterEqual(len(checks), 30, "extraction des check(...) de security_probe.sh dégradée")
        modeles = extraction.echantillons_shell(src, codes=("200",))
        autres = [m for m in modeles if "@PATH@" not in m]
        mod_expose = next(m for m in modeles if "@PATH@" in m and "❌" in m)
        mod_repond = next(m for m in modeles if "@PATH@" in m and "⚠️" in m)
        lignes = list(autres)
        for chemin, motif, gravite in checks:
            # motif attendu vide : le verdict ne peut être que « ⚠️ répond 200 » ; sinon la ligne critique est « ❌ EXPOSÉ »
            lignes.append((mod_expose if motif else mod_repond).replace("@PATH@", chemin).replace("@SEV@", gravite))
        signales, non_signales = self._via_collecte("securite", "security-probe.md", lignes)
        self.assertEqual(non_signales, [], "lignes ❌/⚠️ de security_probe.sh ignorées par signaux.collecter")
        for morceau in ("→ .map HTTP", "⚠️ CORS sur la page HTML"):
            self.assertTrue(any(morceau in c for c in signales), f"pas de signal pour « {morceau} »")
        self._verifier("securite", "securite", signales)
        sans = self._declencheurs_sans_echantillon("securite", lignes)
        sys.stderr.write(f"\n[securite] {len(sans)} déclencheur(s) securite: sans ligne ❌/⚠️ produite par security_probe.sh (informatif) :\n"
                         + "".join(f"  - {s}\n" for s in sans))


if __name__ == "__main__":
    unittest.main()
