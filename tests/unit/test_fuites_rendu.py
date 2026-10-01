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
        # la page contient <code> : page technique, le jeton nu (<span>NaN</span>) n'est plus signalé (voir TestPageTechnique)
        self.assertEqual(jetons(html), ["[object Object]", "null", "undefined", "undefined", "undefined", "{{ prenom }}"])
        self.assertEqual(jetons(html.replace("<code>undefined</code>", "undefined")), ["NaN", "[object Object]", "null", "undefined", "undefined", "undefined", "{{ prenom }}"])

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
                     "<html><head><title>La valeur undefined</title></head><body></body></html>"):
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


def fuites(html, url="https://ex.fr/"):
    return ho.analyser(html, {}, url, modules=[("fuites_rendu", fuites_rendu)])["fuites_rendu"]["fuites"]


class TestPageTechnique(unittest.TestCase):
    """I1 : une page qui contient <code> ou <pre> est technique : seuls restent les jetons collés à une valeur ou à une étiquette."""

    TABLEAU = ("<table><tr><th>Valeur</th><th>Signification</th></tr><tr><td>undefined</td><td>Variable non initialisée</td></tr>"
               "<tr><td>null</td><td>Absence volontaire</td></tr></table>")

    def test_tableau_et_liste_de_jetons_sans_code_hors_page_technique_signales(self):
        self.assertEqual(jetons("<ul><li>undefined</li></ul>"), ["undefined"])

    def test_tableau_liste_titre_dans_une_page_technique(self):
        for corps in (self.TABLEAU, "<ul><li>undefined</li><li>null</li></ul>", "<h3>undefined</h3>", "<dl><dt>undefined</dt><dd>x</dd></dl>",
                      "<p>Quelle valeur ? <button>undefined</button></p>", "<p>undefined undefined</p>", "<p>NaN/NaN</p>"):
            with self.subTest(corps=corps):
                self.assertEqual(jetons("<p>Exemple : <code>let a;</code></p>" + corps), [])
                self.assertEqual(jetons("<pre>let a;</pre>" + corps), [])

    def test_valeur_collee_reste_signalee_dans_une_page_technique(self):
        page = "<pre>let a;</pre>"
        self.assertEqual(jetons(page + "<p>Prix : undefined €</p>"), ["undefined"])
        self.assertEqual(jetons(page + "<p><span>NaN</span>%</p>"), ["NaN"])
        self.assertEqual(jetons(page + "<p>Durée : NaN heures</p>"), ["NaN"])
        self.assertEqual(jetons(page + "<p>Places restantes : null</p>"), ["null"])
        self.assertEqual(jetons(page + '<img src="/a.png" alt="undefined">'), ["undefined"])
        self.assertEqual(jetons(page + '<a href="/f/undefined">x</a>'), ["undefined"])
        self.assertEqual(jetons(page + "<p>[object Object]</p>"), ["[object Object]"])
        self.assertEqual(jetons(page + "<p>Mis à jour le Invalid Date</p>"), ["Invalid Date"])

    def test_code_apres_la_fuite(self):
        self.assertEqual(jetons("<ul><li>undefined</li></ul><p>Voir <code>x</code></p>"), [])

    def test_trois_jetons_nus_distincts_sont_de_la_documentation(self):
        self.assertEqual(jetons("<ul><li>undefined</li><li>null</li><li>NaN</li></ul>"), [])
        self.assertEqual(jetons("<ul><li>undefined</li><li>NaN</li></ul>"), ["NaN", "undefined"])


