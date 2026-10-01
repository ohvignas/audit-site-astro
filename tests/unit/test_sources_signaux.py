import json
import pathlib
import sys
import tempfile
import unittest

RACINE = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RACINE / "plugins/audit-site-astro/skills/audit-complet/scripts"))
import fiches  # noqa: E402
import rapport_html  # noqa: E402
import signaux  # noqa: E402


def ecrire(d, rel, contenu):
    f = pathlib.Path(d, "data", rel)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(contenu), encoding="utf-8")


def issue(sev, domaine=None):
    it = {"label": "Libellé", "severity": sev, "count": 1, "examples": [{"signature": "x"}]}
    if domaine:
        it["domaine"] = domaine
    return it


class TestNouvellesSources(unittest.TestCase):
    def test_issues_de_toutes_les_sources(self):
        with tempfile.TemporaryDirectory() as d:
            ecrire(d, "crawl/issues.json", {"svg_non_masque": issue("moyenne", "Accessibilité"), "title_dup": issue("moyenne")})
            ecrire(d, "rendu/issues.json", {"axe:color-contrast": issue("haute"),
                                            "cookies_avant_consentement": issue("haute", "RGPD / traceurs")})
            ecrire(d, "domaine/issues.json", {"dmarc_absent": issue("basse")})
            ecrire(d, "terrain/issues.json", {"terrain_lcp": issue("haute")})
            vus = sorted((s["source"], s["cle"], s["domaine"]) for s in signaux.collecter(d))
        self.assertEqual(vus, [
            ("crawl", "svg_non_masque", "Accessibilité"), ("crawl", "title_dup", "SEO technique"),
            ("domaine", "dmarc_absent", "Sécurité"),
            ("rendu", "axe:color-contrast", "Accessibilité"), ("rendu", "cookies_avant_consentement", "RGPD / traceurs"),
            ("terrain", "terrain_lcp", "Performance")])

    def test_declencheurs_regex_des_nouvelles_sources(self):
        sig = {"source": "rendu", "cle": "axe:color-contrast"}
        self.assertTrue(fiches.correspond("rendu:^axe:color-contrast$", sig))
        self.assertFalse(fiches.correspond("rendu:^axe:color$", sig))
        self.assertFalse(fiches.correspond("domaine:^axe:color-contrast$", sig))
        self.assertTrue(fiches.correspond("domaine:^spf_(permissif|absent)$", {"source": "domaine", "cle": "spf_absent"}))
        self.assertTrue(fiches.correspond("terrain:^terrain_lcp$", {"source": "terrain", "cle": "terrain_lcp"}))

    def test_fiche_rgpd_valide(self):
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "rgpd-essai.md").write_text(
                '---\nid: rgpd-essai\ntitre: "Essai"\ndomaine: RGPD / traceurs\nseverite_type: haute\neffort: S\n'
                'declencheurs:\n  - "rendu:^cookies_avant_consentement$"\nsources:\n  - https://www.cnil.fr/\n---\n\n# Essai\n',
                encoding="utf-8")
            self.assertEqual([f["id"] for f in fiches.charger_fiches(d)], ["rgpd-essai"])

    def test_rgpd_compte_avec_la_securite(self):
        notes = rapport_html.notes_par_domaine([{"domaine": "RGPD / traceurs", "severite": "haute"}])
        self.assertEqual(notes["Sécurité"]["note"], 90)
        self.assertEqual(notes["Sécurité"]["inclut"], ["RGPD / traceurs"])


if __name__ == "__main__":
    unittest.main()
