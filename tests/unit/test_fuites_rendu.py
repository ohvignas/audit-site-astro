import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

ICI = pathlib.Path(__file__).resolve().parent
SCRIPTS = ICI.parents[1] / "plugins/audit-site-astro/skills/audit-complet/scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(ICI))
import fuites_rendu  # noqa: E402
import html_observateurs as ho  # noqa: E402
from site_local import HTML, SiteLocal  # noqa: E402


def crawler(routes):
    """Crawl d'un SiteLocal (aucun réseau externe) → issues.json."""
    with SiteLocal(routes) as site, tempfile.TemporaryDirectory() as d:
        subprocess.run([sys.executable, str(SCRIPTS / "crawl_site.py"), site.url, "--out", d, "--delay", "0", "--max-pages", "10",
                        "--liens-externes", "0", "--ressources", "0"], check=True, capture_output=True, timeout=120)
        return json.loads(pathlib.Path(d, "issues.json").read_text(encoding="utf-8")), site.base


def jetons(html):
    r = ho.analyser(html, {}, "https://ex.fr/", modules=[("fuites_rendu", fuites_rendu)])["fuites_rendu"]
    return sorted(j for e in r["fuites"] for j in [e["jeton"]] * e["n"])


class TestFuites(unittest.TestCase):
    def test_fuites_et_cas_legitimes(self):
        html = ('<p>Prix : undefined €</p><span>NaN</span><p>[object Object]</p><p>Bonjour {{ prenom }}</p>'
                '<img src="/images/undefined.jpg" alt="undefined"><a href="/formations/null">Formation</a>'
                "<p>En JavaScript, <code>undefined</code> signifie qu'une variable n'a pas reçu de valeur.</p>"
                "<p>La valeur null indique l'absence de donnée dans la base, ce qui est différent d'une chaîne vide.</p>"
                "<script>var a = undefined;</script><p hidden>undefined</p>")
        self.assertEqual(jetons(html), ["NaN", "[object Object]", "null", "undefined", "undefined", "undefined", "{{ prenom }}"])

    def test_crawl(self):
        page = ('<html lang="fr"><head><title>Fiche de formation de test</title></head><body><main>'
                '<p>Durée : NaN heures</p></main></body></html>')
        issues, _ = crawler({"/": (200, HTML, page)})
        self.assertEqual((issues["fuite_rendu"]["severity"], issues["fuite_rendu"]["domaine"]), ("haute", "Contenu"))
        self.assertEqual(issues["fuite_rendu"]["examples"][0]["signature"], "NaN — « Durée : NaN heures »")


