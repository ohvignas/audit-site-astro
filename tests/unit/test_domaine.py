import contextlib
import io
import json
import pathlib
import re
import sys
import tempfile
import unittest
import urllib.error
from unittest import mock
from urllib.parse import parse_qs, urlparse

RACINE = pathlib.Path(__file__).resolve().parents[2]
SCRIPTS = RACINE / "plugins/audit-site-astro/skills/audit-complet/scripts"
sys.path.insert(0, str(SCRIPTS))
import domaine_check as dc  # noqa: E402
import fiches  # noqa: E402

# Aucun test ne fait de vraie requête Internet : tout passe par un résolveur DoH simulé (réponses application/dns-json enregistrées).
_GARDES = [mock.patch("urllib.request.urlopen", side_effect=AssertionError("requête réseau réelle interdite dans les tests unitaires")),
           mock.patch("urllib.request.OpenerDirector.open", side_effect=AssertionError("requête réseau réelle interdite")),
           mock.patch("socket.socket.connect", side_effect=AssertionError("connexion réseau réelle interdite"))]


def setUpModule():
    for g in _GARDES:
        g.start()


def tearDownModule():
    for g in _GARDES:
        g.stop()


SOA = {"Status": 0, "AD": False, "Answer": [{"type": 6, "data": "ns1.ex.fr. hostmaster.ex.fr. 1 2 3 4 5"}]}
VIDE = {"Status": 0, "AD": False, "Answer": []}


def txt(*valeurs):
    return {"Status": 0, "AD": False, "Answer": [{"type": 16, "data": '"{0}"'.format(v)} for v in valeurs]}


def mx(*cibles):
    return {"Status": 0, "Answer": [{"type": 15, "data": c} for c in cibles]}


def resolveur(table, appels=None):
    def q(nom, type_):
        if appels is not None:
            appels.append((nom, type_))
        return table.get((nom, type_), VIDE)
    return q


BASE = {("ex.fr", "SOA"): SOA, ("ex.fr", "MX"): mx("10 mx.ex.fr."),
        ("_dmarc.ex.fr", "TXT"): {"Status": 3}, ("www.ex.fr", "A"): {"Status": 0, "AD": False, "Answer": [{"type": 1, "data": "1.2.3.4"}]}}
SAIN = {**BASE, **{("ex.fr", "TXT"): txt("v=spf1 include:_spf.ex.fr -all"), ("_spf.ex.fr", "TXT"): txt("v=spf1 ip4:1.2.3.4 -all"),
                     ("_dmarc.ex.fr", "TXT"): txt("v=DMARC1; p=reject; rua=mailto:dmarc@ex.fr"),
                     ("ex.fr", "CAA"): {"Status": 0, "Answer": [{"type": 257, "data": '0 issue "letsencrypt.org"'}]},
                     ("www.ex.fr", "A"): {"Status": 0, "AD": True, "Answer": [{"type": 1, "data": "1.2.3.4"}]},
                     ("www.ex.fr", "AAAA"): {"Status": 0, "Answer": [{"type": 28, "data": "2001:db8::1"}]}}}


def sev(r):
    return {k: v["severity"] for k, v in r["issues"].items()}


class TestSpf(unittest.TestCase):
    def test_plus_all_et_dmarc_absent(self):
        r = dc.verifier("www.ex.fr", resolveur({**BASE, **{("ex.fr", "TXT"): txt("v=spf1 include:_spf.ex.fr +all")}}))
        self.assertEqual(r["domaine"], "ex.fr")
        self.assertEqual(sorted(r["issues"]), ["caa_absent", "dmarc_absent", "dnssec_absent", "ipv6_absent", "spf_permissif"])
        self.assertEqual(r["issues"]["spf_permissif"]["severity"], "haute")
        # domaine qui reçoit des e-mails (MX) : DMARC absent = moyenne
        self.assertEqual(r["issues"]["dmarc_absent"]["severity"], "moyenne")

    def test_point_d_interrogation_all_en_basse(self):
        r = dc.verifier("www.ex.fr", resolveur({**SAIN, **{("ex.fr", "TXT"): txt("v=spf1 mx ?all")}}))
        self.assertEqual(sev(r), {"spf_permissif": "basse"})

    def test_tilde_all_et_moins_all_sans_constat(self):
        for fin in ("~all", "-all"):
            with self.subTest(fin=fin):
                r = dc.verifier("www.ex.fr", resolveur({**SAIN, **{("ex.fr", "TXT"): txt("v=spf1 mx " + fin)}}))
                self.assertEqual(r["issues"], {})

    def test_plus_de_dix_requetes(self):
        table = {**SAIN, **{("ex.fr", "TXT"): txt("v=spf1 " + " ".join("include:i{0}.ex.fr".format(i) for i in range(11)) + " -all")}}
        for i in range(11):
            table[("i{0}.ex.fr".format(i), "TXT")] = txt("v=spf1 ip4:10.0.0.{0} -all".format(i))
        r = dc.verifier("www.ex.fr", resolveur(table))
        self.assertEqual(r["issues"]["spf_trop_de_requetes"]["examples"], [{"domaine": "ex.fr", "requetes": 11}])
        self.assertEqual(r["issues"]["spf_trop_de_requetes"]["severity"], "moyenne")

    def test_dix_requetes_pile_acceptees(self):
        table = {**SAIN, **{("ex.fr", "TXT"): txt("v=spf1 " + " ".join("include:i{0}.ex.fr".format(i) for i in range(10)) + " -all")}}
        for i in range(10):
            table[("i{0}.ex.fr".format(i), "TXT")] = txt("v=spf1 ip4:10.0.0.{0} -all".format(i))
        self.assertEqual(dc.verifier("www.ex.fr", resolveur(table))["issues"], {})

    def test_deux_enregistrements(self):
        r = dc.verifier("www.ex.fr", resolveur({**SAIN, **{("ex.fr", "TXT"): txt("v=spf1 -all", "v=spf1 mx -all")}}))
        self.assertEqual(sorted(r["issues"]), ["spf_multiple"])
        self.assertEqual(r["issues"]["spf_multiple"]["severity"], "moyenne")

    def test_texte_txt_decoupe_en_morceaux(self):
        # un TXT de plus de 255 octets est servi en plusieurs chaînes : « "v=spf1 mx" " +all" »
        brut = {"Status": 0, "Answer": [{"type": 16, "data": '"v=spf1 mx" " +all"'}]}
        r = dc.verifier("www.ex.fr", resolveur({**SAIN, **{("ex.fr", "TXT"): brut}}))
        self.assertEqual(sev(r), {"spf_permissif": "haute"})

    def test_txt_sans_guillemets_google(self):
        brut = {"Status": 0, "Answer": [{"type": 16, "data": "v=spf1 mx +all"}]}
        r = dc.verifier("www.ex.fr", resolveur({**SAIN, **{("ex.fr", "TXT"): brut}}))
        self.assertEqual(sev(r), {"spf_permissif": "haute"})

    def test_lookups_spf(self):
        table = {("ex.fr", "TXT"): txt("v=spf1 a mx include:a.ex.fr include:a.ex.fr exists:%{i}.x.ex.fr ip4:1.2.3.4 -all"),
                 ("a.ex.fr", "TXT"): txt("v=spf1 include:b.ex.fr -all"), ("b.ex.fr", "TXT"): txt("v=spf1 a -all")}
        # a, mx, 2 x (include a + include b + a), exists = 2 + 2 * 3 + 1
        self.assertEqual(dc.lookups_spf(resolveur(table), "ex.fr"), 9)

    def test_lookups_spf_boucle(self):
        table = {("ex.fr", "TXT"): txt("v=spf1 include:ex.fr -all")}
        self.assertEqual(dc.lookups_spf(resolveur(table), "ex.fr"), 1)


