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
import html_observateurs as ho  # noqa: E402
import a11y_svg  # noqa: E402
from site_local import HTML, SiteLocal  # noqa: E402


def crawler(routes):
    """Crawl d'un SiteLocal (aucun réseau externe) → issues.json."""
    with SiteLocal(routes) as site, tempfile.TemporaryDirectory() as d:
        subprocess.run([sys.executable, str(SCRIPTS / "crawl_site.py"), site.url, "--out", d, "--delay", "0", "--max-pages", "10",
                        "--liens-externes", "0", "--ressources", "0"], check=True, capture_output=True, timeout=120)
        return json.loads(pathlib.Path(d, "issues.json").read_text(encoding="utf-8")), site.base


def res(html):
    return ho.analyser(html, {}, "https://ex.fr/", modules=[("a11y_svg", a11y_svg)])["a11y_svg"]


def signatures(r):
    return {k: [(e["signature"], e["n"]) for e in v] for k, v in r.items()}


def vide(html):
    """Aucun constat d'aucune sorte pour ce HTML."""
    return res(html) == {"non_masques": [], "img_sans_nom": [], "dans_controle_nomme": []}


ICONE = '<span class="icone"><svg viewBox="0 0 24 24" fill="none"><path d="M1 1"/></svg></span>'


class TestSvg(unittest.TestCase):
    def test_regroupement_et_cas_ignores(self):
        html = (ICONE * 12
                + '<svg viewBox="0 0 24 24" fill="none" aria-hidden="true"></svg>'            # masqué
                + '<svg role="img" viewBox="0 0 10 10"><title>Note : 5 sur 5</title></svg>'    # nommé
                + '<svg role="img" viewBox="0 0 8 8"></svg>'                                   # image sans nom
                + '<div hidden><svg viewBox="0 0 1 1"></svg></div>'                            # ancêtre masqué
                + '<svg role="presentation"></svg><svg width="0" height="0"><defs></defs></svg>'
                + '<svg aria-label="Logo" viewBox="0 0 2 2"><svg viewBox="0 0 3 3"></svg></svg>'  # nommé, imbriqué
                + '<button><svg viewBox="0 0 16 16"></svg>Envoyer</button>'                    # bouton nommé : simple conseil
                + '<a href="/x"><svg viewBox="0 0 9 9"></svg></a>'                              # lien sans nom : laissé à T13
                + '<a href="/y">Voir <svg viewBox="0 0 7 7"></svg></a>')                        # lien nommé : simple conseil
        r = res(html)
        self.assertEqual(signatures(r), {
            "non_masques": [("viewBox=0 0 24 24 fill=none stroke=—", 12)],
            "img_sans_nom": [("viewBox=0 0 8 8 fill=— stroke=—", 1)],
            "dans_controle_nomme": [("viewBox=0 0 16 16 fill=— stroke=—", 1), ("viewBox=0 0 7 7 fill=— stroke=—", 1)]})

    def test_un_constat_pour_un_composant_sur_tout_le_site(self):
        page = '<html lang="fr"><head><title>Page {0} de test assez longue</title></head><body><main>{1}<a href="/b">b</a></main></body></html>'
        issues, base = crawler({"/": (200, HTML, page.format("A", ICONE * 12)), "/b": (200, HTML, page.format("B", ICONE * 12))})
        it = issues["svg_non_masque"]
        self.assertEqual((it["count"], it["severity"], it["domaine"], len(it["examples"])), (24, "moyenne", "Accessibilité", 1))
        self.assertEqual((it["examples"][0]["occurrences"], it["examples"][0]["pages"]), (24, 2))
        self.assertNotIn("svg_img_sans_nom", issues)
        self.assertNotIn("svg_redondant_controle", issues)

    def test_severites_et_exemples_des_trois_constats(self):
        page = ('<html lang="fr"><head><title>Page de test assez longue</title></head><body><main>'
                '<svg role="img" viewBox="0 0 8 8"></svg><a href="/b">Voir <svg viewBox="0 0 7 7"></svg></a></main></body></html>')
        issues, _ = crawler({"/": (200, HTML, page), "/b": (200, HTML, page)})
        self.assertEqual((issues["svg_img_sans_nom"]["severity"], issues["svg_img_sans_nom"]["count"]), ("haute", 2))
        self.assertEqual((issues["svg_redondant_controle"]["severity"], issues["svg_redondant_controle"]["count"]), ("basse", 2))
        self.assertNotIn("svg_non_masque", issues)

    def test_cas_wave_etoiles_et_pictogrammes_donnent_peu_de_constats(self):
        # 74 flèches, 30 étoiles de notes (deux jaunes), 24 icônes colorées : une poignée de signatures, pas 128 constats
        html = ('<span class="fleche"><svg viewBox="0 0 24 24" fill="none"><path d="M1 1"/></svg></span>' * 74
                + '<div class="etoile"><svg viewBox="0 0 20 20" fill="#FBBC05"><path d="M1 1"/></svg></div>' * 20
                + '<div class="etoile"><svg viewBox="0 0 20 20" fill="#FFC037"><path d="M1 1"/></svg></div>' * 10
                + '<i class="ico"><svg viewBox="0 0 32 32" fill="#e91e63"></svg></i>' * 24)
        r = res(html)["non_masques"]
        self.assertEqual([(e["signature"], e["n"]) for e in r], [  # triés par n décroissant
            ("viewBox=0 0 24 24 fill=none stroke=—", 74),
            ("viewBox=0 0 32 32 fill=#e91e63 stroke=—", 24),
            ("viewBox=0 0 20 20 fill=#FBBC05 stroke=—", 20),
            ("viewBox=0 0 20 20 fill=#FFC037 stroke=—", 10)])


