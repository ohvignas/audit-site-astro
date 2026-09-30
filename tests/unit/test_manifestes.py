"""Valide les manifestes Claude Code et Cursor, et les SKILL.md du plugin."""
import json
import pathlib
import re
import unittest

RACINE = pathlib.Path(__file__).resolve().parents[2]
PLUGIN = RACINE / "plugins" / "audit-site-astro"
MARKETPLACE_CLAUDE = RACINE / ".claude-plugin" / "marketplace.json"
MARKETPLACE_CURSOR = RACINE / ".cursor-plugin" / "marketplace.json"
PLUGIN_CLAUDE = PLUGIN / ".claude-plugin" / "plugin.json"
PLUGIN_CURSOR = PLUGIN / ".cursor-plugin" / "plugin.json"
TOUS = (MARKETPLACE_CLAUDE, MARKETPLACE_CURSOR, PLUGIN_CLAUDE, PLUGIN_CURSOR)
KEBAB = re.compile(r"^[a-z0-9][a-z0-9.-]*$")
NOM_SKILL = re.compile(r"^[a-z0-9-]+$")


def charger(chemin):
    return json.loads(chemin.read_text(encoding="utf-8"))


def frontmatter(chemin):
    """Extrait les paires clef: valeur du frontmatter YAML (valeurs sur une ligne)."""
    texte = chemin.read_text(encoding="utf-8")
    m = re.match(r"^---\r?\n(.*?)\r?\n---\r?\n", texte, re.S)
    if not m:
        return None
    champs = {}
    for ligne in m.group(1).splitlines():
        if ligne[:1] in (" ", "\t", "#") or ":" not in ligne:
            continue
        clef, valeur = ligne.split(":", 1)
        valeur = valeur.strip()
        if len(valeur) >= 2 and valeur[0] == valeur[-1] and valeur[0] in "\"'":
            valeur = valeur[1:-1]
        champs[clef.strip()] = valeur
    return champs


class TestManifestes(unittest.TestCase):
    def test_json_valide(self):
        for chemin in TOUS:
            with self.subTest(chemin=str(chemin.relative_to(RACINE))):
                self.assertTrue(chemin.is_file(), "manifeste absent")
                self.assertIsInstance(charger(chemin), dict)

    def test_noms_kebab_case(self):
        for chemin in TOUS:
            data = charger(chemin)
            noms = [data["name"]] + [p["name"] for p in data.get("plugins", [])]
            for nom in noms:
                with self.subTest(chemin=chemin.name, nom=nom):
                    self.assertRegex(nom, KEBAB)

    def test_sources_des_marketplaces(self):
        for chemin in (MARKETPLACE_CLAUDE, MARKETPLACE_CURSOR):
            for plugin in charger(chemin)["plugins"]:
                with self.subTest(chemin=str(chemin.relative_to(RACINE)), plugin=plugin["name"]):
                    source = (RACINE / plugin["source"]).resolve()
                    self.assertTrue(source.is_dir(), "source introuvable : %s" % source)
                    self.assertTrue((source / "skills").is_dir(), "pas de dossier skills/")

    def test_meme_nom_et_version_claude_et_cursor(self):
        pc, pu = charger(PLUGIN_CLAUDE), charger(PLUGIN_CURSOR)
        self.assertEqual(pc["name"], pu["name"])
        self.assertEqual(pc["version"], pu["version"])
        mc, mu = charger(MARKETPLACE_CLAUDE), charger(MARKETPLACE_CURSOR)
        self.assertEqual(mc["name"], mu["name"])
        self.assertEqual([p["name"] for p in mc["plugins"]], [p["name"] for p in mu["plugins"]])
        self.assertEqual(mc["metadata"]["version"], pc["version"])
        for p in mc["plugins"]:
            self.assertEqual(p["version"], pc["version"])

    def test_skills(self):
        fichiers = sorted(PLUGIN.glob("skills/*/SKILL.md"))
        self.assertTrue(fichiers, "aucun SKILL.md trouvé")
        for fichier in fichiers:
            dossier = fichier.parent.name
            with self.subTest(skill=dossier):
                champs = frontmatter(fichier)
                self.assertIsNotNone(champs, "frontmatter absent")
                self.assertEqual(champs.get("name"), dossier)
                self.assertRegex(dossier, NOM_SKILL)
                description = champs.get("description", "")
                self.assertTrue(description.strip(), "description vide")
                self.assertLessEqual(len(description), 1024)


if __name__ == "__main__":
    unittest.main()
