"""Chaîne complète : corrections.py (vraies fiches) puis rapport_html.py sur la fixture d'audit, via subprocess comme la CLI."""
import html
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

RACINE = pathlib.Path(__file__).resolve().parents[2]
SCRIPTS = RACINE / "plugins/audit-site-astro/skills/audit-complet/scripts"
FICHES_REELLES = RACINE / "plugins/audit-site-astro/skills/audit-complet/references/fiches"
FIXTURE_AUDIT = RACINE / "tests/unit/fixtures/audit-exemple"


def lancer(script, *args):
    return subprocess.run([sys.executable, str(SCRIPTS / script)] + [str(a) for a in args], capture_output=True, text=True)


class ChaineBase(unittest.TestCase):
    def setUp(self):
        env = mock.patch.dict(os.environ)  # hermétique : ni AUDIT_DANS_DOCKER ni autre variable héritée ne change le LISEZ-MOI
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop("AUDIT_DANS_DOCKER", None)
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.audit = pathlib.Path(self._tmp.name, "2026-09-30")
        shutil.copytree(FIXTURE_AUDIT, self.audit)

    def corrections(self):
        r = lancer("corrections.py", self.audit, "--fiches", FICHES_REELLES)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r

    def rapport(self):
        r = lancer("rapport_html.py", self.audit)
        self.assertEqual(r.returncode, 0, r.stderr)
        return (self.audit / "RAPPORT.html").read_text(encoding="utf-8"), r


class TestChaineCorrections(ChaineBase):
    def setUp(self):
        super().setUp()
        self.corrections()
        self.h, self.r = self.rapport()
        self.dossier = self.audit / "CORRECTIONS"
        self.index = json.loads((self.dossier / "index.json").read_text(encoding="utf-8"))

    def test_l_index_a_des_corrections(self):
        self.assertGreaterEqual(len(self.index["corrections"]), 1)

    def test_tableau_du_plan_de_correction(self):
        self.assertIn("Plan de correction", self.h)
        self.assertRegex(self.h, r"<caption class=\"sr\">Plan de correction")
        for c in self.index["corrections"]:
            self.assertIn(f'<td class="num"><a href="#correction-{c["num"]}">{c["num"]}</a></td>', self.h)
            self.assertIn(f"<td>{html.escape(c['titre'])}</td>", self.h)

    def test_au_moins_un_lien_comment_corriger_vers_une_ancre_existante(self):
        ids = set(re.findall(r'\bid="([^"]*)"', self.h))
        liens = re.findall(r"Comment corriger → (.*?)</span>", self.h)
        self.assertGreaterEqual(len(liens), 1, "aucun lien « Comment corriger → »")
        for bloc in liens:
            cibles = re.findall(r'<a href="#(correction-[0-9]{2,3})">', bloc)
            self.assertTrue(cibles, bloc)
            for cible in cibles:
                self.assertIn(cible, ids)

    def test_annexe_avec_le_titre_de_chaque_fiche(self):
        self.assertIn("Guides de correction", self.h)
        for c in self.index["corrections"]:
            n = c["num"]
            self.assertIn(f'id="correction-{n}"', self.h)
            article = self.h[self.h.index(f'id="correction-{n}"'):]
            article = article[:article.index("</article>")]
            self.assertIn(f"Guide {n}", article)
            # le titre de la fiche (h1 du corps ou, à défaut, celui de l'index) figure dans son article
            fiche = (self.dossier / c["fichier"]).read_text(encoding="utf-8")
            titre_fiche = re.search(r"^#\s+(.+?)\s*#*\s*$", fiche, re.M)
            attendu = html.escape(titre_fiche.group(1)) if titre_fiche else html.escape(c["titre"])
            self.assertIn(attendu, article)

    def test_sommaire_de_l_annexe_couvre_toutes_les_fiches(self):
        for c in self.index["corrections"]:
            self.assertIn(f'<li><a href="#correction-{c["num"]}">{c["num"]} — {html.escape(c["titre"])}</a></li>', self.h)

    def test_aucun_script(self):
        self.assertNotIn("<script", self.h.lower())

    def test_tous_les_liens_internes_pointent_vers_un_id_existant(self):
        ids = re.findall(r'\bid="([^"]*)"', self.h)
        self.assertEqual(len(ids), len(set(ids)), "ids en double")
        cibles = re.findall(r'href="#([^"]*)"', self.h)
        self.assertGreaterEqual(len(cibles), 2 * len(self.index["corrections"]))
        for cible in cibles:
            self.assertIn(cible, ids, f'href="#{cible}" sans id correspondant')

    def test_mention_du_dossier_et_aucun_avertissement(self):
        self.assertIn("Le dossier CORRECTIONS/ contient ces mêmes fiches", self.h)
        self.assertEqual(self.r.stderr, "")