class TestUrlsExternes(unittest.TestCase):
    """I2 : le segment /undefined, /null, /NaN ne compte que sur le même hôte ou en relatif."""

    def test_liens_externes_jamais_signales(self):
        for h in ("https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/undefined",
                  "https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/NaN",
                  "https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Operators/null",
                  "//cdn.autre.fr/js/null", "http://wa.me/undefined"):
            with self.subTest(h=h):
                self.assertEqual(jetons('<a href="{0}">Docs</a>'.format(h)), [])

    def test_meme_hote_et_relatif_signales(self):
        self.assertEqual(jetons('<a href="https://ex.fr/formations/null">F</a>'), ["null"])
        self.assertEqual(jetons('<a href="https://www.ex.fr/formations/null">F</a>'), ["null"])
        self.assertEqual(jetons('<a href="formations/undefined">F</a>'), ["undefined"])
        self.assertEqual(jetons('<a href="/formations/undefined">F</a>'), ["undefined"])

    def test_parametre_signale_sur_tout_hote(self):
        self.assertEqual(jetons('<a href="https://autre.fr/p?id=undefined">F</a>'), ["undefined"])

    def test_tel_mailto_et_objet_dans_une_url(self):
        self.assertEqual(jetons('<a href="tel:undefined">x</a>'), ["undefined"])
        self.assertEqual(jetons('<a href="mailto:undefined">x</a>'), ["undefined"])
        self.assertEqual(jetons('<a href="mailto:undefined@undefined.com">x</a>'), ["undefined"])
        self.assertEqual(jetons('<a href="mailto:contact@ex.fr">x</a><a href="tel:+33123456789">y</a><a href="mailto:null@ex.fr">z</a>'), [])
        self.assertEqual(jetons('<a href="/f/[object Object]">x</a>'), ["[object Object]"])
        self.assertEqual(jetons('<a href="/f/%5Bobject%20Object%5D">x</a>'), ["[object Object]"])
        self.assertEqual(jetons('<a href="/f?x=%5Bobject+Object%5D">x</a>'), ["[object Object]"])
        self.assertEqual(jetons('<a href="http://[invalide">x</a>'), [])


class TestInvalidDate(unittest.TestCase):
    def test_invalid_date_a_son_propre_jeton(self):
        self.assertEqual(jetons("<p>Mis à jour le Invalid Date</p>"), ["Invalid Date"])
        self.assertEqual(jetons("<p>Mis à jour le <time>Invalid Date</time></p>"), ["Invalid Date"])
        self.assertEqual(jetons("<p>Date : Invalid Date</p>"), ["Invalid Date"])
        self.assertEqual(jetons("<time datetime='Invalid Date'>x</time>"), ["Invalid Date"])

    def test_invalid_date_cite_dans_du_code_ou_invalid_dates(self):
        self.assertEqual(jetons("<p>L'objet <code>Invalid Date</code> apparaît quand le texte est mal formé.</p>"), [])
        self.assertEqual(jetons("<p>Les invalid dates sont rejetées. InvalidDate aussi.</p>"), [])

    def test_infinity_seulement_colle_a_une_valeur(self):
        self.assertEqual(jetons("<p>Prix : Infinity €</p>"), ["Infinity"])
        self.assertEqual(jetons("<p>-Infinity%</p>"), ["Infinity"])
        self.assertEqual(jetons("<p>Number.POSITIVE_INFINITY vaut Infinity en JavaScript.</p><p>Infinity</p>"), [])


class TestTitreEtMetadonnees(unittest.TestCase):
    def page(self, titre="Formation | Site", description="Une description normale de la page.", og=None):
        h = "<html><head><title>{0}</title><meta name=\"description\" content=\"{1}\">".format(titre, description)
        if og is not None:
            h += '<meta property="og:title" content="{0}">'.format(og)
        return h + "</head><body><p>Bonjour</p></body></html>"

    def test_segment_jeton_dans_le_titre(self):
        for titre in ("undefined | Site", "Site - NaN", "Formation — null — ILLITH", "undefined", "Formation · undefined"):
            with self.subTest(titre=titre):
                self.assertEqual(len(fuites(self.page(titre))), 1)

    def test_objet_et_invalid_date_dans_le_titre_ou_la_description(self):
        self.assertEqual(jetons(self.page("[object Object] - Site")), ["[object Object]"])
        self.assertEqual(jetons(self.page(description="Mise à jour : Invalid Date")), ["Invalid Date"])
        self.assertEqual(jetons(self.page(description="undefined")), ["undefined"])
        self.assertEqual(jetons(self.page(og="undefined | Site")), ["undefined"])

    def test_signature_du_titre(self):
        r = fuites(self.page("undefined | Site"))
        self.assertEqual(r[0]["signature"], "undefined — titre « undefined | Site »")

    def test_meme_fuite_titre_et_og_title_comptee_une_fois(self):
        r = fuites(self.page("undefined | Site", og="undefined | Site"))
        self.assertEqual([e["n"] for e in r], [1])

    def test_titres_de_tutoriel_propres(self):
        for titre in ("Comprendre undefined et null en JavaScript | Blog", "Qu'est-ce que NaN ? - Tutoriel JavaScript",
                      "La valeur null en JavaScript", "Null | Boutique", "NaN : pourquoi 0/0 ne plante pas | Blog",
                      "Check-in en ligne - Hôtel", "Nul n'est censé ignorer la loi | Droit"):
            with self.subTest(titre=titre):
                self.assertEqual(jetons(self.page(titre, description="Article sur la valeur null et undefined en JavaScript.")), [])

    def test_titre_de_svg_et_page_technique(self):
        self.assertEqual(jetons("<svg><title>undefined</title></svg>"), [])
        self.assertEqual(jetons(self.page("undefined | Doc").replace("<p>Bonjour</p>", "<pre>x</pre>")), [])