class TestFauxPositifs(unittest.TestCase):
    """Cas qui ne doivent produire AUCUN constat (ni principal, ni conseil)."""

    def test_ancetre_aria_hidden(self):
        self.assertTrue(vide('<div aria-hidden="true"><span><svg viewBox="0 0 24 24"></svg></span></div>'))

    def test_svg_aria_hidden(self):
        self.assertTrue(vide('<svg aria-hidden="true" viewBox="0 0 24 24"></svg>'))

    def test_role_presentation_et_none(self):
        self.assertTrue(vide('<svg role="presentation" viewBox="0 0 1 1"></svg><svg role="none" viewBox="0 0 1 1"></svg>'
                             '<svg role=" NONE " viewBox="0 0 1 1"></svg>'))

    def test_role_img_avec_aria_label(self):
        self.assertTrue(vide('<svg role="img" aria-label="Logo" viewBox="0 0 1 1"></svg>'))

    def test_titre(self):
        self.assertTrue(vide('<svg viewBox="0 0 1 1"><title>Note</title></svg>'))
        self.assertTrue(vide('<svg role="img" viewBox="0 0 1 1"><title>Note</title></svg>'))

    def test_aria_labelledby_vers_un_id_existant(self):
        self.assertTrue(vide('<svg role="img" aria-labelledby="t" viewBox="0 0 1 1"></svg><p id="t">Note</p>'))
        self.assertTrue(vide('<p id="t">Note</p><svg aria-labelledby="t" viewBox="0 0 1 1"></svg>'))
        self.assertTrue(vide('<svg role="img" aria-labelledby="a b" viewBox="0 0 1 1"><title id="b">N</title></svg>'))

    def test_svg_dans_template_ou_element_masque(self):
        for h in ('<template><svg viewBox="0 0 1 1"></svg></template>', '<div hidden><svg viewBox="0 0 1 1"></svg></div>',
                  '<div style="display:none"><svg viewBox="0 0 1 1"></svg></div>', '<div class="hidden"><svg viewBox="0 0 1 1"></svg></div>',
                  '<svg style="display: none" viewBox="0 0 1 1"></svg>', '<noscript><svg viewBox="0 0 1 1"></svg></noscript>',
                  '<span hidden><a href="/x">Voir <svg viewBox="0 0 1 1"></svg></a></span>'):
            self.assertTrue(vide(h), h)

    def test_conteneur_de_definitions_et_imbrique(self):
        self.assertTrue(vide('<svg width="0" height="0" style="position:absolute"><symbol id="a"></symbol></svg>'))
        self.assertTrue(vide('<svg height="0"><defs></defs></svg>'))
        self.assertTrue(vide('<svg aria-label="Logo"><svg viewBox="0 0 1 1"><g></g></svg></svg>'))

    def test_svg_seul_contenu_d_un_lien_ou_bouton_sans_nom_laisse_a_t13(self):
        self.assertTrue(vide('<a href="/x"><svg viewBox="0 0 1 1"></svg></a>'))
        self.assertTrue(vide('<button type="button"><svg viewBox="0 0 1 1"></svg></button>'))
        self.assertTrue(vide('<a href="/x"><span><svg viewBox="0 0 1 1"></svg></span> <span aria-hidden="true">texte masqué</span></a>'))

    def test_svg_dans_lien_ou_bouton_nomme_n_est_pas_le_constat_principal(self):
        for h in ('<button aria-label="Fermer"><svg viewBox="0 0 1 1"></svg></button>',
                  '<a href="/x" title="Accueil"><svg viewBox="0 0 1 1"></svg></a>',
                  '<a href="/x">Contact <svg viewBox="0 0 1 1"></svg></a>',
                  '<button><svg viewBox="0 0 1 1"></svg> <span class="sr-only">Menu</span></button>',
                  '<a href="/x"><svg viewBox="0 0 1 1"></svg><img src="/l.png" alt="Logo"></a>'):
            r = res(h)
            self.assertEqual(r["non_masques"], [], h)
            self.assertEqual(r["img_sans_nom"], [], h)
            self.assertEqual([e["n"] for e in r["dans_controle_nomme"]], [1], h)  # au plus un conseil séparé

    def test_svg_nomme_dans_un_lien_donne_un_nom_au_lien(self):
        self.assertTrue(vide('<a href="/"><svg role="img" aria-label="Accueil" viewBox="0 0 1 1"></svg></a>'))
        r = res('<a href="/"><svg role="img" aria-label="Accueil" viewBox="0 0 1 1"></svg><svg viewBox="0 0 2 2"></svg></a>')
        self.assertEqual((r["non_masques"], r["img_sans_nom"], len(r["dans_controle_nomme"])), ([], [], 1))

    def test_lien_sans_href_n_est_pas_un_controle(self):
        self.assertEqual(signatures(res('<a><svg viewBox="0 0 1 1"></svg></a>'))["non_masques"],
                         [("viewBox=0 0 1 1 fill=— stroke=—", 1)])