class TestChaineDossierConserve(ChaineBase):
    """Cas M4 : CORRECTIONS/.garder ou suivi commencé -> le rapport suit CORRECTIONS-<horodatage>/, pas l'ancien plan."""

    def preparer_ancien_plan(self):
        self.corrections()
        ancien = self.audit / "CORRECTIONS"
        idx = json.loads((ancien / "index.json").read_text(encoding="utf-8"))
        idx["corrections"] = idx["corrections"][:1]
        idx["corrections"][0]["titre"] = "TITRE DE L ANCIEN PLAN"
        (ancien / "index.json").write_text(json.dumps(idx, ensure_ascii=False), encoding="utf-8")
        return ancien, idx

    def verifier_suit_le_nouveau(self, ancien):
        nom = (self.audit / "data/corrections-dossier.txt").read_text(encoding="utf-8")
        self.assertRegex(nom, r"^CORRECTIONS-[0-9]{8}-[0-9]{6}(-[0-9]+)?\n$")
        nom = nom.strip()
        nouveau = json.loads((self.audit / nom / "index.json").read_text(encoding="utf-8"))
        h, r = self.rapport()
        self.assertNotIn("TITRE DE L ANCIEN PLAN", h)
        self.assertIn(f"Le dossier {nom}/ contient ces mêmes fiches", h)
        self.assertNotIn("Le dossier CORRECTIONS/ contient", h)
        self.assertEqual(len(re.findall(r'<article class="fiche', h)), len(nouveau["corrections"]))
        self.assertEqual(r.stderr, "")
        self.assertIn("TITRE DE L ANCIEN PLAN", (ancien / "index.json").read_text(encoding="utf-8"))  # ancien dossier intact

    def test_garder(self):
        ancien, _ = self.preparer_ancien_plan()
        (ancien / ".garder").write_text("", encoding="utf-8")
        self.corrections()
        self.verifier_suit_le_nouveau(ancien)

    def test_suivi_commence(self):
        ancien, _ = self.preparer_ancien_plan()
        plan = ancien / "00-PLAN.md"
        plan.write_text(plan.read_text(encoding="utf-8") + "\n- [x] 01 fait\n", encoding="utf-8")
        self.corrections()
        self.verifier_suit_le_nouveau(ancien)


class TestCleDeJointure(ChaineBase):
    """N2 : index.json et rapport nettoient `cle` de la même façon ; les liens « Comment corriger » subsistent."""
    INVISIBLES = "\u200b\U000e0049\U000e0047\u061c\u00ad"

    def test_cle_invisible_nettoyee_et_toujours_liee(self):
        constat = "Balise titre\u200b manquante\U000e0049\U000e0047 sur la page d'accueil\u061c"
        (self.audit / "data/geo/geo.json").write_text(
            json.dumps({"signaux": [{"severite": "haute", "constat": constat}], "pages": []}, ensure_ascii=False), encoding="utf-8")
        fiches = pathlib.Path(self._tmp.name, "fiches")
        fiches.mkdir()
        (fiches / "geo-titre.md").write_text(
            "---\nid: geo-titre\ntitre: \"Titre manquant\"\ndomaine: GEO / IA\nseverite_type: haute\neffort: S\ndeclencheurs:\n"
            "  - \"geo:manquante\"\n---\n\n# Titre manquant\n\nCorps.\n", encoding="utf-8")
        r = lancer("corrections.py", self.audit, "--fiches", fiches)
        self.assertEqual(r.returncode, 0, r.stderr)
        brut = (self.audit / "CORRECTIONS/index.json").read_text(encoding="utf-8")
        for c in self.INVISIBLES:
            self.assertNotIn(c, brut)
        idx = json.loads(brut)
        cles = [s["cle"] for c in idx["corrections"] for s in c["signaux"]]
        self.assertEqual(cles, ["Balise titre manquante sur la page d'accueil"])
        h, rr = self.rapport()
        self.assertEqual(rr.stderr, "")
        self.assertRegex(h, r"Comment corriger → <a href=\"#correction-01\">01</a>")
        self.assertIn('id="correction-01"', h)

    def test_meme_nettoyage_des_deux_cotes(self):
        sys.path.insert(0, str(SCRIPTS))
        try:
            import corrections
            import rapport_html
        finally:
            sys.path.remove(str(SCRIPTS))
        brut = "Ligne " + self.INVISIBLES + "avec cl\u00e9 AKIAABCDEFGHIJKLMNOP"
        cle = corrections.cle_jointure(brut)
        self.assertNotIn("AKIAABCDEFGHIJKLMNOP", cle)
        for c in self.INVISIBLES:
            self.assertNotIn(c, cle)
        self.assertEqual(rapport_html.cle_jointure(brut), cle)
        self.assertEqual(corrections.cle_jointure(cle), cle)  # idempotent
        liens = rapport_html.liens_signaux({"corrections": [{"num": "01", "cles": [("geo", cle)]}]})
        s = {"source": "geo", "cle": brut, "severite": "haute", "texte": "t"}
        self.assertIn('href="#correction-01"', rapport_html._lien_corriger(s, liens))


if __name__ == "__main__":
    unittest.main()