class TestFuitesVisibles(unittest.TestCase):
    """Jeton collé à une valeur, étiquette de prix, ou seul dans son élément : fuite."""

    def test_jeton_pres_d_une_valeur(self):
        for html, attendu in (
                ("<p>Prix : undefined €</p>", ["undefined"]),
                ("<p>Durée : NaN min</p>", ["NaN"]),
                ("<p>Tarif : null</p>", ["null"]),
                ("<p>Places restantes : undefined</p>", ["undefined"]),
                ("<p>Total NaN €</p>", ["NaN"]),
                ("<p>12 undefined</p>", ["undefined"]),
                ("<p>À partir de 49 € / NaN</p>", ["NaN"]),
                ("<p>undefined%</p>", ["undefined"]),
                ("<li>null</li>", ["null"]),
                ("<td>  undefined  </td>", ["undefined"]),
                ("<p>NaN.</p>", ["NaN"]),
        ):
            with self.subTest(html=html):
                self.assertEqual(jetons(html), attendu)

    def test_jeton_remplit_un_element_dans_une_phrase_courte(self):
        self.assertEqual(jetons("<p>Prix : <span>undefined</span> €</p>"), ["undefined"])
        self.assertEqual(jetons("<p>Prix : <strong>NaN</strong></p>"), ["NaN"])
        self.assertEqual(jetons('<ul><li><a href="/x">undefined</a></li></ul>'), ["undefined"])
        self.assertEqual(jetons("<button>undefined</button>"), ["undefined"])

    def test_elements_voisins_sans_espace(self):
        self.assertEqual(jetons("<select><option>undefined</option><option>Paris</option></select>"), ["undefined"])
        self.assertEqual(jetons("<p><button>Valider</button><button>NaN</button></p>"), ["NaN"])
        self.assertEqual(jetons("<div><span>Prix</span> <span>undefined</span></div>"), ["undefined"])

    def test_lien_dont_le_texte_est_un_jeton_meme_dans_une_phrase(self):
        self.assertEqual(jetons('<p>Voir la fiche <a href="/x">undefined</a> pour plus de détails sur le sujet.</p>'), ["undefined"])

    def test_jeton_dans_un_long_paragraphe_extrait_borne(self):
        r = ho.analyser("<p>" + "mot " * 30 + "Prix : NaN € fin " + "mot " * 30 + "</p>", {}, "https://ex.fr/",
                        modules=[("fuites_rendu", fuites_rendu)])["fuites_rendu"]
        self.assertEqual(len(r["fuites"]), 1)
        self.assertLessEqual(len(r["fuites"][0]["signature"]), 90)
        self.assertIn("Prix : NaN €", r["fuites"][0]["signature"])

    def test_texte_coupe_par_un_commentaire(self):
        self.assertEqual(jetons("<p>Prix : <!-- c -->undefined<!-- d --> €</p>"), ["undefined"])

    def test_attributs_visibles(self):
        self.assertEqual(jetons('<img src="/a.png" alt="undefined">'), ["undefined"])
        self.assertEqual(jetons('<a href="/a" title="null">Lien</a>'), ["null"])
        self.assertEqual(jetons('<button aria-label="NaN">x</button>'), ["NaN"])
        self.assertEqual(jetons('<input type="text" value="undefined">'), ["undefined"])
        self.assertEqual(jetons('<input value="[object Object]">'), ["[object Object]"])
        self.assertEqual(jetons('<img src="/a.png" alt="Prix : undefined €">'), ["undefined"])

    def test_attributs_non_visibles_ignores(self):
        self.assertEqual(jetons('<input type="hidden" name="a" value="undefined">'), [])
        self.assertEqual(jetons('<input type="password" value="null">'), [])
        self.assertEqual(jetons('<input type="checkbox" value="undefined">'), [])
        self.assertEqual(jetons('<input type="text" value="undefined" hidden>'), [])
        self.assertEqual(jetons('<img src="/a.png" alt="" data-x="undefined" class="null">'), [])
        self.assertEqual(jetons('<img src="/a.png" alt="La valeur null en JavaScript">'), [])
        self.assertEqual(jetons('<code title="undefined">x</code>'), [])

    def test_segment_d_url(self):
        self.assertEqual(jetons('<a href="/formations/undefined">F</a>'), ["undefined"])
        self.assertEqual(jetons('<a href="/formations/NaN/">F</a>'), ["NaN"])
        self.assertEqual(jetons('<a href="/formations?id=undefined">F</a>'), ["undefined"])
        self.assertEqual(jetons('<a href="/formations/nullable">F</a>'), [])
        self.assertEqual(jetons('<a href="/blog/null-et-undefined-en-js">F</a>'), [])
        self.assertEqual(jetons('<a href="mailto:null@ex.fr">F</a><a href="data:text/plain,undefined">G</a>'), [])

    def test_objet_et_gabarit_partout(self):
        self.assertEqual(jetons("<p>Bonjour, voici la fiche de [object Object] pour toute la session de formation.</p>"),
                         ["[object Object]"])
        self.assertEqual(jetons("<p>Bonjour ${prenom}, bienvenue.</p>"), ["${prenom}"])
        self.assertEqual(jetons("<p><b>[object Object]</b></p>"), ["[object Object]"])