class TestVrais_positifs(unittest.TestCase):
    def test_icone_non_masquee_hors_controle(self):
        self.assertEqual(signatures(res('<p>Texte <svg viewBox="0 0 1 1"></svg></p>'))["non_masques"],
                         [("viewBox=0 0 1 1 fill=— stroke=—", 1)])

    def test_aria_labelledby_vide_ou_vers_un_id_absent_n_est_pas_un_nom(self):
        self.assertEqual(len(res('<svg role="img" aria-labelledby="" viewBox="0 0 1 1"></svg>')["img_sans_nom"]), 1)
        self.assertEqual(len(res('<svg role="img" aria-labelledby="absent" viewBox="0 0 1 1"></svg>')["img_sans_nom"]), 1)
        self.assertEqual(len(res('<svg aria-labelledby="absent" viewBox="0 0 1 1"></svg>')["non_masques"]), 1)

    def test_aria_label_ou_titre_vides_ne_nomment_pas(self):
        self.assertEqual(len(res('<svg role="img" aria-label="  " viewBox="0 0 1 1"></svg>')["img_sans_nom"]), 1)
        self.assertEqual(len(res('<svg role="img" viewBox="0 0 1 1"><title> </title></svg>')["img_sans_nom"]), 1)

    def test_role_graphics_sans_nom(self):
        self.assertEqual(len(res('<svg role="graphics-document" viewBox="0 0 1 1"></svg>')["img_sans_nom"]), 1)

    def test_svg_auto_ferme(self):
        self.assertEqual(len(res('<p><svg viewBox="0 0 1 1"/></p><p><svg viewBox="0 0 1 1"/></p>')["non_masques"]), 1)

    def test_titre_du_document_ne_nomme_pas_un_svg(self):
        r = res('<html><head><title>Page</title></head><body><svg viewBox="0 0 1 1"></svg></body></html>')
        self.assertEqual(len(r["non_masques"]), 1)

    def test_resultat_est_du_json_et_deterministe(self):
        h = ICONE * 3 + '<svg role="img" viewBox="0 0 8 8"></svg>'
        self.assertEqual(json.dumps(res(h)), json.dumps(res(h)))


