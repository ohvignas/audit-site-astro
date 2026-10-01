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
import donnees_structurees  # noqa: E402
import html_observateurs as ho  # noqa: E402
from site_local import HTML, SiteLocal  # noqa: E402

TEXTE = "<p>" + "Formation de démonstration pour tester la lecture du texte visible de la page. " * 3 + "</p>"


def crawler(routes):
    """Crawl d'un SiteLocal (aucun réseau externe) → issues.json."""
    with SiteLocal(routes) as site, tempfile.TemporaryDirectory() as d:
        subprocess.run([sys.executable, str(SCRIPTS / "crawl_site.py"), site.url, "--out", d, "--delay", "0", "--max-pages", "10",
                        "--liens-externes", "0", "--ressources", "0"], check=True, capture_output=True, timeout=120)
        return json.loads(pathlib.Path(d, "issues.json").read_text(encoding="utf-8"))


def res(blocs, brut=""):
    html = "".join('<script type="application/ld+json">{0}</script>'.format(json.dumps(b)) for b in blocs) + brut
    r = ho.analyser(html, {}, "https://ex.fr/", modules=[("donnees_structurees", donnees_structurees)])["donnees_structurees"]
    return {k: [e["signature"] for e in v] for k, v in r.items()}


def une(bloc, corps=""):
    return res([bloc], corps)