class TestFauxPositifs(unittest.TestCase):
    """Aucun de ces cas ne doit être signalé."""

    def test_elements_de_code(self):
        for html in ("<code>undefined</code>", "<pre>Prix : undefined €</pre>", "<kbd>null</kbd>", "<samp>NaN</samp>",
                     "<var>null</var>", "<pre><code>const a = undefined;</code></pre>", "<p>Valeur : <code>NaN</code></p>",
                     "<pre><span>undefined</span></pre>", "<code><span>NaN min</span></code>"):
            with self.subTest(html=html):
                self.assertEqual(jetons(html), [])

    def test_script_style_jsonld_et_masques(self):
        for html in ("<script>var a = undefined; var b = NaN;</script>",
                     '<script type="application/ld+json">{"price": null, "name": "undefined"}</script>',
                     "<style>.undefined::after{content:'null'}</style>",
                     "<p hidden>undefined</p>", '<div aria-hidden="true">Prix : NaN €</div>',
                     '<div style="display:none">null</div>', "<template><p>undefined</p></template>",
                     "<noscript>undefined</noscript>", "<textarea>undefined</textarea>",
                     "<html><head><title>undefined</title></head><body></body></html>"):
            with self.subTest(html=html):
                self.assertEqual(jetons(html), [])

    def test_prose_sur_la_programmation(self):
        for html in ("<p>La valeur null en JavaScript</p>",
                     "<p>NaN means Not-a-Number</p>",
                     "<p>undefined est le type d'une variable non initialisée</p>",
                     "<p>En JavaScript, undefined signifie qu'une variable n'a pas reçu de valeur.</p>",
                     "<p>La valeur null indique l'absence de donnée.</p>",
                     "<p>Valeur null possible</p>",
                     "<p>The value is null.</p>",
                     "<p>Le type Number inclut NaN (Not-a-Number) pour les calculs invalides.</p>",
                     "<p>Pour tester NaN, utilisez Number.isNaN et non une comparaison directe.</p>",
                     "<p>Une variable déclarée sans valeur contient undefined jusqu'à son affectation.</p>",
                     "<h2>Comprendre undefined et null</h2>",
                     "<p>La valeur <em>null</em> indique l'absence de donnée dans la base.</p>",
                     "<p>Une propriété absente renvoie <strong>undefined</strong> et non une erreur.</p>",
                     "<p>Exemple : null</p>", "<p>Résultat : NaN</p>",
                     "<p>La réponse de la fonction, quand rien n'est trouvé, est : null.</p>",
                     "<p>null, undefined et NaN sont trois valeurs distinctes.</p>"):
            with self.subTest(html=html):
                self.assertEqual(jetons(html), [])

    def test_article_qui_explique_undefined(self):
        html = ("<article><h1>Comprendre undefined en JavaScript</h1>"
                "<p>Quand on lit une propriété qui n'existe pas, le moteur renvoie undefined plutôt que de lever une erreur.</p>"
                "<p>On distingue <code>undefined</code> de <code>null</code> : le second est une absence voulue.</p>"
                "<ul><li>undefined : variable non initialisée</li><li>null : absence volontaire de valeur</li></ul>"
                "<p>Enfin, <em>NaN</em> est le résultat d'un calcul numérique invalide.</p></article>")
        self.assertEqual(jetons(html), [])

    def test_mot_francais_nul_et_null_dans_une_phrase(self):
        for html in ("<p>Le résultat est nul.</p>", "<p>Une note nulle est éliminatoire.</p>", "<p>Nul n'est censé ignorer la loi.</p>",
                     "<p>Match nul entre les deux équipes ; la différence est nulle.</p>",
                     "<p>Il n'existe aucune valeur null dans cette colonne de la table.</p>",
                     "<p>nullable et undefined_behavior sont des identifiants, pas des fuites.</p>"):
            with self.subTest(html=html):
                self.assertEqual(jetons(html), [])


class TestComptage(unittest.TestCase):
    def test_signature_et_n(self):
        r = ho.analyser("<p>Prix : undefined €</p><p>Prix : undefined €</p><p>Durée : NaN h</p>", {}, "https://ex.fr/",
                        modules=[("fuites_rendu", fuites_rendu)])["fuites_rendu"]
        self.assertEqual(r["fuites"], [{"signature": "NaN — « Durée : NaN h »", "n": 1, "jeton": "NaN"},
                                       {"signature": "undefined — « Prix : undefined € »", "n": 2, "jeton": "undefined"}])

    def test_resultat_json_strict_et_page_sans_fuite(self):
        r = ho.analyser("<p>Bonjour tout le monde</p>", {}, "https://ex.fr/", modules=[("fuites_rendu", fuites_rendu)])
        self.assertEqual(r, {"fuites_rendu": {"fuites": []}})
        json.dumps(r, allow_nan=False)


if __name__ == "__main__":
    unittest.main()