class TestSignatureParComposant(unittest.TestCase):
    def test_le_parent_ne_change_pas_la_signature(self):
        h = ''.join('<{0} class="{1}"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><path d="M1 1"/></svg></{0}>'.format(t, c)
                    for t, c in (("div", "flex gap-3"), ("span", "bg-white border"), ("span", "inline-flex text-rose"), ("li", "")))
        self.assertEqual(signatures(res(h))["non_masques"], [("viewBox=0 0 24 24 fill=none stroke=currentColor", 4)])

    def test_la_taille_et_le_trace_ne_changent_pas_la_signature(self):
        h = ('<svg viewBox="0 0 24 24" width="15" height="15" fill="#FBBC05"><path d="M12 17.3L18.2"/></svg>'
             '<svg viewBox="0 0 24 24" width="20" height="20" fill="#FBBC05"><path d="M12 17.3L18.2"/></svg>'
             '<svg viewBox="0 0 24 24" width="18" height="18" fill="#FBBC05"><path d="M5 5h14"/></svg>')
        r = res(h)["non_masques"]
        self.assertEqual([(e["signature"], e["n"]) for e in r], [("viewBox=0 0 24 24 fill=#FBBC05 stroke=—", 3)])
        self.assertIn("+1 autre tracé", r[0]["exemple"])  # deux tracés différents dans le groupe

    def test_parent_seulement_si_le_svg_n_a_aucun_attribut_propre(self):
        r = res('<div class="z b a"><svg></svg></div><p><svg></svg></p><p><svg></svg></p>')["non_masques"]
        self.assertEqual([(e["signature"], e["n"]) for e in r], [("viewBox=— fill=— stroke=— parent=p", 2),
                                                                 ("viewBox=— fill=— stroke=— parent=div.a.b", 1)])

    def test_exemple_lisible_sans_parametres_de_requete(self):
        h = ('<svg viewBox="0 0 24 24" width="15" height="15" fill="#FBBC05" class="shrink-0 a?b=1" data-x="y">'
             '<path d="M12 17.3L18.2 21l-1.6-7L22 9.2l-7.2-.6L12 2 9.2 8.6 2 9.2z"/><path d="M0 0"/></svg>')
        e = res(h)["non_masques"][0]["exemple"]
        self.assertTrue(e.startswith('<svg viewBox="0 0 24 24" width="15" height="15" fill="#FBBC05"'), e)
        self.assertIn('<path d="M12 17.3L18.2 21l-1.6-7', e)
        self.assertNotIn("?", e)
        self.assertNotIn("data-x", e)
        self.assertRegex(e, r"tracé [0-9a-f]{8}")
        self.assertLess(len(e), 200)
        self.assertEqual(e, res(h)["non_masques"][0]["exemple"])  # déterministe

    def test_exemple_sans_trace(self):
        self.assertEqual(res('<svg viewBox="0 0 8 8"></svg>')["non_masques"][0]["exemple"], '<svg viewBox="0 0 8 8">')

    def test_tri_par_n_decroissant_puis_signature(self):
        h = '<svg viewBox="0 0 1 1"></svg>' + '<svg viewBox="0 0 9 9"></svg>' * 3 + '<svg viewBox="0 0 5 5"></svg>' * 3
        self.assertEqual([e["n"] for e in res(h)["non_masques"]], [3, 3, 1])
        self.assertEqual([e["signature"][:16] for e in res(h)["non_masques"]], ["viewBox=0 0 5 5 ", "viewBox=0 0 9 9 ", "viewBox=0 0 1 1 "])

    def test_constats_tries_par_n_decroissant_dans_issues_json(self):
        page = ('<html lang="fr"><head><title>Page de test assez longue</title></head><body><main>'
                '<svg viewBox="0 0 1 1"></svg>' + '<svg viewBox="0 0 9 9"></svg>' * 4 + '<a href="/b">b</a></main></body></html>')
        issues, _ = crawler({"/": (200, HTML, page), "/b": (200, HTML, page)})
        ex = issues["svg_non_masque"]["examples"]
        self.assertEqual([(e["signature"][:16], e["occurrences"]) for e in ex], [("viewBox=0 0 9 9 ", 8), ("viewBox=0 0 1 1 ", 2)])
        self.assertIn("exemple", ex[0])
        self.assertEqual(list(ex[0]).index("exemple") < list(ex[0]).index("exemples_pages"), True)  # lisible avant les URL (ex_str coupe à 220)