class TestCasCourts(unittest.TestCase):
    def test_fuites_courtes_recuperees(self):
        for html in ("<p>Bonjour undefined</p>", "<h1>Bienvenue undefined</h1>", "<p>Bonjour null !</p>", "<p>Par undefined</p>",
                     "<p>Écrit par undefined le 12 mars</p>", "<p>undefined undefined</p>", "<p>Bonjour undefined undefined</p>",
                     "<p>Formateur : undefined undefined</p>", "<p>NaN inscrits</p>", "<p>NaN/NaN/NaN</p>", "<p>Lieu : undefined, Paris</p>",
                     "<button>undefined</button>", "<p>3 / undefined places</p>", "<p>Il reste NaN jours</p>"):
            with self.subTest(html=html):
                self.assertTrue(jetons(html), html)

    def test_pas_de_faux_positif_des_cas_courts(self):
        for html in ("<p>Par défaut</p>", "<p>Bonjour tout le monde</p>", "<p>Par null ou undefined, le test échoue.</p>",
                     "<p>Bienvenue dans le guide sur null et undefined.</p>", "<p>NaN est différent de NaN.</p>",
                     "<p>Valeur : <code>NaN/NaN</code></p>", "<p>null, undefined et NaN sont trois valeurs distinctes.</p>"):
            with self.subTest(html=html):
                self.assertEqual(jetons(html), [])

    def test_etiquette_trop_longue_ou_pedagogique_n_est_pas_une_valeur(self):
        for html in ("<p>La propriété renvoie la valeur : null</p>", "<p>Q : que renvoie 0/0 ? R : NaN</p>", "<p>'a' * 2 : NaN</p>",
                     "<ul><li>Number : NaN</li><li>String : undefined</li></ul>", "<p>Par défaut : undefined</p>", "<p>Default: null</p>"):
            with self.subTest(html=html):
                self.assertEqual(jetons(html), [])

    def test_libelle_de_bouton_qui_finit_par_un_jeton(self):
        self.assertEqual(jetons("<button>S'inscrire à undefined</button>"), ["undefined"])
        self.assertEqual(jetons("<button>Valider</button><p>La valeur undefined est falsy.</p>"), [])

    def test_alt_en_fin_de_phrase(self):
        self.assertEqual(jetons('<img src="/a.png" alt="Photo de undefined">'), ["undefined"])
        self.assertEqual(jetons('<img src="/a.png" alt="Formation NaN.">'), ["NaN"])
        self.assertEqual(jetons('<img src="/a.png" alt="La valeur undefined en JavaScript">'), [])
        self.assertEqual(jetons('<img src="/a.png" alt="Schéma"><pre>x</pre><img src="/b.png" alt="Photo de undefined">'), [])
        self.assertEqual(jetons('<input placeholder="undefined">'), ["undefined"])


class TestPerformanceEtStabilite(unittest.TestCase):
    def test_cinq_mille_null_dans_un_paragraphe(self):
        import time
        for html in ("<p>" + "null " * 5000 + "</p>", "<p>" + "Le null " * 5000 + "fin</p>", "<p>" + "Prix : null € " * 5000 + "</p>",
                     "<div>" + "<span>null</span> " * 5000 + "</div>"):
            t0 = time.perf_counter()
            fuites(html)
            self.assertLess(time.perf_counter() - t0, 0.5, html[:30])

    def test_signature_stable_entre_elements_voisins(self):
        a = fuites("<div><span>NaN%</span><span>de satisfaction</span></div>")
        b = fuites("<div><span>NaN%</span> <span>de satisfaction</span></div>")
        self.assertEqual(a, b)
        self.assertEqual(fuites("<p><span>undefined</span>€</p>"), fuites("<p><span>undefined</span> €</p>"))


if __name__ == "__main__":
    unittest.main()