class TestDonnees(unittest.TestCase):
    def test_requis_et_retires(self):
        blocs = [{"@context": "https://schema.org", "@type": "Event", "name": "Atelier"},
                 {"@context": "https://schema.org", "@graph": [
                     {"@type": "Product", "name": "X", "offers": {"@type": "Offer", "price": "10", "priceCurrency": "EUR"}},
                     {"@type": "Product", "name": "Y"}]},
                 {"@type": "ClaimReview", "claimReviewed": "x"},
                 {"@type": "Course", "name": "C", "description": "D", "provider": {"@type": "Organization", "name": "O"}},
                 {"@type": "Course", "name": "C2", "description": "D2", "hasCourseInstance": {"@type": "CourseInstance"}},
                 {"@type": ["Organization", "Restaurant"], "name": "R"},
                 {"@type": "Book", "name": "Livre", "potentialAction": {"@type": "ReadAction"}}]
        self.assertEqual(res(blocs, '<script type="application/ld+json">{invalide</script>'), {
            "manquantes": ["Event : startDate, location", "Product : offers|review|aggregateRating", "Restaurant : address"],
            "retires": ["ClaimReview : affichage en cours de retrait (bannière Google du 12/06/2025)",
                        "Course Info (hasCourseInstance) : documentation supprimée le 09/09/2025"]})

    def test_propre(self):  # mêmes objets que le jumeau propre
        self.assertEqual(res([{"@type": "EducationalOrganization", "name": "Cobaye Formation"},
                              {"@type": "Course", "name": "No-code", "description": "Formation", "provider": {"@id": "/#o"}},
                              {"@type": "Article", "headline": "Titre", "author": {"@type": "Person", "name": "Camille"}},
                              {"@type": "Event", "name": "Atelier", "startDate": "2026-11-05T09:00:00+01:00",
                               "location": {"@type": "Place", "name": "Centre", "address": "1 rue de Paris, 75001 Paris"}}]),
                         {"manquantes": [], "retires": []})

    # --- site de formation : Course + Organization (schema.org valide) ---------------------------------------------------

    def test_formation_course_et_organisation_complets(self):
        r = res([{"@context": "https://schema.org", "@type": "EducationalOrganization", "name": "Cobaye", "url": "https://ex.fr/"},
                 {"@context": "https://schema.org", "@type": "Course", "name": "No-code", "description": "Formation",
                  "provider": {"@type": "Organization", "name": "Cobaye"}}])
        self.assertEqual(r, {"manquantes": [], "retires": []})

    def test_course_info_est_info_seulement(self):
        r = une({"@type": "Course", "name": "C", "description": "D", "hasCourseInstance": [{"@type": "CourseInstance"}]})
        self.assertEqual(r["manquantes"], [])  # Google exige seulement name et description pour la liste de cours
        self.assertEqual(r["retires"], ["Course Info (hasCourseInstance) : documentation supprimée le 09/09/2025"])

    def test_course_sans_description_est_basse_hors_liste(self):
        # Google n'affiche « liste de cours » que pour au moins trois cours : un cours isolé est un constat à part (basse)
        r = une({"@type": "Course", "name": "C"})
        self.assertEqual((r["manquantes"], r["cours_isoles"]), ([], ["Course : description"]))

    def test_course_sans_description_dans_une_liste_de_trois_est_moyenne(self):
        cours = [{"@type": "Course", "name": "C1", "description": "d"}, {"@type": "Course", "name": "C2"},
                 {"@type": "Course", "name": "C3", "description": "d"}]
        liste = {"@type": "ItemList", "itemListElement": [{"@type": "ListItem", "position": i + 1, "item": c} for i, c in enumerate(cours)]}
        r = une(liste)
        self.assertEqual((r["manquantes"], "cours_isoles" in r), (["Course : description"], False))
        r = res(cours)  # trois cours de premier niveau : même chose
        self.assertEqual(r["manquantes"], ["Course : description"])
        self.assertNotIn("cours_isoles", r)

    # --- types retirés ou restreints --------------------------------------------------------------------------------------

    def test_types_retires(self):
        cas = {"SpecialAnnouncement": {"@type": "SpecialAnnouncement", "name": "x"},
               "Occupation": {"@type": "Occupation", "name": "x"},
               "Quiz": {"@type": "Quiz", "name": "x"},
               "HowTo": {"@type": "HowTo", "name": "x"},
               "Vehicle": {"@type": "Car", "name": "x", "offers": {"@type": "Offer", "price": "1"}},
               "Learning": {"@type": ["VideoObject", "LearningResource"], "name": "v", "thumbnailUrl": "u", "uploadDate": "2025-01-01",
                            "learningResourceType": "Concept Overview"}}
        for nom, bloc in cas.items():
            r = une(bloc)
            self.assertEqual(len(r["retires"]), 1, nom)
        self.assertIn("Estimated salary", une(cas["Occupation"])["retires"][0])
        self.assertIn("06/01/2026", une(cas["Quiz"])["retires"][0])
        self.assertIn("Vehicle listing", une(cas["Vehicle"])["retires"][0])
        self.assertIn("Learning video", une(cas["Learning"])["retires"][0])

    def test_faq_n_est_plus_un_resultat_enrichi_depuis_mai_2026(self):
        r = une({"@type": "FAQPage", "mainEntity": [{"@type": "Question", "name": "Q"}]})
        self.assertEqual(r["manquantes"], [])
        self.assertEqual(len(r["retires"]), 1)
        self.assertIn("07/05/2026", r["retires"][0])
        # un FAQPage sans mainEntity n'est plus une exigence Google : aucune propriété requise signalée
        self.assertEqual(une({"@type": "FAQPage"})["manquantes"], [])

    def test_sitelinks_search_box(self):
        r = une({"@type": "WebSite", "url": "https://ex.fr/", "potentialAction": {"@type": "SearchAction", "target": "https://ex.fr/?q={q}"}})
        self.assertEqual(len(r["retires"]), 1)
        self.assertIn("Sitelinks search box", r["retires"][0])
        self.assertEqual(une({"@type": "WebSite", "url": "https://ex.fr/"})["retires"], [])

    def test_types_encore_actifs_non_signales(self):
        r = res([{"@type": "Dataset", "name": "D", "description": "d"},
                 {"@type": "Book", "name": "L", "potentialAction": {"@type": "BorrowAction"}},
                 {"@type": "Recipe", "name": "R", "image": "i", "recipeInstructions": [{"@type": "HowToStep", "text": "t"}]},
                 {"@type": "VideoObject", "name": "v", "thumbnailUrl": "u", "uploadDate": "2025-01-01"},
                 {"@type": "Car", "name": "voiture sans offre"},
                 {"@type": "LearningResource", "name": "ressource", "learningResourceType": "Exercise"}])
        self.assertEqual(r, {"manquantes": [], "retires": []})

    def test_un_objet_a_deux_types_retires_compte_une_fois(self):
        r = une({"@type": ["VideoObject", "LearningResource"], "name": "v", "thumbnailUrl": "u", "uploadDate": "d", "educationalLevel": "x"})
        self.assertEqual(len(r["retires"]), 1)

    # --- propriétés requises ----------------------------------------------------------------------------------------------

    def test_groupes_requis_verifies_sur_les_pages_google(self):
        self.assertEqual(une({"@type": "JobPosting", "title": "T"})["manquantes"],
                         ["JobPosting : datePosted, description, hiringOrganization, jobLocation|applicantLocationRequirements"])
        # emploi 100 % télétravail : applicantLocationRequirements remplace jobLocation
        self.assertEqual(une({"@type": "JobPosting", "title": "T", "datePosted": "2026-01-01", "description": "d",
                              "hiringOrganization": {"@type": "Organization", "name": "O"},
                              "applicantLocationRequirements": {"@type": "Country", "name": "FR"}})["manquantes"], [])
        self.assertEqual(une({"@type": "VideoObject", "name": "v"})["manquantes"], ["VideoObject : thumbnailUrl, uploadDate"])
        self.assertEqual(une({"@type": "BreadcrumbList"})["manquantes"], ["BreadcrumbList : itemListElement"])
        self.assertEqual(une({"@type": "SoftwareApplication", "name": "A"})["manquantes"],
                         ["SoftwareApplication : offers, aggregateRating|review"])
        self.assertEqual(une({"@type": "Review", "reviewBody": "x"})["manquantes"], ["Review : author, reviewRating"])
        self.assertEqual(une({"@type": "Recipe", "name": "R"})["manquantes"], ["Recipe : image"])

    def test_aggregate_rating_imbriquee(self):
        r = une({"@type": "Product", "name": "P", "aggregateRating": {"@type": "AggregateRating", "ratingValue": "4.5"}})
        self.assertEqual(r["manquantes"], ["AggregateRating : ratingCount|reviewCount"])
        r = une({"@type": "Product", "name": "P", "aggregateRating": {"@type": "AggregateRating", "ratingValue": "4.5", "reviewCount": 12}})
        self.assertEqual(r["manquantes"], [])

    def test_valeurs_vides_comptent_comme_absentes(self):
        r = une({"@type": "Event", "name": " ", "startDate": "", "location": {}})
        self.assertEqual(r["manquantes"], ["Event : name, startDate, location"])

    def test_sous_types_de_local_business_comptes_une_fois(self):
        r = une({"@type": ["Electrician", "Plumber"], "name": "Dépannage"})
        self.assertEqual(r["manquantes"], ["Electrician : address"])
        self.assertEqual(une({"@type": "Dentist", "name": "D", "address": "1 rue X"})["manquantes"], [])

    def test_objet_imbrique_simple_reference_non_signale(self):
        # Course ou Event cités par nom/url dans un autre objet : ce sont des renvois, pas des pages candidates
        r = une({"@type": "EducationalOrganization", "name": "O",
                 "makesOffer": {"@type": "Offer", "itemOffered": {"@type": "Course", "name": "No-code", "url": "https://ex.fr/c"}},
                 "event": {"@type": "Event", "name": "Atelier", "url": "https://ex.fr/e"}})
        self.assertEqual(r["manquantes"], [])
        # mais un objet imbriqué plus riche est vérifié, et un objet de premier niveau l'est toujours
        r = une({"@type": "WebPage", "mainEntity": {"@type": "Event", "name": "Atelier", "offers": {"@type": "Offer", "price": "5"}}})
        self.assertEqual(r["manquantes"], ["Event : startDate, location"])

    # --- relecture 1 : seuls les objets que Google évalue (I1) ---------------------------------------------------------------

    def test_valeurs_d_autres_proprietes_ne_sont_pas_des_pages_candidates(self):
        cas = {
            "itemOffered": {"@type": "Offer", "price": "5", "itemOffered": {"@type": "Product", "name": "X", "sku": "1"}},
            "itemReviewed": {"@type": "Review", "author": "A", "reviewRating": {"@type": "Rating", "ratingValue": 4},
                             "itemReviewed": {"@type": "Product", "name": "X", "brand": "B"}},
            "catalogue": {"@type": "EducationalOrganization", "name": "O", "hasOfferCatalog": {
                "@type": "OfferCatalog", "itemListElement": [{"@type": "Offer", "itemOffered": {
                    "@type": "Course", "name": "C", "provider": {"@type": "Organization", "name": "O"}}}]}},
            "provider": {"@type": "Service", "name": "S", "provider": {"@type": "LocalBusiness", "name": "L", "telephone": "1"}},
            "location": {"@type": "Organization", "name": "O", "event": {"@type": "Event", "name": "E", "location": {
                "@type": "LocalBusiness", "name": "Lieu", "telephone": "1"}, "startDate": "2026-01-01"}},
            "author": {"@type": "Article", "headline": "H", "author": {"@type": "Event", "name": "pas un événement", "startDate": "x"},
                       "publisher": {"@type": "Product", "name": "P"}},
        }
        for nom, bloc in cas.items():
            self.assertEqual(une(bloc), {"manquantes": [], "retires": []}, nom)

    def test_objets_evalues_par_google_restent_controles(self):
        # racine, @graph, mainEntity, item d'un ListItem, Review et AggregateRating imbriqués
        self.assertEqual(une({"@type": "WebPage", "mainEntity": {"@type": "Product", "name": "P", "sku": "1"}})["manquantes"],
                         ["Product : offers|review|aggregateRating"])
        self.assertEqual(une({"@type": "ItemList", "itemListElement": [
            {"@type": "ListItem", "position": 1, "item": {"@type": "Product", "name": "P"}}]})["manquantes"],
            ["Product : offers|review|aggregateRating"])
        r = une({"@type": "Product", "name": "P", "review": {"@type": "Review", "author": "A"},
                 "aggregateRating": {"@type": "AggregateRating", "ratingValue": 4}})
        self.assertEqual(r["manquantes"], ["AggregateRating : ratingCount|reviewCount", "Review : reviewRating"])

    def test_video_fil_d_ariane_et_liste_d_elements_evalues(self):
        self.assertEqual(une({"@type": "Article", "headline": "H", "video": {"@type": "VideoObject", "name": "v"}})["manquantes"],
                         ["VideoObject : thumbnailUrl, uploadDate"])
        self.assertEqual(une({"@type": "WebPage", "breadcrumb": {"@type": "BreadcrumbList"}})["manquantes"],
                         ["BreadcrumbList : itemListElement"])
        # élément placé directement dans itemListElement, sans enveloppe ListItem
        self.assertEqual(une({"@type": "ItemList", "itemListElement": [{"@type": "Product", "name": "P"}]})["manquantes"],
                         ["Product : offers|review|aggregateRating"])
        # un fil d'Ariane complet et une vidéo complète ne produisent rien
        r = une({"@type": "WebPage", "breadcrumb": {"@type": "BreadcrumbList", "itemListElement": [{"@type": "ListItem", "position": 1}]},
                 "video": {"@type": "VideoObject", "name": "v", "thumbnailUrl": "u", "uploadDate": "2026-01-01"}})
        self.assertEqual(r, {"manquantes": [], "retires": []})

    # --- relecture 1 : @id résolus (M1) ----------------------------------------------------------------------------------

    def test_id_resolus_dans_le_graphe(self):
        graphe = {"@graph": [{"@type": "Product", "@id": "#p", "name": "X"},
                             {"@type": "Offer", "price": "10", "itemOffered": {"@id": "#p"}}]}
        self.assertEqual(une(graphe)["manquantes"], [])
        graphe = {"@graph": [{"@type": "Product", "@id": "#p", "name": "X"},
                             {"@type": "Review", "author": "A", "reviewRating": {"@type": "Rating", "ratingValue": 5},
                              "itemReviewed": {"@id": "#p"}}]}
        self.assertEqual(une(graphe)["manquantes"], [])
        # même @id décrit en deux nœuds : les propriétés se cumulent
        graphe = {"@graph": [{"@type": "Event", "@id": "#e", "name": "A"},
                             {"@id": "#e", "startDate": "2026-01-01", "location": {"@type": "Place", "name": "L", "address": "a"}}]}
        self.assertEqual(une(graphe)["manquantes"], [])
        # sans offre qui le désigne, le produit reste signalé
        graphe = {"@graph": [{"@type": "Product", "@id": "#p", "name": "X"}, {"@type": "Offer", "price": "10", "itemOffered": {"@id": "#autre"}}]}
        self.assertEqual(une(graphe)["manquantes"], ["Product : offers|review|aggregateRating"])

    # --- relecture 1 : types préfixés et sous-types (M2) -----------------------------------------------------------------

    def test_types_prefixes_et_sous_types(self):
        for t in ("https://schema.org/Event", "http://schema.org/Event", "schema:Event", "MusicEvent", "EducationEvent", "BusinessEvent"):
            self.assertEqual(une({"@type": t, "name": "E"})["manquantes"], [t.rsplit("/", 1)[-1].replace("schema:", "") + " : startDate, location"], t)
        for t in ("MobileApplication", "WebApplication", "schema:SoftwareApplication"):
            self.assertEqual(une({"@type": t, "name": "A"})["manquantes"], [t.replace("schema:", "") + " : offers, aggregateRating|review"], t)
        self.assertEqual(une({"@type": "schema:ClaimReview"})["retires"][0][:11], "ClaimReview")
        # CourseInstance est un sous-type d'Event en schema.org mais n'est pas un résultat « événement »
        self.assertEqual(une({"@type": "CourseInstance", "courseMode": "Onsite"})["manquantes"], [])

    # --- relecture 1 : sous-propriétés exigées par les pages Google (M3, M4) ---------------------------------------------

    def test_event_exige_location_name_et_address(self):
        base = {"@type": "Event", "name": "E", "startDate": "2026-11-05"}
        place = {"@type": "Place", "name": "Centre", "address": "1 rue de Paris"}
        self.assertEqual(une(dict(base, location=place))["manquantes"], [])
        self.assertEqual(une(dict(base, location={"@type": "Place", "name": "Centre"}))["manquantes"], ["Event : location.address"])
        self.assertEqual(une(dict(base, location={"@type": "Place", "address": "a"}))["manquantes"], ["Event : location.name"])
        self.assertEqual(une(dict(base, location={"@type": "Place"}))["manquantes"], ["Event : location.name, location.address"])
        # lieu en ligne, texte libre et renvoi non résolu : pas de jugement
        self.assertEqual(une(dict(base, location={"@type": "VirtualLocation", "url": "https://ex.fr/live"}))["manquantes"], [])
        self.assertEqual(une(dict(base, location="Paris"))["manquantes"], [])
        self.assertEqual(une(dict(base, location={"@id": "https://ex.fr/#lieu"}))["manquantes"], [])
        graphe = {"@graph": [dict(base, location={"@id": "#l"}), {"@type": "Place", "@id": "#l", "name": "L", "address": "a"}]}
        self.assertEqual(une(graphe)["manquantes"], [])
        graphe = {"@graph": [dict(base, location={"@id": "#l"}), {"@type": "Place", "@id": "#l", "name": "L"}]}
        self.assertEqual(une(graphe)["manquantes"], ["Event : location.address"])

    def test_application_exige_offers_price(self):
        base = {"@type": "SoftwareApplication", "name": "A", "aggregateRating": {"@type": "AggregateRating", "ratingValue": 4, "ratingCount": 3}}
        self.assertEqual(une(dict(base, offers={"@type": "Offer", "price": 0}))["manquantes"], [])
        self.assertEqual(une(dict(base, offers={"@type": "Offer", "price": "1.00", "priceCurrency": "EUR"}))["manquantes"], [])
        self.assertEqual(une(dict(base, offers={"@type": "Offer"}))["manquantes"], ["SoftwareApplication : offers.price"])
        self.assertEqual(une(dict(base, offers=[{"@type": "Offer"}, {"@type": "Offer", "price": 2}]))["manquantes"], [])

    # --- relecture 1 : prix démesurés ou non finis (M6) et espaces insécables (M7) ----------------------------------------

    def test_prix_demesures_ne_font_pas_perdre_les_autres_constats(self):
        bloc_event = {"@type": "Event", "name": "E"}
        for prix in (10 ** 400, float("inf"), float("nan"), "9" * 500, 1e300, "1e400"):
            r = res([bloc_event, self.offre(prix)], TEXTE)
            self.assertEqual(r["manquantes"], ["Event : startDate, location"], repr(prix)[:30])
            self.assertNotIn("incoherentes", r, repr(prix)[:30])

    def test_prix_avec_espaces_insecables(self):
        for texte in ("1&nbsp;490&nbsp;€", "1&#8239;490 €", "1\u00a0490\u00a0€", "1\u202f490 €", "1&thinsp;490 €"):
            r = une(self.offre("1490"), TEXTE + "<p>" + texte + "</p>")
            self.assertNotIn("incoherentes", r, texte)
        self.assertEqual(une(self.offre("1490"), TEXTE + "<p>1&nbsp;990&nbsp;€</p>")["incoherentes"], ["Offer : prix 1490 absent du texte visible"])

    def test_json_invalide_ou_exotique_sans_erreur(self):
        brut = ('<script type="application/ld+json">{invalide</script><script type="application/ld+json"></script>'
                '<script type="application/ld+json">[1, "a", null, {"@type": 5}]</script>'
                '<script type="application/ld+json">' + "[" * 3000 + "]" * 3000 + "</script>")
        self.assertEqual(res([], brut), {"manquantes": [], "retires": []})

    def test_resultat_deterministe_et_compte(self):
        blocs = [{"@type": "Event", "name": "A"}, {"@type": "Event", "name": "B"}]
        html = "".join('<script type="application/ld+json">{0}</script>'.format(json.dumps(b)) for b in blocs)
        r = ho.analyser(html, {}, "https://ex.fr/", modules=[("donnees_structurees", donnees_structurees)])["donnees_structurees"]
        self.assertEqual(r["manquantes"], [{"signature": "Event : startDate, location", "n": 2}])

    # --- valeurs contraires au texte visible : seulement le prix, seulement si la page a du texte --------------------------

    def offre(self, prix):
        return {"@type": "Product", "name": "Formation", "offers": {"@type": "Offer", "price": prix, "priceCurrency": "EUR"}}

    def test_prix_present_dans_le_texte_visible(self):
        for prix, texte in (("1200", "1 200 €"), (1200, "1200 EUR"), ("1200.00", "1.200,00 €"), ("49.9", "49,90 €"), ("49", "Tarif : 49 euros")):
            r = une(self.offre(prix), TEXTE + "<p>" + texte + "</p>")
            self.assertNotIn("incoherentes", r, texte)

    def test_prix_absent_du_texte_visible(self):
        r = une(self.offre("390"), TEXTE + "<p>Tarif : 490 € par personne</p>")
        self.assertEqual(r["incoherentes"], ["Offer : prix 390 absent du texte visible"])

    def test_prix_dans_un_element_masque_ou_un_script_ne_compte_pas(self):
        r = une(self.offre("390"), TEXTE + '<p hidden>390 €</p><script>var p = "390";</script>')
        self.assertEqual(r["incoherentes"], ["Offer : prix 390 absent du texte visible"])

    def test_prix_gratuit_ou_page_sans_texte_non_juges(self):
        self.assertNotIn("incoherentes", une(self.offre("0"), TEXTE))
        self.assertNotIn("incoherentes", une(self.offre("390")))  # aucune page à comparer
        self.assertNotIn("incoherentes", une(self.offre("sur devis"), TEXTE))

    # --- crawl complet -----------------------------------------------------------------------------------------------------

    def test_crawl_severites_et_domaine(self):
        blocs = [{"@context": "https://schema.org", "@type": "Event", "name": "Atelier"},
                 {"@context": "https://schema.org", "@type": "ClaimReview", "claimReviewed": "x"},
                 {"@context": "https://schema.org", "@type": "Course", "name": "C", "description": "D",
                  "hasCourseInstance": {"@type": "CourseInstance"}},
                 {"@context": "https://schema.org", "@type": "Course", "name": "Cours isolé sans description"}]
        scripts = "".join('<script type="application/ld+json">{0}</script>'.format(json.dumps(b)) for b in blocs)
        page = ('<html lang="fr"><head><title>Atelier de test des données structurées</title>' + scripts +
                '</head><body><main><h1>Atelier</h1><p>x</p></main></body></html>')
        issues = crawler({"/": (200, HTML, page)})
        req, sans = issues["jsonld_proprietes_requises"], issues["jsonld_type_sans_effet"]
        self.assertEqual((req["severity"], req["domaine"], req["examples"][0]["signature"]),
                         ("moyenne", "SEO technique", "Event : startDate, location"))
        cours = issues["jsonld_cours_incomplet"]  # moins de trois cours : basse, pas moyenne
        self.assertEqual((cours["severity"], cours["domaine"], cours["examples"][0]["signature"]),
                         ("basse", "SEO technique", "Course : description"))
        self.assertEqual((sans["severity"], sans["domaine"]), ("info", "SEO technique"))
        self.assertEqual(sorted(e["signature"].split(" ")[0] for e in sans["examples"]), ["ClaimReview", "Course"])

    def test_crawl_page_propre_sans_constat(self):
        bloc = {"@context": "https://schema.org", "@type": "Event", "name": "Atelier", "startDate": "2026-11-05T09:00:00+01:00",
                "location": {"@type": "Place", "name": "Centre", "address": "1 rue de Paris"}}
        page = ('<html lang="fr"><head><title>Atelier complet de test des données</title><script type="application/ld+json">'
                + json.dumps(bloc) + '</script></head><body><main><h1>Atelier</h1><p>x</p></main></body></html>')
        issues = crawler({"/": (200, HTML, page)})
        for cle in ("jsonld_proprietes_requises", "jsonld_type_sans_effet", "jsonld_prix_absent_du_texte"):
            self.assertNotIn(cle, issues)


if __name__ == "__main__":
    unittest.main()