def etoile(fill, taille, d="M12 17.3L18.2 21l-1.6-7L22 9.2"):
    return '<svg viewBox="0 0 24 24" width="{0}" height="{0}" fill="{1}"><path d="{2}"/></svg>'.format(taille, fill, d)


def pictos(n, d):
    return '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.7" class="shrink-0"><path d="{0}"/></svg>'.format(d) * n


def accueil_synthetique():
    """HTML inventé, de même structure qu'un accueil réel : un composant d'icônes à trait dont le tracé change et le parent aussi,
    des étoiles de notes de trois couleurs, un guillemet, des icônes dans des liens et boutons nommés, des icônes masquées
    (ancêtre aria-hidden) et des panneaux repliés (hidden + display:none) pleins d'icônes."""
    glyphes = ("M5 12h14", "M12 7v5l3 2", "M8 11l2 2 5-5", "M4 6h16v12H4z", "M12 3l9 5-9 5-9-5z")
    parents = ('<div class="flex gap-3">', '<span class="bg-white border">', '<span class="inline-flex text-rose">',
               '<span class="bg-rose-50 h-12">', '<p class="mt-2">', '<li class="py-1">')
    fermetures = ("</div>", "</span>", "</span>", "</span>", "</p>", "</li>")
    avantages = "".join(p + pictos(1, g) + f for g in glyphes for p, f in zip(parents, fermetures))  # 30 icônes exposées
    return "".join([
        avantages,
        '<nav aria-hidden="true">' + pictos(8, "M1 1h2") + '</nav>',
        '<span aria-hidden="true"><span>' + pictos(3, "M2 2h2") + '</span></span>',
        '<div data-panel hidden style="display:none">' + pictos(40, "M3 3h3") + etoile("#FBBC05", 15) * 10 + '</div>',
        '<span class="inline-flex gap-[3px]">' + etoile("#FBBC05", 15) * 15 + '</span>',
        '<span class="flex gap-0.5">' + etoile("#FFC037", 13) * 5 + '</span>',
        '<span class="flex gap-0.5">' + etoile("#D81B60", 16) * 5 + '</span>',
        '<figcaption class="flex gap-3">' + '<svg viewBox="0 0 24 24" width="22" height="22" fill="#FDE2F3"><path d="M7 7h4v4H7z"/></svg>' * 4 + '</figcaption>',
        ''.join('<a href="/v{0}" class="inline-flex">Regarder<svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor"><path d="M8 5v14l11-7z"/></svg></a>'.format(i)
                for i in range(3)),
        ''.join('<button type="button">Suivant' + pictos(1, "M9 18l6-6-6-6") + '</button>' for _ in range(2)),
    ])