class TestInfra(unittest.TestCase):
    def test_domaine_sain(self):
        r = dc.verifier("www.ex.fr", resolveur(SAIN))
        self.assertEqual((r["statut"], r["issues"]), ("ok", {}))
        self.assertEqual(r["non_verifies"], [])

    def test_dmarc_none_en_info(self):
        r = dc.verifier("www.ex.fr", resolveur({**SAIN, **{("_dmarc.ex.fr", "TXT"): txt("v=DMARC1; p=none")}}))
        self.assertEqual(sev(r), {"dmarc_none": "info"})

    def test_nom_non_resolu_et_adresse_ip(self):
        self.assertEqual(dc.verifier("casse.cobaye.test", resolveur({}))["statut"], "non résolu")
        self.assertEqual(dc.verifier("127.0.0.1", resolveur({}))["statut"], "adresse IP")
        self.assertEqual(dc.verifier("::1", resolveur({}))["statut"], "adresse IP")

    def test_ecriture(self):
        with tempfile.TemporaryDirectory() as d:
            dc.ecrire(dc.verifier("www.ex.fr", resolveur(BASE)), d)
            issues = json.loads(pathlib.Path(d, "issues.json").read_text(encoding="utf-8"))
            md = pathlib.Path(d, "domaine.md").read_text(encoding="utf-8")
            brut = json.loads(pathlib.Path(d, "domaine.json").read_text(encoding="utf-8"))
        self.assertEqual(issues["caa_absent"]["domaine"], "Serveur / HTTP")
        self.assertEqual(issues["dmarc_absent"]["domaine"], "Sécurité")
        self.assertIn("# Domaine — ex.fr", md)
        self.assertEqual(brut["statut"], "ok")

    def test_aucune_adresse_email_en_sortie(self):
        r = dc.verifier("www.ex.fr", resolveur({**SAIN, **{("_dmarc.ex.fr", "TXT"): txt("v=DMARC1; p=none; rua=mailto:secret@ex.fr")}}))
        with tempfile.TemporaryDirectory() as d:
            dc.ecrire(r, d)
            sortie = "".join(p.read_text(encoding="utf-8") for p in pathlib.Path(d).iterdir())
        self.assertNotIn("@", sortie)
        self.assertNotIn("mailto", sortie)

    def test_sorties_deterministes(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            dc.ecrire(dc.verifier("www.ex.fr", resolveur(BASE)), a)
            dc.ecrire(dc.verifier("www.ex.fr", resolveur(BASE)), b)
            for nom in ("issues.json", "domaine.json", "domaine.md"):
                self.assertEqual(pathlib.Path(a, nom).read_bytes(), pathlib.Path(b, nom).read_bytes())

    def test_dnssec_via_le_soa_quand_le_site_est_en_cname(self):
        # www pointe vers un CDN non signé (AD absent sur l'A) mais la zone du domaine est signée (AD sur le SOA)
        table = {**SAIN, **{("ex.fr", "SOA"): {**SOA, "AD": True}, ("www.ex.fr", "A"): {"Status": 0, "AD": False, "Answer": []}}}
        self.assertEqual(dc.verifier("www.ex.fr", resolveur(table))["issues"], {})

    def test_chaque_requete_une_seule_fois(self):
        appels = []
        dc.verifier("www.ex.fr", resolveur(SAIN, appels))
        self.assertEqual(len(appels), len(set(appels)), appels)

    def test_nom_normalise(self):
        r = dc.verifier("WWW.EX.FR.", resolveur(SAIN))
        self.assertEqual((r["statut"], r["domaine"], r["issues"]), ("ok", "ex.fr", {}))

    def test_chaque_cle_a_une_fiche(self):
        cles = re.findall(r'ajouter\("([a-z0-9_]+)"', (SCRIPTS / "domaine_check.py").read_text(encoding="utf-8"))
        self.assertEqual(sorted(set(cles)), sorted(["spf_absent", "spf_multiple", "spf_permissif", "spf_trop_de_requetes", "dmarc_absent",
                                                    "dmarc_none", "caa_absent", "dnssec_absent", "ipv6_absent"]))
        self.assertEqual(len(set(cles)), 9)
        f = fiches.charger_fiches(SCRIPTS.parent / "references/fiches")
        self.assertEqual(fiches.associer([{"source": "domaine", "cle": c} for c in cles], f)[1], [])


class TestGravite(unittest.TestCase):
    """SPF et DMARC ne pèsent que si le domaine reçoit ou envoie des e-mails ; CAA, DNSSEC et IPv6 ne dépassent jamais « basse »."""

    SANS_MX = {k: v for k, v in BASE.items() if k != ("ex.fr", "MX")}

    def test_avec_mx_dmarc_absent_est_moyenne(self):
        r = dc.verifier("www.ex.fr", resolveur({**SAIN, **{("_dmarc.ex.fr", "TXT"): {"Status": 3}}}))
        self.assertEqual(sev(r), {"dmarc_absent": "moyenne"})

    def test_sans_mx_durcissement_en_basse(self):
        r = dc.verifier("www.ex.fr", resolveur(self.SANS_MX))
        self.assertEqual(sev(r), {"spf_absent": "basse", "dmarc_absent": "basse", "caa_absent": "info", "dnssec_absent": "info",
                                  "ipv6_absent": "info"})
        self.assertIn("durcissement", r["issues"]["dmarc_absent"]["label"])
        self.assertIn("durcissement", r["issues"]["spf_absent"]["label"])

    def test_avec_mx_spf_absent_est_moyenne(self):
        r = dc.verifier("www.ex.fr", resolveur({**SAIN, **{("ex.fr", "TXT"): VIDE}}))
        self.assertEqual(sev(r), {"spf_absent": "moyenne"})
        self.assertIn("MX", r["issues"]["spf_absent"]["label"])

    def test_sans_mx_spf_absent_reste_basse_et_dmarc_present(self):
        table = {**SAIN, **{("ex.fr", "MX"): VIDE, ("ex.fr", "TXT"): VIDE}}
        self.assertEqual(sev(dc.verifier("www.ex.fr", resolveur(table))), {"spf_absent": "basse"})

    def test_mx_nul_rfc7505_vaut_absence_de_mx(self):
        table = {**SAIN, **{("ex.fr", "MX"): mx("0 ."), ("_dmarc.ex.fr", "TXT"): {"Status": 3}}}
        self.assertEqual(sev(dc.verifier("www.ex.fr", resolveur(table))), {"dmarc_absent": "basse"})

    def test_caa_dnssec_ipv6_jamais_au_dessus_de_basse(self):
        for table in (BASE, self.SANS_MX, {}):
            r = dc.verifier("www.ex.fr", resolveur({**table, **{("ex.fr", "SOA"): SOA}}))
            for cle in ("caa_absent", "dnssec_absent", "ipv6_absent"):
                self.assertIn(r["issues"][cle]["severity"], ("info", "basse"), cle)
                self.assertEqual(r["issues"][cle]["domaine"], "Serveur / HTTP")

    def test_domaines_des_constats_email(self):
        r = dc.verifier("www.ex.fr", resolveur(BASE))
        for cle in ("spf_absent", "dmarc_absent"):
            self.assertEqual(r["issues"][cle]["domaine"], "Sécurité")


class TestDomaineOrganisationnel(unittest.TestCase):
    def test_sous_domaine_remonte_au_premier_soa(self):
        q = resolveur({("ex.fr", "SOA"): SOA})
        self.assertEqual(dc.domaine_organisationnel("beta.ex.fr", q), "ex.fr")
        self.assertEqual(dc.domaine_organisationnel("a.b.ex.fr", q), "ex.fr")
        self.assertEqual(dc.domaine_organisationnel("ex.fr", q), "ex.fr")

    def test_suffixe_multi_etiquettes(self):
        self.assertEqual(dc.domaine_organisationnel("www.ex.co.uk", resolveur({("ex.co.uk", "SOA"): SOA})), "ex.co.uk")

    def test_jamais_le_tld_seul(self):
        self.assertIsNone(dc.domaine_organisationnel("inconnu.fr", resolveur({("fr", "SOA"): SOA})))
        self.assertIsNone(dc.domaine_organisationnel("localhost", resolveur({})))

    def test_jamais_un_suffixe_public_multi_etiquettes(self):
        # co.uk a un SOA mais est un registre : x.inconnu.co.uk n'a pas de domaine enregistrable résolu
        self.assertIsNone(dc.domaine_organisationnel("x.inconnu.co.uk", resolveur({("co.uk", "SOA"): SOA})))
        self.assertEqual(dc.domaine_organisationnel("a.b.ex.com.au", resolveur({("ex.com.au", "SOA"): SOA, ("com.au", "SOA"): SOA})), "ex.com.au")

    def test_soa_par_cname_ignore(self):
        # www CNAME @ : la réponse SOA pour un nom contient le SOA d'un autre nom ; seul le SOA du nom demandé compte
        autre = {"Status": 0, "Answer": [{"name": "cdn.autre.net.", "type": 6, "data": "ns. h. 1 2 3 4 5"}]}
        self.assertIsNone(dc.domaine_organisationnel("www.ex.fr", resolveur({("ex.fr", "SOA"): autre})))
        propre = {"Status": 0, "Answer": [{"name": "Ex.Fr.", "type": 6, "data": "ns. h. 1 2 3 4 5"}]}
        self.assertEqual(dc.domaine_organisationnel("www.ex.fr", resolveur({("ex.fr", "SOA"): propre})), "ex.fr")

    def test_dmarc_cherche_sur_le_domaine_organisationnel(self):
        table = {**SAIN, **{("beta.ex.fr", "A"): {"Status": 0, "AD": True, "Answer": [{"type": 1, "data": "1.2.3.4"}]},
                            ("beta.ex.fr", "AAAA"): {"Status": 0, "Answer": [{"type": 28, "data": "2001:db8::2"}]}}}
        appels = []
        r = dc.verifier("beta.ex.fr", resolveur(table, appels))
        self.assertEqual((r["domaine"], r["issues"]), ("ex.fr", {}))
        # recherche DMARC : d'abord le nom exact, puis le domaine organisationnel
        dmarc = [n for n, t in appels if t == "TXT" and n.startswith("_dmarc.")]
        self.assertEqual(dmarc, ["_dmarc.beta.ex.fr", "_dmarc.ex.fr"])

    def test_zone_deleguee_dmarc_et_caa_remontent_au_domaine_a_deux_etiquettes(self):
        # sub.ex.fr a son propre SOA (zone déléguée) : DMARC et CAA publiés sur ex.fr restent trouvés
        table = {**SAIN, **{("sub.ex.fr", "SOA"): SOA, ("sub.ex.fr", "MX"): mx("10 mx.ex.fr."), ("sub.ex.fr", "TXT"): txt("v=spf1 mx -all"),
                            ("www.sub.ex.fr", "A"): SAIN[("www.ex.fr", "A")], ("www.sub.ex.fr", "AAAA"): SAIN[("www.ex.fr", "AAAA")]}}
        appels = []
        r = dc.verifier("www.sub.ex.fr", resolveur(table, appels))
        self.assertEqual((r["domaine"], r["issues"]), ("ex.fr", {}))
        self.assertEqual([n for n, t in appels if n.startswith("_dmarc.")], ["_dmarc.www.sub.ex.fr", "_dmarc.sub.ex.fr", "_dmarc.ex.fr"])

    def test_dmarc_propre_au_sous_domaine_prioritaire(self):
        table = {**SAIN, **{("_dmarc.beta.ex.fr", "TXT"): txt("v=DMARC1; p=none"), ("beta.ex.fr", "AAAA"): SAIN[("www.ex.fr", "AAAA")],
                            ("beta.ex.fr", "A"): SAIN[("www.ex.fr", "A")]}}
        self.assertEqual(sev(dc.verifier("beta.ex.fr", resolveur(table))), {"dmarc_none": "info"})

    def test_sp_du_domaine_organisationnel_s_applique_au_sous_domaine(self):
        table = {**SAIN, **{("_dmarc.ex.fr", "TXT"): txt("v=DMARC1; p=reject; sp=none"), ("beta.ex.fr", "AAAA"): SAIN[("www.ex.fr", "AAAA")],
                            ("beta.ex.fr", "A"): SAIN[("www.ex.fr", "A")]}}
        self.assertEqual(sev(dc.verifier("beta.ex.fr", resolveur(table))), {"dmarc_none": "info"})
        sain_apex = {**table, ("ex.fr", "AAAA"): SAIN[("www.ex.fr", "AAAA")], ("ex.fr", "A"): SAIN[("www.ex.fr", "A")]}
        self.assertEqual(dc.verifier("ex.fr", resolveur(sain_apex))["issues"], {})

    def test_caa_herite_du_domaine_organisationnel(self):
        # CAA publié sur ex.fr seulement : s'applique à www.ex.fr (remontée de l'arbre, RFC 8659)
        self.assertNotIn("caa_absent", dc.verifier("www.ex.fr", resolveur(SAIN))["issues"])


class TestPanneDoh(unittest.TestCase):
    @staticmethod
    def en_panne(*noms):
        """Résolveur sain sauf pour les (nom, type) listés, qui lèvent une erreur réseau."""
        def q(nom, type_):
            if (nom, type_) in noms:
                raise urllib.error.URLError("timeout")
            return SAIN.get((nom, type_), VIDE)
        return q

    def test_panne_totale(self):
        def q(nom, type_):
            raise OSError("réseau coupé")
        r = dc.verifier("www.ex.fr", q)
        self.assertEqual((r["statut"], r["domaine"], r["issues"]), ("non vérifié", None, {}))
        self.assertTrue(any("⚠️" in x and "non vérifié" in x for x in r["lignes"]), r["lignes"])

    def test_servfail_est_une_panne_pas_une_absence(self):
        r = dc.verifier("www.ex.fr", resolveur({**SAIN, **{("_dmarc.ex.fr", "TXT"): {"Status": 2}, ("_dmarc.www.ex.fr", "TXT"): {"Status": 2}}}))
        self.assertNotIn("dmarc_absent", r["issues"])
        self.assertEqual(r["non_verifies"], ["DMARC"])

    def test_panne_partielle_pas_de_faux_constat(self):
        r = dc.verifier("www.ex.fr", self.en_panne(("_dmarc.ex.fr", "TXT"), ("www.ex.fr", "AAAA"), ("ex.fr", "CAA")))
        self.assertEqual(r["statut"], "ok")
        self.assertEqual(r["issues"], {})
        self.assertEqual(r["non_verifies"], ["DMARC", "CAA", "IPv6"])
        for nom in r["non_verifies"]:
            self.assertTrue(any(x.startswith("- ⚠️ {0} : non vérifié".format(nom)) for x in r["lignes"]), (nom, r["lignes"]))
        self.assertFalse(any("✅" in x and "non vérifié" in x for x in r["lignes"]))

    def test_panne_ne_masque_pas_les_vrais_constats(self):
        table = {**BASE, **{("ex.fr", "TXT"): txt("v=spf1 mx +all")}}

        def q(nom, type_):
            if type_ == "CAA":
                raise TimeoutError()
            return table.get((nom, type_), VIDE)
        r = dc.verifier("www.ex.fr", q)
        self.assertIn("spf_permissif", r["issues"])
        self.assertNotIn("caa_absent", r["issues"])

    def test_panne_du_mx_ne_declasse_pas_en_info(self):
        r = dc.verifier("www.ex.fr", self.en_panne(("ex.fr", "MX"), ("_dmarc.ex.fr", "TXT")))
        self.assertIn("MX", r["non_verifies"])

    def test_ecriture_apres_panne(self):
        def q(nom, type_):
            raise OSError("réseau coupé")
        with tempfile.TemporaryDirectory() as d:
            dc.ecrire(dc.verifier("www.ex.fr", q), d)
            self.assertEqual(json.loads(pathlib.Path(d, "issues.json").read_text(encoding="utf-8")), {})
            md = pathlib.Path(d, "domaine.md").read_text(encoding="utf-8")
        self.assertIn("⚠️", md)
        self.assertIn("non vérifié", md)


class Reponse:
    def __init__(self, corps):
        self.corps = corps if isinstance(corps, bytes) else json.dumps(corps).encode("utf-8")

    def read(self, n=-1):
        return self.corps if n < 0 else self.corps[:n]

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def faux_ouvrir(journal, scenario):
    """Faux urlopen : scenario = {hote du résolveur: dict JSON | bytes | exception}."""
    def ouvrir(req, timeout=None):
        journal.append({"url": req.full_url, "accept": req.get_header("Accept"), "timeout": timeout})
        v = scenario[urlparse(req.full_url).hostname]
        if isinstance(v, Exception):
            raise v
        return Reponse(v)
    return ouvrir


CF, GG = "cloudflare-dns.com", "dns.google"
OK = {"Status": 0, "AD": True, "Answer": [{"type": 1, "data": "1.2.3.4"}]}


class TestTransport(unittest.TestCase):
    def transport(self, scenario, **kw):
        journal = []
        kw.setdefault("dormir", lambda s: None)
        return dc.transport_http(None, ouvrir=faux_ouvrir(journal, scenario), **kw), journal

    def test_resolveurs_par_defaut_cloudflare_puis_google(self):
        self.assertEqual(urlparse(dc.RESOLVEUR).hostname, CF)
        self.assertEqual([urlparse(r).hostname for r in dc.RESOLVEURS], [CF, GG])

    def test_requete_dns_json(self):
        q, journal = self.transport({CF: OK, GG: OK})
        self.assertEqual(q("www.ex.fr", "A"), OK)
        self.assertEqual(len(journal), 1)
        self.assertEqual(journal[0]["accept"], "application/dns-json")
        self.assertEqual(parse_qs(urlparse(journal[0]["url"]).query), {"name": ["www.ex.fr"], "type": ["A"]})
        self.assertEqual(urlparse(journal[0]["url"]).scheme, "https")

    def test_repli_sur_google_si_cloudflare_tombe(self):
        q, journal = self.transport({CF: urllib.error.URLError("timeout"), GG: OK})
        self.assertEqual(q("www.ex.fr", "A"), OK)
        self.assertEqual([urlparse(j["url"]).hostname for j in journal], [CF, GG])

    def test_repli_sur_reponse_invalide_et_servfail(self):
        for mauvais in (b"<html>captcha</html>", {"Status": 2}, [1, 2], b""):
            with self.subTest(mauvais=mauvais):
                q, journal = self.transport({CF: mauvais, GG: OK})
                self.assertEqual(q("www.ex.fr", "A"), OK)
                self.assertEqual(len(journal), 2)

    def test_nxdomain_est_une_reponse_valide(self):
        q, journal = self.transport({CF: {"Status": 3}, GG: OK})
        self.assertEqual(q("inconnu.ex.fr", "A"), {"Status": 3})
        self.assertEqual(len(journal), 1)

    def test_deux_resolveurs_en_panne(self):
        q, _ = self.transport({CF: OSError("x"), GG: urllib.error.HTTPError("u", 503, "x", {}, io.BytesIO())})
        with self.assertRaises(dc.DohErreur):
            q("www.ex.fr", "A")

    def test_resolveur_defaillant_abandonne_pour_la_suite(self):
        q, journal = self.transport({CF: OSError("x"), GG: OK})
        for _ in range(6):
            q("www.ex.fr", "A")
        # Cloudflare n'est plus sollicité après deux échecs : pas de timeouts répétés
        self.assertEqual(sum(1 for j in journal if urlparse(j["url"]).hostname == CF), 2)

    def test_delais_courts_au_plus_8_secondes(self):
        q, journal = self.transport({CF: OSError("x"), GG: OK}, delai=60)
        q("www.ex.fr", "A")
        self.assertTrue(journal and all(0 < j["timeout"] <= 8 for j in journal), journal)

    def test_budget_de_temps_global(self):
        t = [0.0]
        q, journal = self.transport({CF: OK, GG: OK}, budget=10, horloge=lambda: t[0])
        q("a.ex.fr", "A")
        t[0] = 11.0
        with self.assertRaises(dc.DohErreur):
            q("b.ex.fr", "A")
        self.assertEqual(len(journal), 1)

    def test_timeout_borne_par_le_budget_restant(self):
        t = [0.0]
        q, journal = self.transport({CF: OK, GG: OK}, budget=10, horloge=lambda: t[0])
        t[0] = 7.0
        q("a.ex.fr", "A")
        self.assertLessEqual(journal[0]["timeout"], 3.0 + 1e-9)

    def test_pause_entre_requetes(self):
        pauses = []
        q, _ = self.transport({CF: OK}, dormir=pauses.append, pause=0.25)
        q("a.ex.fr", "A")
        q("b.ex.fr", "A")
        self.assertEqual(pauses, [0.25])

    def test_resolveur_personnalise_uniquement(self):
        journal = []
        q = dc.transport_http(["https://doh.perso.test/dns-query"], ouvrir=faux_ouvrir(journal, {"doh.perso.test": OK}), dormir=lambda s: None)
        q("www.ex.fr", "A")
        self.assertEqual([urlparse(j["url"]).hostname for j in journal], ["doh.perso.test"])

    def test_schemas_refuses(self):
        for mauvais in ("file:///etc/passwd", "ftp://x/y", "javascript:alert(1)", "doh.perso.test", "http://doh.perso.test/dns-query"):
            with self.subTest(mauvais=mauvais):
                with self.assertRaises(ValueError):
                    dc.transport_http([mauvais])

    def test_reponse_trop_volumineuse_ignoree(self):
        q, journal = self.transport({CF: b"x" * 2_000_000, GG: OK})
        self.assertEqual(q("www.ex.fr", "A"), OK)

    def test_verifier_avec_transport_bout_en_bout(self):
        """Transport HTTP simulé de bout en bout : Cloudflare en panne, Google répond ; aucun accès réseau réel."""
        def corps(nom, type_):
            return SAIN.get((nom, type_), VIDE)
        journal = []

        def ouvrir(req, timeout=None):
            journal.append(urlparse(req.full_url).hostname)
            if urlparse(req.full_url).hostname == CF:
                raise urllib.error.URLError("timeout")
            qs = parse_qs(urlparse(req.full_url).query)
            return Reponse(corps(qs["name"][0], qs["type"][0]))
        q = dc.transport_http(None, ouvrir=ouvrir, dormir=lambda s: None)
        r = dc.verifier("www.ex.fr", q)
        self.assertEqual((r["statut"], r["issues"], r["non_verifies"]), ("ok", {}, []))
        self.assertIn(GG, journal)


class TestCli(unittest.TestCase):
    def setUp(self):
        sortie = contextlib.redirect_stdout(io.StringIO())
        sortie.__enter__()
        self.addCleanup(sortie.__exit__, None, None, None)

    def test_main_ecrit_les_trois_fichiers_code_0(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(dc.main(["https://www.ex.fr/page?a=1", "--out", d], transport=resolveur(BASE)), 0)
            self.assertEqual(sorted(p.name for p in pathlib.Path(d).iterdir()), ["domaine.json", "domaine.md", "issues.json"])

    def test_main_adresse_ip_et_nom_non_resolu_code_0(self):
        for url in ("http://127.0.0.1:8080/", "https://casse.cobaye.test/", "http://[::1]:4321/"):
            with self.subTest(url=url), tempfile.TemporaryDirectory() as d:
                self.assertEqual(dc.main([url, "--out", d], transport=resolveur({})), 0)
                self.assertEqual(json.loads(pathlib.Path(d, "issues.json").read_text(encoding="utf-8")), {})
                self.assertIn("⏭️", pathlib.Path(d, "domaine.md").read_text(encoding="utf-8"))

    def test_main_panne_doh_code_0(self):
        def q(nom, type_):
            raise OSError("réseau coupé")
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(dc.main(["https://www.ex.fr/", "--out", d], transport=q), 0)
            self.assertIn("non vérifié", pathlib.Path(d, "domaine.md").read_text(encoding="utf-8"))

    def test_main_sans_schema(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(dc.main(["www.ex.fr", "--out", d], transport=resolveur(SAIN)), 0)
            self.assertIn("# Domaine — ex.fr", pathlib.Path(d, "domaine.md").read_text(encoding="utf-8"))

    def test_resolveur_non_https_refuse(self):
        with tempfile.TemporaryDirectory() as d, mock.patch("sys.stderr", new=io.StringIO()):
            with self.assertRaises(SystemExit):
                dc.main(["https://www.ex.fr/", "--out", d, "--resolveur", "file:///etc/passwd"])

    def test_aucun_secret_de_resolveur_en_sortie(self):
        with tempfile.TemporaryDirectory() as d:
            dc.main(["https://www.ex.fr/", "--out", d], transport=resolveur(BASE))
            sortie = "".join(p.read_text(encoding="utf-8") for p in pathlib.Path(d).iterdir())
        self.assertNotIn("http", sortie)


class TestPlateformesPartagees(unittest.TestCase):
    """Sous-domaine d'un suffixe PRIVÉ de la PSL : le DNS est celui de la plateforme, aucun constat."""

    HOTES = ("site.vercel.app", "foo.netlify.app", "x.github.io", "a.pages.dev", "app.herokuapp.com", "a.b.github.io")

    def test_statut_et_aucun_constat(self):
        for hote in self.HOTES:
            with self.subTest(hote=hote):
                appels = []
                r = dc.verifier(hote, resolveur({}, appels))
                self.assertEqual((r["statut"], r["issues"], r["non_verifies"]), ("plateforme partagée", {}, []))
                self.assertEqual(appels, [], "aucune requête DNS pour une plateforme partagée")
                self.assertTrue(any(x.startswith("- ⏭️") for x in r["lignes"]), r["lignes"])

    def test_meme_avec_des_enregistrements_publies_par_la_plateforme(self):
        # ni un DMARC p=none, ni l'absence de DNSSEC de la plateforme ne sont imputés au propriétaire du site
        table = {("vercel.app", "SOA"): SOA, ("_dmarc.vercel.app", "TXT"): txt("v=DMARC1; p=none"), ("vercel.app", "MX"): mx("10 mx.v.app.")}
        r = dc.verifier("site.vercel.app", resolveur(table))
        self.assertEqual((r["statut"], r["issues"]), ("plateforme partagée", {}))

    def test_ligne_explicative(self):
        r = dc.verifier("site.vercel.app", resolveur({}))
        ligne = " ".join(r["lignes"])
        self.assertIn("vercel.app", ligne)
        self.assertIn("plateforme", ligne)
        self.assertIn("domaine personnalisé", ligne)
        self.assertEqual(r["suffixe"], "vercel.app")

    def test_ecriture_et_cli(self):
        with tempfile.TemporaryDirectory() as d:
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(dc.main(["https://site.vercel.app/", "--out", d], transport=resolveur({})), 0)
            self.assertEqual(json.loads(pathlib.Path(d, "issues.json").read_text(encoding="utf-8")), {})
            md = pathlib.Path(d, "domaine.md").read_text(encoding="utf-8")
        self.assertIn("# Domaine — site.vercel.app", md)
        self.assertIn("⏭️", md)

    def test_domaine_personnalise_non_concerne(self):
        self.assertEqual(dc.verifier("www.ex.fr", resolveur(SAIN))["statut"], "ok")

    def test_domaine_enregistrable_sous_suffixe_multi_etiquettes(self):
        table = {**SAIN, ("ex.co.uk", "SOA"): SOA, ("ex.co.uk", "MX"): mx("10 mx.ex.fr.")}
        r = dc.verifier("www.ex.co.uk", resolveur(table))
        self.assertEqual(r["domaine"], "ex.co.uk")


class TestSpfExact(unittest.TestCase):
    """RFC 7208 : le premier « all » l'emporte ; redirect= et include: sont suivis pour trouver un « +all » hérité."""

    def r(self, table_spf):
        return dc.verifier("www.ex.fr", resolveur({**SAIN, **{k: txt(v) for k, v in table_spf.items()}}))

    def test_premier_all_gagne_moins_all_puis_plus_all(self):
        self.assertEqual(self.r({("ex.fr", "TXT"): "v=spf1 mx -all +all"})["issues"], {})

    def test_premier_all_gagne_plus_all_puis_moins_all(self):
        r = self.r({("ex.fr", "TXT"): "v=spf1 mx +all -all"})
        self.assertEqual(sev(r), {"spf_permissif": "haute"})

    def test_all_nu_est_plus_all_et_tilde_puis_plus_all_sans_constat(self):
        self.assertEqual(sev(self.r({("ex.fr", "TXT"): "v=spf1 mx all"})), {"spf_permissif": "haute"})
        self.assertEqual(self.r({("ex.fr", "TXT"): "v=spf1 mx ~all +all"})["issues"], {})

    def test_redirect_vers_plus_all(self):
        r = self.r({("ex.fr", "TXT"): "v=spf1 redirect=_s.ex.fr", ("_s.ex.fr", "TXT"): "v=spf1 +all"})
        self.assertEqual(sev(r), {"spf_permissif": "haute"})
        self.assertEqual(r["issues"]["spf_permissif"]["examples"][0]["via"], "_s.ex.fr")

    def test_chaine_de_redirect(self):
        r = self.r({("ex.fr", "TXT"): "v=spf1 redirect=_a.ex.fr", ("_a.ex.fr", "TXT"): "v=spf1 redirect=_b.ex.fr",
                    ("_b.ex.fr", "TXT"): "v=spf1 redirect=_c.ex.fr", ("_c.ex.fr", "TXT"): "v=spf1 ip4:1.2.3.4 +all"})
        self.assertEqual(sev(r), {"spf_permissif": "haute"})

    def test_redirect_vers_moins_all_ou_point_d_interrogation(self):
        self.assertEqual(self.r({("ex.fr", "TXT"): "v=spf1 redirect=_s.ex.fr", ("_s.ex.fr", "TXT"): "v=spf1 -all"})["issues"], {})
        r = self.r({("ex.fr", "TXT"): "v=spf1 redirect=_s.ex.fr", ("_s.ex.fr", "TXT"): "v=spf1 ?all"})
        self.assertEqual(sev(r), {"spf_permissif": "basse"})

    def test_redirect_ignore_quand_un_all_est_present(self):
        r = self.r({("ex.fr", "TXT"): "v=spf1 -all redirect=_s.ex.fr", ("_s.ex.fr", "TXT"): "v=spf1 +all"})
        self.assertEqual(r["issues"], {})

    def test_include_vers_plus_all(self):
        r = self.r({("ex.fr", "TXT"): "v=spf1 include:_s.ex.fr -all", ("_s.ex.fr", "TXT"): "v=spf1 +all"})
        self.assertEqual(sev(r), {"spf_permissif": "haute"})
        self.assertEqual(r["issues"]["spf_permissif"]["examples"][0]["via"], "_s.ex.fr")

    def test_include_imbrique_vers_plus_all(self):
        r = self.r({("ex.fr", "TXT"): "v=spf1 include:_a.ex.fr -all", ("_a.ex.fr", "TXT"): "v=spf1 include:_b.ex.fr ~all",
                    ("_b.ex.fr", "TXT"): "v=spf1 ip4:1.2.3.4 all"})
        self.assertEqual(sev(r), {"spf_permissif": "haute"})

    def test_include_qui_ne_correspond_pas_pour_toute_adresse(self):
        # ?all, ~all, -all dans l'include : pas de correspondance générale, le « -all » de l'enregistrement racine s'applique
        for fin in ("?all", "~all", "-all"):
            with self.subTest(fin=fin):
                r = self.r({("ex.fr", "TXT"): "v=spf1 include:_s.ex.fr -all", ("_s.ex.fr", "TXT"): "v=spf1 ip4:1.2.3.4 " + fin})
                self.assertEqual(r["issues"], {})

    def test_include_avec_qualificateur_moins_vers_plus_all_n_est_pas_permissif(self):
        r = self.r({("ex.fr", "TXT"): "v=spf1 -include:_s.ex.fr +all", ("_s.ex.fr", "TXT"): "v=spf1 +all"})
        self.assertEqual(r["issues"], {})

    def test_boucle_include_et_redirect(self):
        for racine in ("v=spf1 include:ex.fr -all", "v=spf1 redirect=ex.fr", "v=spf1 redirect=_a.ex.fr"):
            with self.subTest(racine=racine):
                r = self.r({("ex.fr", "TXT"): racine, ("_a.ex.fr", "TXT"): "v=spf1 redirect=ex.fr"})
                self.assertNotIn("spf_permissif", r["issues"])

    def test_profondeur_bornee_par_la_limite_des_requetes(self):
        table = {("ex.fr", "TXT"): "v=spf1 redirect=r0.ex.fr"}
        for i in range(40):
            table[("r{0}.ex.fr".format(i), "TXT")] = "v=spf1 redirect=r{0}.ex.fr".format(i + 1)
        table[("r40.ex.fr", "TXT")] = "v=spf1 +all"
        appels = []
        table = {**SAIN, **{k: txt(v) for k, v in table.items()}}
        r = dc.verifier("www.ex.fr", resolveur(table, appels))
        self.assertNotIn("spf_permissif", r["issues"])  # au-delà de 10 requêtes l'évaluation s'arrête (PermError)
        self.assertLess(len([a for a in appels if a[1] == "TXT" and a[0].startswith("r")]), 15)

    def test_redirect_non_compte_quand_un_all_est_present(self):
        q = resolveur({("ex.fr", "TXT"): txt("v=spf1 -all redirect=_s.ex.fr"), ("_s.ex.fr", "TXT"): txt("v=spf1 include:a.ex.fr -all")})
        self.assertEqual(dc.lookups_spf(q, "ex.fr"), 0)

    def test_termes_apres_le_premier_all_non_comptes(self):
        q = resolveur({("ex.fr", "TXT"): txt("v=spf1 a -all include:a.ex.fr mx")})
        self.assertEqual(dc.lookups_spf(q, "ex.fr"), 1)

    def test_redirect_compte_sans_all(self):
        q = resolveur({("ex.fr", "TXT"): txt("v=spf1 mx redirect=_s.ex.fr"), ("_s.ex.fr", "TXT"): txt("v=spf1 a -all")})
        self.assertEqual(dc.lookups_spf(q, "ex.fr"), 3)

    def test_panne_sur_include_garde_le_constat_trouve(self):
        def q(nom, type_):
            if nom == "_x.ex.fr":
                raise OSError("réseau")
            return {**SAIN, ("ex.fr", "TXT"): txt("v=spf1 include:_x.ex.fr +all")}.get((nom, type_), VIDE)
        r = dc.verifier("www.ex.fr", q)
        self.assertEqual(sev(r), {"spf_permissif": "haute"})
        self.assertTrue(any("+all" in x for x in r["lignes"]))
        self.assertFalse(any(x.startswith("- ⚠️ SPF : non vérifié") for x in r["lignes"]))

    def test_panne_sur_include_sans_constat_est_non_verifie(self):
        def q(nom, type_):
            if nom == "_x.ex.fr":
                raise OSError("réseau")
            return {**SAIN, ("ex.fr", "TXT"): txt("v=spf1 include:_x.ex.fr -all")}.get((nom, type_), VIDE)
        r = dc.verifier("www.ex.fr", q)
        self.assertEqual((r["issues"], r["non_verifies"]), ({}, ["SPF"]))

    def test_libelle_spf_multiple(self):
        r = dc.verifier("www.ex.fr", resolveur({**SAIN, **{("ex.fr", "TXT"): txt("v=spf1 -all", "v=spf1 mx -all")}}))
        self.assertIn("PermError", r["issues"]["spf_multiple"]["label"])


class TestDetails(unittest.TestCase):
    def test_nom_invalide_sans_requete(self):
        for hote in (("a" * 64) + ".ex.fr", "a..ex.fr", ".".join(["abcdefghi"] * 30)):
            with self.subTest(hote=hote[:20]):
                appels = []
                r = dc.verifier(hote, resolveur(SAIN, appels))
                self.assertEqual((r["statut"], r["issues"]), ("nom invalide", {}))
                self.assertEqual(appels, [])

    def test_nombre_de_noms_interroges_borne(self):
        hote = ".".join(["a"] * 100) + ".ex.fr"
        appels = []
        r = dc.verifier(hote, resolveur({**SAIN}, appels))
        self.assertEqual(r["statut"], "ok")
        dmarc = [n for n, t in appels if n.startswith("_dmarc.")]
        self.assertLessEqual(len(dmarc), 8, dmarc)
        self.assertEqual(dmarc[0], "_dmarc." + hote)
        self.assertEqual(dmarc[-1], "_dmarc.ex.fr")
        self.assertLessEqual(len(appels), 40, len(appels))

    def test_redirection_de_resolveur_refusee(self):
        import urllib.request
        h = dc._SansRedirection()
        req = urllib.request.Request("https://cloudflare-dns.com/dns-query?name=a&type=A")
        for code in (301, 302, 307, 308):
            self.assertIsNone(h.redirect_request(req, io.BytesIO(), code, "Moved", {}, "http://evil.test/x"), code)

    def test_opener_par_defaut_sans_redirection(self):
        self.assertTrue(any(isinstance(h, dc._SansRedirection) for h in dc._ouvreur().handlers))

    def test_dmarc_sans_p_est_invalide_pas_en_place(self):
        r = dc.verifier("www.ex.fr", resolveur({**SAIN, **{("_dmarc.ex.fr", "TXT"): txt("v=DMARC1; rua=mailto:x@ex.fr")}}))
        ligne = [x for x in r["lignes"] if "DMARC" in x]
        self.assertEqual(len(ligne), 1, ligne)
        self.assertTrue(ligne[0].startswith("- ⚠️ DMARC"), ligne)
        self.assertIn("invalide", ligne[0])
        self.assertNotIn("✅", ligne[0])
        self.assertEqual(r["issues"], {})

    def test_dmarc_politique_illisible(self):
        r = dc.verifier("www.ex.fr", resolveur({**SAIN, **{("_dmarc.ex.fr", "TXT"): txt("v=DMARC1; p=bidon")}}))
        self.assertTrue(any(x.startswith("- ⚠️ DMARC") and "invalide" in x for x in r["lignes"]), r["lignes"])

    def test_dmarc_sp_dans_le_libelle(self):
        table = {**SAIN, **{("_dmarc.ex.fr", "TXT"): txt("v=DMARC1; p=reject; sp=none"), ("beta.ex.fr", "AAAA"): SAIN[("www.ex.fr", "AAAA")],
                            ("beta.ex.fr", "A"): SAIN[("www.ex.fr", "A")]}}
        r = dc.verifier("beta.ex.fr", resolveur(table))
        self.assertIn("sp=", r["issues"]["dmarc_none"]["label"])

    def test_dmarc_plusieurs_enregistrements(self):
        r = dc.verifier("www.ex.fr", resolveur({**SAIN, **{("_dmarc.ex.fr", "TXT"): txt("v=DMARC1; p=reject", "v=DMARC1; p=none")}}))
        self.assertIn("plusieurs", r["issues"]["dmarc_absent"]["label"])

    def test_caa_iodef_seul_n_est_pas_en_place(self):
        caa = {"Status": 0, "Answer": [{"type": 257, "data": '0 iodef "mailto:secu@ex.fr"'}]}
        r = dc.verifier("www.ex.fr", resolveur({**SAIN, ("ex.fr", "CAA"): caa}))
        self.assertEqual(sev(r), {"caa_absent": "info"})
        ligne = [x for x in r["lignes"] if "CAA" in x]
        self.assertTrue(ligne[0].startswith("- ⚠️"), ligne)
        self.assertIn("issue", ligne[0])
        with tempfile.TemporaryDirectory() as d:
            dc.ecrire(r, d)
            self.assertNotIn("secu@", "".join(p.read_text(encoding="utf-8") for p in pathlib.Path(d).iterdir()))

    def test_caa_issue_ou_issuewild_en_place(self):
        for data in ('0 issue "letsencrypt.org"', '0 issuewild "letsencrypt.org"', '128 ISSUE "pki.goog"', '0 issue ";"'):
            with self.subTest(data=data):
                caa = {"Status": 0, "Answer": [{"type": 257, "data": data}]}
                self.assertNotIn("caa_absent", dc.verifier("www.ex.fr", resolveur({**SAIN, ("ex.fr", "CAA"): caa}))["issues"])

    def test_ipv6_apex_et_www(self):
        a = {"Status": 0, "AD": True, "Answer": [{"type": 1, "data": "1.2.3.4"}]}
        aaaa = {"Status": 0, "Answer": [{"type": 28, "data": "2001:db8::1"}]}
        base = {**SAIN, ("ex.fr", "A"): a, ("www.ex.fr", "A"): a}
        # apex en IPv6, www sans AAAA (alors qu'il a un A) : le défaut est signalé sur www, nommé
        r = dc.verifier("ex.fr", resolveur({**base, ("ex.fr", "AAAA"): aaaa, ("www.ex.fr", "AAAA"): VIDE}))
        self.assertEqual(sev(r), {"ipv6_absent": "info"})
        self.assertIn("www.ex.fr", r["issues"]["ipv6_absent"]["label"])
        self.assertEqual(r["issues"]["ipv6_absent"]["examples"][0]["sans_ipv6"], ["www.ex.fr"])
        # l'inverse : URL en www, apex sans AAAA
        r = dc.verifier("www.ex.fr", resolveur({**base, ("ex.fr", "AAAA"): VIDE, ("www.ex.fr", "AAAA"): aaaa}))
        self.assertEqual(r["issues"]["ipv6_absent"]["examples"][0]["sans_ipv6"], ["ex.fr"])
        # les deux
        r = dc.verifier("www.ex.fr", resolveur({**base, ("ex.fr", "AAAA"): VIDE, ("www.ex.fr", "AAAA"): VIDE}))
        self.assertEqual(r["issues"]["ipv6_absent"]["examples"][0]["sans_ipv6"], ["www.ex.fr", "ex.fr"])
        # les deux en IPv6 : rien
        r = dc.verifier("www.ex.fr", resolveur({**base, ("ex.fr", "AAAA"): aaaa, ("www.ex.fr", "AAAA"): aaaa}))
        self.assertEqual(r["issues"], {})

    def test_ipv6_nom_jumeau_inexistant_ignore(self):
        # apex sans enregistrement A (le jumeau www n'existe pas) : seul le nom audité compte
        a = {"Status": 0, "AD": True, "Answer": [{"type": 1, "data": "1.2.3.4"}]}
        aaaa = {"Status": 0, "Answer": [{"type": 28, "data": "2001:db8::1"}]}
        r = dc.verifier("ex.fr", resolveur({**SAIN, ("ex.fr", "A"): a, ("ex.fr", "AAAA"): aaaa}))
        self.assertEqual(r["issues"], {})

    def test_ipv6_sous_domaine_autre_que_www_un_seul_nom(self):
        appels = []
        dc.verifier("beta.ex.fr", resolveur(SAIN, appels))
        self.assertEqual([n for n, t in appels if t == "AAAA"], ["beta.ex.fr"])

    def test_libelle_dnssec_mentionne_la_ds(self):
        r = dc.verifier("www.ex.fr", resolveur(BASE))
        self.assertIn("DS", r["issues"]["dnssec_absent"]["label"])

    def test_aide_resolveur_mentionne_dnssec_et_validation(self):
        with mock.patch("sys.stdout", new=io.StringIO()) as sortie:
            with self.assertRaises(SystemExit):
                dc.main(["--help"])
        self.assertIn("valid", sortie.getvalue())


if __name__ == "__main__":
    unittest.main()