class TestAccueilSynthetique(unittest.TestCase):
    """Régression : un accueil réel donnait 14 signatures pour 4 composants, parce que la signature dépendait des classes du parent."""

    def setUp(self):
        self.r = res(accueil_synthetique())

    def test_comptes_par_signature_et_tri(self):
        self.assertEqual(signatures(self.r)["non_masques"], [
            ("viewBox=0 0 24 24 fill=none stroke=currentColor", 30),
            ("viewBox=0 0 24 24 fill=#FBBC05 stroke=—", 15),
            ("viewBox=0 0 24 24 fill=#D81B60 stroke=—", 5),
            ("viewBox=0 0 24 24 fill=#FFC037 stroke=—", 5),
            ("viewBox=0 0 24 24 fill=#FDE2F3 stroke=—", 4)])
        self.assertEqual(signatures(self.r)["dans_controle_nomme"], [
            ("viewBox=0 0 24 24 fill=currentColor stroke=—", 3),
            ("viewBox=0 0 24 24 fill=none stroke=currentColor", 2)])
        self.assertEqual(self.r["img_sans_nom"], [])

    def test_peu_de_signatures_pour_pres_de_soixante_icones(self):
        n = sum(e["n"] for e in self.r["non_masques"] + self.r["dans_controle_nomme"])
        sigs = len(self.r["non_masques"]) + len(self.r["dans_controle_nomme"])
        self.assertEqual((n, sigs), (64, 7))

    def test_le_composant_d_icones_a_trait_est_un_seul_constat_avec_son_exemple(self):
        g = self.r["non_masques"][0]
        self.assertIn('class="shrink-0"', g["exemple"])
        self.assertIn("+4 autres tracés", g["exemple"])  # cinq glyphes, un seul composant

    def test_les_icones_masquees_et_les_panneaux_replies_ne_comptent_pas(self):
        tout = self.r["non_masques"] + self.r["dans_controle_nomme"]
        self.assertEqual(sum(e["n"] for e in tout), 64)  # 30 + 15 + 5 + 5 + 4 + 5 (liens et boutons nommés) ; 8 + 3 + 50 ignorés


class TestEtoilesDeNote(unittest.TestCase):
    ETOILES = etoile("#FBBC05", 15) * 5

    def test_enveloppe_role_img_avec_aria_label_couvre_les_etoiles(self):
        self.assertTrue(vide('<span role="img" aria-label="Note : 5 sur 5">' + self.ETOILES + '</span>'))
        self.assertTrue(vide('<div role="img" aria-label="Note : 5 sur 5"><div>' + self.ETOILES + '</div></div>'))

    def test_enveloppe_role_img_nommee_par_titre_ou_aria_labelledby(self):
        self.assertTrue(vide('<span role="img" title="Note : 5 sur 5">' + self.ETOILES + '</span>'))
        self.assertTrue(vide('<span role="img" aria-labelledby="n">' + self.ETOILES + '</span><b id="n">Note : 5 sur 5</b>'))
        self.assertTrue(vide('<b id="n">Note : 5 sur 5</b><span role="img" aria-labelledby="n">' + self.ETOILES + '</span>'))

    def test_svg_role_img_dans_une_enveloppe_nommee_est_couvert_aussi(self):
        self.assertTrue(vide('<span role="img" aria-label="Note"><svg role="img" viewBox="0 0 1 1"></svg></span>'))

    def test_enveloppe_role_img_sans_nom_ne_couvre_rien(self):
        for h in ('<span role="img">' + self.ETOILES + '</span>', '<span role="img" aria-label=" ">' + self.ETOILES + '</span>',
                  '<span role="img" aria-labelledby="absent">' + self.ETOILES + '</span>'):
            self.assertEqual([e["n"] for e in res(h)["non_masques"]], [5], h)

    def test_un_nom_sur_un_autre_role_ne_couvre_pas(self):
        self.assertEqual([e["n"] for e in res('<span aria-label="Note">' + self.ETOILES + '</span>')["non_masques"]], [5])
        self.assertEqual([e["n"] for e in res('<span role="group" aria-label="Note">' + self.ETOILES + '</span>')["non_masques"]], [5])

    def test_variante_texte_masque_visuellement_et_etoiles_aria_hidden(self):
        self.assertTrue(vide('<span><span class="sr-only">Note : 5 sur 5</span>'
                             + self.ETOILES.replace("<svg ", '<svg aria-hidden="true" ') + '</span>'))

    def test_etoiles_a_cote_de_la_note_chiffree_restent_signalees_sans_aria_hidden(self):
        self.assertEqual([e["n"] for e in res('<span>' + self.ETOILES + ' 4,8 / 5</span>')["non_masques"]], [5])


class TestCorrectionsDeRevue(unittest.TestCase):
    def test_svg_role_img_seul_dans_un_lien_ou_bouton_sans_nom_laisse_a_t13(self):
        self.assertTrue(vide('<a href="/x"><svg role="img" viewBox="0 0 1 1"></svg></a>'))
        self.assertTrue(vide('<button><svg role="img" viewBox="0 0 1 1"></svg></button>'))
        r = res('<a href="/x">Voir <svg role="img" viewBox="0 0 1 1"></svg></a>')  # lien nommé : l'image sans nom reste signalée
        self.assertEqual(len(r["img_sans_nom"]), 1)

    def test_sprite_masque_par_style_ou_classe_ou_ne_contenant_que_des_definitions(self):
        for h in ('<svg style="position:absolute;width:0;height:0"><path d="M1 1"/></svg>',
                  '<svg style="height: 0px; position:absolute" viewBox="0 0 1 1"><path d="M1 1"/></svg>',
                  '<svg class="absolute w-0 h-0"><path d="M1 1"/></svg>',
                  '<svg class="sprite h-0"><path d="M1 1"/></svg>',
                  '<svg><defs><linearGradient id="g"></linearGradient></defs></svg>',
                  '<svg><symbol id="a"><path d="M1 1"/></symbol><symbol id="b"></symbol></svg>',
                  '<svg><style>.a{fill:red}</style></svg>'):
            self.assertTrue(vide(h), h)

    def test_svg_qui_dessine_avec_des_defs_reste_signale(self):
        self.assertEqual(len(res('<svg viewBox="0 0 1 1"><defs><linearGradient id="g"/></defs><rect width="1" height="1"/></svg>')["non_masques"]), 1)
        self.assertEqual(len(res('<svg viewBox="0 0 1 1"><defs></defs><use href="#a"/></svg>')["non_masques"]), 1)

    def test_commandes_aria_hors_a_et_button(self):
        for h in ('<div role="button" aria-label="Fermer"><svg viewBox="0 0 1 1"></svg></div>',
                  '<div role="button" tabindex="0"><svg viewBox="0 0 1 1"></svg></div>',
                  '<span role="link"><svg viewBox="0 0 1 1"></svg></span>', '<li role="tab"><svg viewBox="0 0 1 1"></svg></li>'):
            self.assertEqual(res(h)["non_masques"], [], h)
        r = res('<div role="button" aria-label="Fermer"><svg viewBox="0 0 1 1"></svg></div>')
        self.assertEqual(len(r["dans_controle_nomme"]), 1)
        self.assertEqual(len(res('<div role="button" tabindex="0"><svg viewBox="0 0 1 1"></svg><span>Menu</span></div>')["dans_controle_nomme"]), 1)

    def test_libelles(self):
        issues, _ = crawler({"/": (200, HTML, '<html lang="fr"><head><title>Page de test assez longue</title></head><body><main>'
                                              '<svg viewBox="0 0 1 1"></svg><a href="/b">Voir <svg viewBox="0 0 2 2"></svg></a></main></body></html>'),
                             "/b": (200, HTML, "<html><body>b</body></html>")})
        lib = issues["svg_redondant_controle"]["label"]
        self.assertIn("RGAA 1.2.4", lib)
        self.assertNotIn("Conseil", lib)
        self.assertIn("RGAA 1.2.4", issues["svg_non_masque"]["label"])
        self.assertNotIn("par composant", issues["svg_non_masque"]["label"])


if __name__ == "__main__":
    unittest.main()
