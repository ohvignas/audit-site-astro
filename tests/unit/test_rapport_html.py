import contextlib
import io
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

RACINE = pathlib.Path(__file__).resolve().parents[2]
SCRIPTS = RACINE / "plugins/audit-site-astro/skills/audit-complet/scripts"
FIXTURE = RACINE / "tests/unit/fixtures/audit-exemple"
sys.path.insert(0, str(SCRIPTS))


class TestRapportHtml(unittest.TestCase):
    def test_notes_par_domaine_bareme(self):
        import rapport_html
        s = [{"severite": "haute", "domaine": "Performance", "texte": "x", "exemples": []},
             {"severite": "moyenne", "domaine": "Performance", "texte": "y", "exemples": []},
             {"severite": "critique", "domaine": "Sécurité", "texte": "z", "exemples": []}]
        n = rapport_html.notes_par_domaine(s)
        self.assertEqual(n["Performance"]["note"], 86)
        self.assertEqual(n["Performance"]["lettre"], "B")
        self.assertEqual(n["Sécurité"]["note"], 80)

    def test_markdown_minimal(self):
        import rapport_html
        h = rapport_html.markdown_vers_html("# Titre\n\n- **gras** et `code`\n\n| A | B |\n|---|---|\n| 1 | <b>2</b> |\n")
        self.assertIn("<h1>Titre</h1>", h)
        self.assertIn("<strong>gras</strong>", h)
        self.assertIn("<code>code</code>", h)
        self.assertIn("<table>", h)
        self.assertIn("&lt;b&gt;2&lt;/b&gt;", h)  # HTML brut échappé

    def test_page_complete_sans_script_ni_ressource_externe(self):
        with tempfile.TemporaryDirectory() as t:
            copie = pathlib.Path(t, "audit")
            shutil.copytree(FIXTURE, copie)
            subprocess.run([sys.executable, str(SCRIPTS / "rapport_html.py"), str(copie)], check=True, capture_output=True)
            h = (copie / "RAPPORT.html").read_text(encoding="utf-8")
        self.assertTrue(h.startswith("<!doctype html>"))
        for section in ("Synthèse", "Lighthouse", "Rapport priorisé", "Signaux", "Annexes"):
            self.assertIn(section, h)
        self.assertNotIn("<script", h.lower())
        self.assertNotRegex(h, r'(src|href)="https?://(?!exemple\.test)')
        self.assertIn("@page", h)
        self.assertIn("prefers-color-scheme", h)

    def test_echappement_des_donnees_du_site(self):
        with tempfile.TemporaryDirectory() as t:
            copie = pathlib.Path(t, "audit")
            shutil.copytree(FIXTURE, copie)
            issues = copie / "data/crawl/issues.json"
            # \\" = guillemet échappé : le JSON reste valide et la charge utile atteint le rapport
            issues.write_text(issues.read_text(encoding="utf-8").replace("exemple.test", 'exemple.test/\\"><img src=x onerror=alert(1)>'), encoding="utf-8")
            subprocess.run([sys.executable, str(SCRIPTS / "rapport_html.py"), str(copie)], check=True, capture_output=True)
            h = (copie / "RAPPORT.html").read_text(encoding="utf-8")
        self.assertNotIn("<img src=x", h)
        self.assertIn("&lt;img src=x", h)

    def test_rapport_priorise_integre(self):
        with tempfile.TemporaryDirectory() as t:
            copie = pathlib.Path(t, "audit")
            shutil.copytree(FIXTURE, copie)
            (copie / "RAPPORT-AUDIT.md").write_text("# Audit du site\n\n### [PERF-001] Compression absente\n", encoding="utf-8")
            subprocess.run([sys.executable, str(SCRIPTS / "rapport_html.py"), str(copie)], check=True, capture_output=True)
            h = (copie / "RAPPORT.html").read_text(encoding="utf-8")
        self.assertIn("[PERF-001] Compression absente", h)
        self.assertIn("font foi", h)


    # --- correctifs de la revue (tour 1) ---------------------------------------------------------------------------
    def _audit_minimal(self, racine, issues=None, code=None, pagespeed=None):
        """Dossier d'audit réduit pour piloter les cas limites de generer()."""
        import json
        a = pathlib.Path(racine, "audit")
        (a / "data/crawl").mkdir(parents=True)
        (a / "data/crawl/pages.json").write_text(json.dumps({"meta": {"start_url": "https://exemple.test/"}}), encoding="utf-8")
        (a / "data/crawl/issues.json").write_text(json.dumps(issues or {}), encoding="utf-8")
        if code is not None:
            (a / "data/code").mkdir()
            (a / "data/code/code-scan.json").write_text(json.dumps({"constats": code}), encoding="utf-8")
        if pagespeed is not None:
            (a / "data/perf").mkdir()
            (a / "data/perf/pagespeed.json").write_text(json.dumps(pagespeed), encoding="utf-8")
        return a

    def test_liens_dangereux_neutralises(self):
        import rapport_html
        for url in ("\x01javascript:alert(1)", "java\tscript:alert(1)", "java\nscript:alert(1)", "JaVaScRiPt:alert(1)",
                    "data:text/html;base64,AAAA", "vbscript:msgbox(1)", "//evil.example/x", "\\\\evil.example",
                    "&#x6A;avascript:alert(1)", "ftp://exemple.test/f"):
            h = rapport_html.markdown_vers_html(f"[x]({url})")
            self.assertNotIn("<a ", h, url)
            self.assertNotIn("href", h, url)

    def test_liens_sains_conserves(self):
        import rapport_html
        for url in ("https://exemple.test/a?b=1&c=2", "http://exemple.test", "mailto:a@exemple.test", "#ancre", "/chemin/page",
                    "./page.html", "../page", "page.html", "dossier/page?x=1", "?q=1"):
            self.assertIn('<a href="', rapport_html.markdown_vers_html(f"[x]({url})"), url)
        self.assertIn('href="https://exemple.test/a?b=1&amp;c=2"', rapport_html.markdown_vers_html("[x](https://exemple.test/a?b=1&c=2)"))

    def test_lighthouse_malforme_tolere(self):
        with tempfile.TemporaryDirectory() as t:
            a = self._audit_minimal(t, pagespeed=[
                {"url": "https://exemple.test/", "strategie": "mobile", "scores": "x", "metriques": ["y"], "terrain_page": "z", "terrain_origine": 3},
                {"url": "https://exemple.test/b", "strategie": "desktop", "scores": {"performance": "NaN?"}, "metriques": {"LCP": "4 s", "CLS": None},
                 "terrain_page": {"categorie_globale": "FAST", "LCP": "vite", "CLS": {"p75": 0.1, "verdict": "bon"}}}])
            import rapport_html
            h = rapport_html.generer(a)
        self.assertIn("https://exemple.test/b", h)
        self.assertIn("Lighthouse", h)

    def test_markdown_tableau_gfm_un_tiret_et_code_avec_barre(self):
        import rapport_html
        h = rapport_html.markdown_vers_html("| A | B |\n|-|-|\n| 1 | 2 |\n\n| C | D |\n|:-|-:|\n| `x|y` | z \\| w |\n")
        self.assertEqual(h.count("<table>"), 2)
        self.assertIn("<code>x|y</code>", h)
        self.assertEqual(h.count("<td>"), 4)
        self.assertIn("z | w", h)

    def test_markdown_titre_garde_diese_final(self):
        import rapport_html
        self.assertIn("<h1>C#</h1>", rapport_html.markdown_vers_html("# C#"))
        self.assertIn("<h2>Titre</h2>", rapport_html.markdown_vers_html("## Titre ##"))
        self.assertIn("<h3>Titre #tag</h3>", rapport_html.markdown_vers_html("### Titre #tag"))

    def test_note_globale_renormalisee(self):
        import rapport_html
        n = {"Performance": {"note": 80, "critique": 0}, "Sécurité": {"note": 90, "critique": 0}, "Divers": {"note": 0, "critique": 0}}
        # (20 x 80 + 12 x 90) / 32 = 83,75 ; « Divers » (hors grille) et les domaines absents sont exclus
        self.assertEqual(rapport_html.note_globale(n), (84, False))
        self.assertEqual(rapport_html.note_globale({}), (None, False))

    def test_plafond_49_avec_critique_securite_ou_seo(self):
        import rapport_html
        bon = {"note": 100, "critique": 0}
        self.assertEqual(rapport_html.note_globale({"Performance": bon, "Sécurité": {"note": 80, "critique": 1}}), (49, True))
        self.assertEqual(rapport_html.note_globale({"Performance": bon, "SEO technique": {"note": 80, "critique": 1}}), (49, True))
        self.assertEqual(rapport_html.note_globale({"Performance": {"note": 80, "critique": 1}, "Code": bon}), (87, False))  # critique hors sécurité/SEO
        with tempfile.TemporaryDirectory() as t:
            a = self._audit_minimal(t, code=[{"severite": "critique", "categorie": "securite", "constat": "Clé secrète exposée", "piste": "", "ou": []}])
            import rapport_html as r
            h = r.generer(a)
        self.assertIn("Note plafonnée à 49/100", h)
        self.assertIn("Note globale indicative : 49 sur 100", h)
        with tempfile.TemporaryDirectory() as t:
            h = rapport_html.generer(self._audit_minimal(t))
        self.assertNotIn("Note plafonnée", h)


CLE_CODE = "Image d'en-tête non optimisée (<img> au lieu de <Image>)"  # signal « code » de la fixture
FICHE = ("# Ajouter width et height\n\nPourquoi : éviter le décalage de mise en page.\n\n```astro\n<img src=\"/a.png\" width=\"10\">\n"
         "<script>alert(1)</script>\n</pre><script>alert(2)</script>\n```\n\n```bash\nnpm run build && echo \"ok\" > /dev/null\n```\n\n"
         "- voir [la doc](https://exemple.test/doc)\n- piège [x](javascript:alert(3))\n")


class TestRapportHtmlCorrections(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.audit = pathlib.Path(self._tmp.name, "audit")
        shutil.copytree(FIXTURE, self.audit)
        self.dossier = self.audit / "CORRECTIONS"

    def corrections(self, entrees, fiches=None, sans_fiche=None, version=1):
        """Écrit CORRECTIONS/ : entrees = [(num, titre, [(source, cle)])] ; le fichier NN-id.md est créé sauf si fiches[num] est None."""
        self.dossier.mkdir(exist_ok=True)
        liste = []
        for num, titre, cles in entrees:
            nom = f"{num}-correction-{int(num)}.md"
            liste.append({"num": num, "id": f"correction-{int(num)}", "titre": titre, "domaine": "Performance", "severite": "haute",
                          "effort": "S", "fichier": nom, "signaux": [{"texte": "t", "source": a, "cle": b} for a, b in cles]})
            corps = (fiches or {}).get(num, FICHE)
            if corps is not None:
                (self.dossier / nom).write_text(corps, encoding="utf-8")
        idx = {"version": version, "corrections": liste, "sans_fiche": sans_fiche or []}
        (self.dossier / "index.json").write_text(json.dumps(idx), encoding="utf-8")
        return liste

    def page(self):
        """(html, stderr) de generer() en direct."""
        import rapport_html
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            h = rapport_html.generer(self.audit)
        return h, err.getvalue()

    # --- sans index ou index inutilisable : page inchangée ---------------------------------------------------------
    def test_sans_index_page_sans_trace_des_corrections(self):
        h, err = self.page()
        self.assertEqual(err, "")
        for trace in ("Plan de correction", "Guides de correction", "Comment corriger", "correction-", "corriger{"):
            self.assertNotIn(trace, h)
        self.assertEqual(h.count("<section"), 5)

    def test_dossier_sans_index_identique_a_sans_dossier(self):
        avant, _ = self.page()
        self.dossier.mkdir()
        (self.dossier / "01-correction-1.md").write_text(FICHE, encoding="utf-8")
        apres, err = self.page()
        self.assertEqual(avant, apres)
        self.assertEqual(err, "")

    def test_index_inutilisable_page_identique_et_avertissement(self):
        base, _ = self.page()
        cas = {"json cassé": "{pas du json", "version 2": json.dumps({"version": 2, "corrections": []}),
               "sans version": json.dumps({"corrections": []}), "racine liste": "[]",
               "corrections absent": json.dumps({"version": 1}), "vide": json.dumps({"version": 1, "corrections": []})}
        self.dossier.mkdir()
        for nom, contenu in cas.items():
            (self.dossier / "index.json").write_text(contenu, encoding="utf-8")
            h, err = self.page()
            if nom == "vide":
                self.assertEqual(err, "", nom)  # index valide mais sans correction : rien à signaler
            else:
                self.assertIn("CORRECTIONS/", err, nom)
            self.assertEqual(h, base, nom)

    # --- page avec index --------------------------------------------------------------------------------------------
    def test_plan_annexe_et_ancres_coherents(self):
        self.corrections([("03", "Dimensions des images", [("code", CLE_CODE)]),
                          ("07", "Liens cassés", [("crawl", "liens_casses"), ("code", CLE_CODE)]),
                          ("12", "Sans signal", [])])
        h, err = self.page()
        self.assertEqual(err, "")
        # ordre des sections : synthèse, plan, Lighthouse, ..., annexes, guides
        ids = re.findall(r'<section class="majeure" id="([^"]+)"', h)
        self.assertEqual(ids, ["synthese", "plan-correction", "lighthouse", "priorise", "signaux", "annexes", "guides"])
        self.assertIn("<h2>Plan de correction</h2>", h)
        self.assertIn("<h2>Guides de correction</h2>", h)
        self.assertIn("Le dossier CORRECTIONS/ contient ces mêmes fiches, à donner à votre agent de code.", h)
        # chaque lien interne vers une correction a sa cible, chaque cible est unique
        cibles = re.findall(r'id="(correction-\d+)"', h)
        self.assertEqual(sorted(cibles), ["correction-03", "correction-07", "correction-12"])
        for href in set(re.findall(r'href="#(correction-\d+)"', h)):
            self.assertIn(href, cibles)
        for c in cibles:
            self.assertIn(f'href="#{c}"', h)
        # tableau du plan : n°, titre, domaine, sévérité, effort, lien
        plan = h[h.index('id="plan-correction"'):h.index('id="lighthouse"')]
        self.assertIn('<a href="#correction-03">03</a>', plan)
        self.assertIn("Dimensions des images", plan)
        for col in ("Domaine", "Sévérité", "Effort"):
            self.assertIn(col, plan)
        self.assertEqual(plan.count("Voir le guide"), 3)

    def test_lien_comment_corriger_sur_les_signaux(self):
        self.corrections([("03", "A", [("code", CLE_CODE)]), ("07", "B", [("code", CLE_CODE), ("crawl", "liens_casses")])])
        h, _ = self.page()
        # signal associé à deux corrections : les deux numéros, par ordre croissant
        self.assertIn('Comment corriger → <a href="#correction-03">03</a>, <a href="#correction-07">07</a>', h)
        # signal associé à une seule correction
        self.assertIn('Comment corriger → <a href="#correction-07">07</a></span>', h)
        # 2 signaux associés, chacun dans le top 15 et dans la liste par domaine ; les autres signaux n'ont pas de lien
        self.assertEqual(h.count("Comment corriger →"), 4)
        signaux = h[h.index('id="signaux"'):h.index('id="annexes"')]
        self.assertEqual(signaux.count("Comment corriger →"), 4)
        self.assertNotIn("Comment corriger", h[:h.index('id="signaux"')])

    def test_association_exige_source_et_cle(self):
        self.corrections([("01", "A", [("crawl", CLE_CODE), ("code", "liens_casses")])])  # bonnes clés, mauvaises sources
        h, _ = self.page()
        self.assertNotIn("Comment corriger", h)
        self.assertIn('id="correction-01"', h)  # la fiche reste dans le plan et l'annexe

    def test_fiches_rendues_et_code_echappe(self):
        self.corrections([("01", "Dimensions", [("code", CLE_CODE)])])
        h, _ = self.page()
        guides = h[h.index('id="guides"'):]
        self.assertIn("<h3>Ajouter width et height</h3>", guides)  # h1 de la fiche descendu en h3
        self.assertIn("<pre><code>", guides)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", guides)
        self.assertIn("&lt;/pre&gt;&lt;script&gt;alert(2)&lt;/script&gt;", guides)  # « </pre> » dans un bloc ne referme rien
        self.assertIn("npm run build &amp;&amp; echo &quot;ok&quot; &gt; /dev/null", guides)
        self.assertEqual(guides.count("<pre>"), guides.count("</pre>"))
        self.assertNotIn("<script", h.lower())
        self.assertNotIn("javascript:", h.lower())
        self.assertIn('<a href="https://exemple.test/doc" rel="noopener">la doc</a>', guides)

    def test_titres_de_l_index_echappes(self):
        self.corrections([("01", '<img src=x onerror=alert(1)>"', [("code", CLE_CODE)])], sans_fiche=[{"texte": "<b>sans</b> guide", "source": "s", "cle": "c"}])
        h, _ = self.page()
        self.assertNotIn("<img src=x", h)
        self.assertNotIn("<b>sans</b>", h)
        self.assertIn("&lt;img src=x onerror=alert(1)&gt;", h)
        self.assertIn("&lt;b&gt;sans&lt;/b&gt; guide", h)
        self.assertIn("Constats sans guide dédié", h)

    def test_fiche_sans_titre_recoit_celui_de_l_index_et_frontmatter_retire(self):
        self.corrections([("01", "Titre de l'index", [])], fiches={"01": "---\nid: x\n---\nCorps simple.\n"})
        h, _ = self.page()
        guides = h[h.index('id="guides"'):]
        self.assertIn("<h3>Titre de l&#x27;index</h3>", guides)
        self.assertIn("<p>Corps simple.</p>", guides)
        self.assertNotIn("id: x", guides)

    def test_numeros_a_trois_chiffres(self):
        self.corrections([("101", "Grande", [("code", CLE_CODE)]), ("102", "Autre", [])])
        h, err = self.page()
        self.assertEqual(err, "")
        self.assertIn('id="correction-101"', h)
        self.assertIn('Comment corriger → <a href="#correction-101">101</a>', h)

    # --- robustesse -------------------------------------------------------------------------------------------------
    def test_parties_cassees_ignorees_avec_avertissement(self):
        liste = self.corrections([("01", "Bonne", [("code", CLE_CODE)]), ("02", "Fiche absente", [("crawl", "liens_casses")]),
                                  ("03", "Chemin", []), ("04", "Majuscules", []), ("05", "Sous-dossier", []),
                                  ("06", "Numéro invalide", []), ("07", "Doublon", [])], fiches={"02": None})
        (self.audit / "secret.md").write_text("# SECRET\n", encoding="utf-8")
        for entree, fichier in zip(liste[2:5], ("../secret.md", "03-Correction.md", "sub/05-x.md")):
            entree["fichier"] = fichier
        liste[5]["num"] = "6"
        liste[6]["num"] = "01"
        (self.dossier / "index.json").write_text(json.dumps({"version": 1, "corrections": liste + ["pas un dict", 3]}), encoding="utf-8")
        h, err = self.page()
        self.assertIn('id="correction-01"', h)
        for n in ("02", "03", "04", "05", "06", "07"):
            self.assertNotIn(f'id="correction-{n}"', h)
        self.assertNotIn("SECRET", h)
        self.assertNotIn("Fiche absente", h)
        self.assertNotIn("Comment corriger → <a href=\"#correction-02\"", h)  # pas de lien vers une ancre inexistante
        self.assertGreaterEqual(err.count("CORRECTIONS/"), 7)
        self.assertIn("02", err)

    def test_fichier_hors_dossier_refuse_meme_valide_par_le_motif(self):
        liste = self.corrections([("01", "Lien symbolique", [])], fiches={"01": None})
        cible = self.audit / "hors.md"
        cible.write_text("# HORS DOSSIER\n", encoding="utf-8")
        try:
            os.symlink(cible, self.dossier / liste[0]["fichier"])
        except (OSError, NotImplementedError):
            self.skipTest("liens symboliques indisponibles")
        h, err = self.page()
        self.assertNotIn("HORS DOSSIER", h)
        self.assertNotIn("Guides de correction", h)
        self.assertIn("CORRECTIONS/", err)

    def test_num_et_fichier_avec_retour_a_la_ligne_refuses(self):
        liste = self.corrections([("03", "Bonne", []), ("04", "Faux numéro", []), ("05", "Faux fichier", [])])
        liste[1]["num"] = "03\n"
        liste[2]["fichier"] = "05-correction-5.md\n"
        (self.dossier / "index.json").write_text(json.dumps({"version": 1, "corrections": liste}), encoding="utf-8")
        h, err = self.page()
        self.assertEqual(re.findall(r'id="(correction-[^"]*)"', h), ["correction-03"])
        self.assertNotIn("\n\"", h)
        self.assertEqual(err.count("CORRECTIONS/"), 2)

    def test_fiche_illisible_ignoree(self):
        self.corrections([("01", "Binaire", []), ("02", "Bonne", [])], fiches={"01": None})
        (self.dossier / "01-correction-1.md").write_bytes(b"\xff\xfe\x00\x80 invalide")
        h, err = self.page()
        self.assertNotIn('id="correction-01"', h)
        self.assertIn('id="correction-02"', h)
        self.assertIn("01", err)

    # --- impression, style, poids ------------------------------------------------------------------------------------
    def test_impression_saut_de_page_par_fiche_et_code_qui_passe_a_la_ligne(self):
        self.corrections([("01", "A", []), ("02", "B", [])])
        h, _ = self.page()
        css = h[h.index("<style>"):h.index("</style>")]
        self.assertRegex(css, r"\.fiche\{break-before:page")
        self.assertIn("white-space:pre-wrap", css)
        self.assertIn("overflow-wrap:anywhere", css)
        self.assertIn("prefers-color-scheme: dark", css)
        self.assertNotIn("<script", h.lower())
        # les couleurs ajoutées passent par les variables du thème : pas de couleur en dur pour les fiches
        ajout = css[css.index(".corriger"):]
        self.assertNotRegex(ajout, r"#[0-9a-fA-F]{3,6}\b")

    def test_taille_raisonnable_avec_quarante_fiches(self):
        ligne = "Étape de correction : vérifier la configuration puis relancer la construction du site.\n"
        bloc = "```nginx\nserver { listen 443 ssl; add_header X-Frame-Options \"DENY\"; }\n```\n"
        fiche = "# Fiche de correction\n\n" + "".join((ligne if i % 3 else bloc) for i in range(150))
        self.corrections([(f"{n:02d}", f"Correction {n}", [("code", CLE_CODE)] if n == 1 else []) for n in range(1, 41)],
                         fiches={f"{n:02d}": fiche for n in range(1, 41)})
        h, err = self.page()
        self.assertEqual(err, "")
        self.assertEqual(h.count('<article class="fiche'), 40)
        self.assertLess(len(h.encode("utf-8")), 3 * 1024 * 1024)

    def test_cli_avec_corrections(self):
        self.corrections([("01", "A", [("code", CLE_CODE)])])
        r = subprocess.run([sys.executable, str(SCRIPTS / "rapport_html.py"), str(self.audit)], check=True, capture_output=True, text=True)
        self.assertEqual(r.stderr, "")
        self.assertIn('id="correction-01"', (self.audit / "RAPPORT.html").read_text(encoding="utf-8"))


class TestRapportHtmlDossierPointe(TestRapportHtmlCorrections):
    """Le rapport suit data/corrections-dossier.txt (dossier réellement écrit) et retombe sur CORRECTIONS/ si le pointeur est absent ou hostile."""
    HORODATE = "CORRECTIONS-20260930-101500"

    def dossier_horodate(self, titre="Nouveau plan"):
        """CORRECTIONS/ = ancien plan (conservé) ; CORRECTIONS-<horodatage>/ = nouveau plan ; renvoie le dossier du nouveau."""
        self.corrections([("01", "Ancien plan", [])])
        self.dossier = self.audit / self.HORODATE
        self.corrections([("01", titre, [("code", CLE_CODE)]), ("02", "Deuxieme", [])])
        return self.dossier

    def pointeur(self, contenu):
        chemin = self.audit / "data/corrections-dossier.txt"
        chemin.parent.mkdir(exist_ok=True)
        chemin.write_bytes(contenu if isinstance(contenu, bytes) else contenu.encode("utf-8"))

    def test_le_pointeur_designe_le_nouveau_plan(self):
        self.dossier_horodate()
        self.pointeur(self.HORODATE + "\n")
        h, err = self.page()
        self.assertEqual(err, "")
        self.assertIn("Nouveau plan", h)
        self.assertNotIn("Ancien plan", h)
        self.assertEqual(re.findall(r'id="(correction-[^"]*)"', h), ["correction-01", "correction-02"])
        self.assertIn("Comment corriger", h)

    def test_la_mention_montre_le_dossier_reel(self):
        self.dossier_horodate()
        self.pointeur(self.HORODATE + "\n")
        h, _ = self.page()
        self.assertEqual(h.count(f"Le dossier {self.HORODATE}/ contient ces mêmes fiches"), 2)
        self.assertNotIn("Le dossier CORRECTIONS/ contient", h)

    def test_mention_inchangee_avec_corrections_simple(self):
        self.corrections([("01", "A", [])])
        self.pointeur("CORRECTIONS\n")
        h, err = self.page()
        self.assertEqual(err, "")
        self.assertEqual(h.count("Le dossier CORRECTIONS/ contient ces mêmes fiches"), 2)

    def test_sans_pointeur_lit_corrections(self):
        self.dossier_horodate()
        h, _ = self.page()
        self.assertIn("Ancien plan", h)
        self.assertNotIn("Nouveau plan", h)

    def test_pointeur_sans_retour_a_la_ligne_final_accepte(self):
        self.dossier_horodate()
        self.pointeur(self.HORODATE)
        h, _ = self.page()
        self.assertIn("Nouveau plan", h)

    def test_pointeurs_hostiles_retombent_sur_corrections(self):
        self.dossier_horodate()
        hostiles = ["../x\n", "/etc\n", "/etc/passwd", "..\n", ".\n", "CORRECTIONS/..\n", "CORRECTIONS/../CORRECTIONS-20260930-101500\n",
                    self.HORODATE + "\nautre\n", "\n" + self.HORODATE + "\n", self.HORODATE + "\n\n", self.HORODATE + "\r\n",
                    "CORRECTIONS-\n", "CORRECTIONS-a\n", "corrections\n", " CORRECTIONS\n", "CORRECTIONS \n", "C:\\x\n", "",
                    "\n", "\x00", "CORRECTIONS\x00\n", "CORRECTIONS-1/../..\n", "CORRECTIONS-" + "1" * 300 + "\n"]
        for hostile in hostiles:
            with self.subTest(hostile=hostile):
                self.pointeur(hostile)
                h, err = self.page()
                self.assertIn("Ancien plan", h)
                self.assertNotIn("Nouveau plan", h)
                self.assertNotIn("/etc", h)

    def test_pointeur_binaire_ou_illisible_ignore(self):
        self.dossier_horodate()
        self.pointeur(b"\xff\xfe\x80")
        h, _ = self.page()
        self.assertIn("Ancien plan", h)
        (self.audit / "data/corrections-dossier.txt").unlink()
        (self.audit / "data/corrections-dossier.txt").mkdir()  # un dossier à la place du fichier
        h, _ = self.page()
        self.assertIn("Ancien plan", h)

    def test_pointeur_hostile_avertit_sans_le_suivre(self):
        self.dossier_horodate()
        # un dossier voisin valide hors du motif : jamais lu
        voisin = self.audit.parent / "x"
        voisin.mkdir()
        (voisin / "index.json").write_text(json.dumps({"version": 1, "corrections": []}), encoding="utf-8")
        self.pointeur("../x\n")
        h, err = self.page()
        self.assertIn("corrections-dossier.txt invalide", err)
        self.assertIn("Ancien plan", h)

    def test_pointeur_vers_un_dossier_absent_ne_ressort_pas_l_ancien_plan(self):
        self.corrections([("01", "Ancien plan", [])])
        self.pointeur("CORRECTIONS-20991231-000000\n")
        h, err = self.page()
        self.assertNotIn("Ancien plan", h)
        self.assertNotIn("Guides de correction", h)
        self.assertIn("CORRECTIONS-20991231-000000/", err)

    def test_pointeur_vers_un_lien_symbolique_refuse(self):
        self.corrections([("01", "Ancien plan", [])])
        ailleurs = self.audit.parent / "ailleurs"
        shutil.copytree(self.dossier, ailleurs)
        try:
            os.symlink(str(ailleurs), str(self.audit / self.HORODATE))
        except (OSError, NotImplementedError):
            self.skipTest("liens symboliques indisponibles")
        self.pointeur(self.HORODATE + "\n")
        h, err = self.page()
        self.assertNotIn("Guides de correction", h)
        self.assertIn(self.HORODATE, err)

    def test_cli_suit_le_pointeur(self):
        self.dossier_horodate()
        self.pointeur(self.HORODATE + "\n")
        subprocess.run([sys.executable, str(SCRIPTS / "rapport_html.py"), str(self.audit)], check=True, capture_output=True, text=True)
        h = (self.audit / "RAPPORT.html").read_text(encoding="utf-8")
        self.assertIn("Nouveau plan", h)
        self.assertNotIn("Ancien plan", h)


FICHES_REELLES = SCRIPTS.parent / "references/fiches"


class TestMarkdownListes(unittest.TestCase):
    def md(self, texte, decalage=0):
        import rapport_html
        return rapport_html.markdown_vers_html(texte, decalage)

    def test_bloc_indente_dans_une_etape_reste_dans_le_li_sans_indentation(self):
        h = self.md("1. Étape **un**\n\n   ```astro\n   <div a=\"1\">\n     <b>x</b>\n   </div>\n   ```\n2. Étape deux\n")
        self.assertNotIn("```", h)
        self.assertEqual(h.count("<ol"), 1)
        self.assertIn("<li>Étape <strong>un</strong><pre><code>&lt;div a=&quot;1&quot;&gt;\n  &lt;b&gt;x&lt;/b&gt;\n&lt;/div&gt;</code></pre></li><li>Étape deux</li>", h)

    def test_paragraphe_apres_bloc_ou_ligne_vide_reste_dans_l_etape(self):
        h = self.md("1. Un\n\n   suite du un\n\n   ```bash\n   ls\n   ```\n\n   après le code\n2. Deux\n")
        self.assertEqual(h.count("<ol"), 1)
        self.assertIn("<li>Un<p>suite du un</p><pre><code>ls</code></pre><p>après le code</p></li><li>Deux</li>", h)

    def test_liste_interrompue_garde_sa_numerotation(self):
        h = self.md("1. a\n2. b\n\n```bash\nx\n```\n\n3. c\n4. d\n")
        self.assertIn('<ol start="3"><li>c</li>', h)
        self.assertEqual(h.count('<ol>'), 1)
        self.assertNotIn('start="1"', h)

    def test_gras_autour_du_code_en_ligne(self):
        h = self.md("**`aria-hidden`** et **le `<body>` seul** et [`lien`](https://exemple.test/)")
        self.assertIn("<strong><code>aria-hidden</code></strong>", h)
        self.assertIn("<strong>le <code>&lt;body&gt;</code> seul</strong>", h)
        self.assertIn('<a href="https://exemple.test/" rel="noopener"><code>lien</code></a>', h)
        self.assertEqual(self.md("[x](`javascript:alert(1)`)").count("href"), 0)
        self.assertNotIn("\x00", self.md("a \x00 `b` \x000\x00"))

    def test_cases_a_cocher_en_symboles_sans_input(self):
        h = self.md("- [ ] à faire\n- [x] fait\n- [X] fait aussi\n- [texte] normal\n")
        self.assertIn("<li>☐ à faire</li>", h)
        self.assertIn("<li>☑ fait</li>", h)
        self.assertIn("<li>☑ fait aussi</li>", h)
        self.assertIn("<li>[texte] normal</li>", h)
        self.assertNotIn("<input", h)

    def test_bloc_indente_hors_liste_perd_son_retrait(self):
        self.assertIn("<pre><code>a\n  b</code></pre>", self.md("   ```\n   a\n     b\n   ```\n"))


class TestEchappementsMarkdown(unittest.TestCase):
    """« \\X » (ponctuation ASCII, CommonMark) : X littéral, jamais de lien, gras, code ni case à cocher ; pas de barre oblique."""

    def md(self, texte, decalage=0):
        import rapport_html
        return rapport_html.markdown_vers_html(texte, decalage)

    def test_lien_echappe_reste_du_texte(self):
        h = self.md("Constat : \\[x\\](https://evil.example/x)")
        self.assertNotIn("<a", h)
        self.assertNotIn("href", h)
        self.assertNotIn("\\", h)
        self.assertIn("[x](https://evil.example/x)", h)

    def test_balise_echappee_sans_barre_oblique_et_echappee_en_html(self):
        h = self.md("3 \\<img\\> sans attribut alt")
        self.assertEqual(h, "<p>3 &lt;img&gt; sans attribut alt</p>")

    def test_prose_de_corrections_rendue_sans_syntaxe_ni_barre(self):
        import corrections
        for brut in ("x <img> [a](https://e.example/) **gras** *it* `code` _souligne_ PUBLIC_CLE <head>",
                     "[cliquez ici](https://evil.example/x)", "- [x] coché ?", "# titre", "1. liste", "\\ fin \\"):
            h = self.md(corrections.prose(brut))
            for interdit in ("<a", "<strong", "<em", "<code", "<h", "<li", "☑", "☐"):
                self.assertNotIn(interdit, h, f"{brut!r} -> {h!r}")
            self.assertEqual(h, f"<p>{html_texte(brut)}</p>")  # texte d'origine exact : aucune barre oblique ajoutée

    def test_aller_retour_des_caracteres_echappes(self):
        self.assertEqual(self.md("a \\_b\\_ \\*c\\* \\`d\\` \\\\ \\# \\|"), "<p>a _b_ *c* `d` \\ # |</p>")
        self.assertEqual(self.md("\\*\\*pas gras\\*\\*"), "<p>**pas gras**</p>")
        self.assertEqual(self.md("- \\[ \\] pas une case"), "<ul><li>[ ] pas une case</li></ul>")

    def test_echappement_dans_le_code_reste_litteral(self):
        self.assertEqual(self.md("`a\\*b` et \\`c`"), "<p><code>a\\*b</code> et `c`</p>")

    def test_barre_oblique_non_echappante_conservee(self):
        self.assertEqual(self.md("C:\\Users\\x et \\d+ \\é"), "<p>C:\\Users\\x et \\d+ \\é</p>")

    def test_echappement_dans_l_url_d_un_lien_de_confiance(self):
        self.assertIn('<a href="https://exemple.test/a_b" rel="noopener">lien</a>', self.md("[lien](https://exemple.test/a\\_b)"))
        self.assertNotIn("href", self.md("[x](javascript\\:alert(1))"))


class TestCodeEnLigneMultiple(unittest.TestCase):
    """Codes en ligne CommonMark : une suite de N accents graves se ferme sur la suite suivante d'exactement N ; contenu littéral."""

    HOSTILES = ("a`[b](https://evil.example/x)", "a`**gras**", "a``[b](https://evil.example/x)``c", "`[b](https://evil.example/x)",
                "[b](https://evil.example/x)`", "``", "`", "a```b", "[x] a`b", "a` *it* `b", "x`<img src=x>`[y](javascript:1)",
                " `a` ", "a\\`[b](https://evil.example/x)")

    def md(self, texte, decalage=0):
        import rapport_html
        return rapport_html.markdown_vers_html(texte, decalage)

    def test_reproduction_de_la_revue(self):
        import corrections
        h = self.md("- constat: " + corrections.code("a`[b](https://evil.example/x)"))
        self.assertNotIn("<a", h)
        self.assertIn("<code>a`[b](https://evil.example/x)</code>", h)
        self.assertNotIn("<strong", self.md("- " + corrections.code("a`**gras**")))

    def test_suites_doubles_et_triples(self):
        self.assertEqual(self.md("``a`[b](https://e.example/)``"), "<p><code>a`[b](https://e.example/)</code></p>")
        self.assertEqual(self.md("```x``[y](https://e.example/)```"), "<p><code>x``[y](https://e.example/)</code></p>")
        self.assertEqual(self.md("`a` et ``b`c``"), "<p><code>a</code> et <code>b`c</code></p>")

    def test_accent_grave_en_bord_de_code(self):
        self.assertEqual(self.md("`` `a ``"), "<p><code>`a</code></p>")
        self.assertEqual(self.md("`` a` ``"), "<p><code>a`</code></p>")
        self.assertEqual(self.md("`  `"), "<p><code>  </code></p>")  # que des espaces : rien n'est retiré

    def test_suite_sans_fermeture_reste_du_texte(self):
        self.assertEqual(self.md("``a`"), "<p>``a`</p>")
        self.assertEqual(self.md("a ``b` **c**"), "<p>a ``b` <strong>c</strong></p>")  # texte de confiance hors code : Markdown normal
        self.assertEqual(self.md("```a``"), "<p>```a``</p>")

    def test_aucune_syntaxe_dans_un_code(self):
        self.assertEqual(self.md("``**x** [a](https://e.example/) *y*``"), "<p><code>**x** [a](https://e.example/) *y*</code></p>")

    def test_donnees_hostiles_via_corrections_code(self):
        import corrections, html
        for brut in self.HOSTILES:
            for contexte in ("- {}", "{}", "| a |\n|---|\n| {} |", "1. {} fin"):
                h = self.md(contexte.format(corrections.code(brut)))
                for interdit in ("<a", "<strong", "<em", "☑", "☐", "<img"):
                    self.assertNotIn(interdit, h, f"{brut!r} dans {contexte!r} -> {h!r}")
            h = self.md("- " + corrections.code(brut))
            self.assertIn(f"<code>{html.escape(corrections.propre(brut))}</code>", h, brut)


class TestBlocsDeCode(unittest.TestCase):
    def md(self, texte):
        import rapport_html
        return rapport_html.markdown_vers_html(texte)

    def test_la_cloture_est_une_suite_au_moins_aussi_longue_sans_texte(self):
        self.assertEqual(self.md("````text\n```x [a](https://e.example/)\n```\n````\nfin"),
                         "<pre><code>```x [a](https://e.example/)\n```</code></pre>\n<p>fin</p>")
        self.assertEqual(self.md("```\na\n```\nb"), "<pre><code>a</code></pre>\n<p>b</p>")


def html_texte(s):
    import html
    return html.escape(s)


class TestFichesReelles(unittest.TestCase):
    """Rend de vraies fiches de references/fiches/ : les blocs de code des étapes numérotées et les listes doivent tenir."""

    def rendre(self, nom):
        import rapport_html
        brut = (FICHES_REELLES / nom).read_text(encoding="utf-8")
        md = re.sub(r"\A---\n.*?\n---\n", "", brut, count=1, flags=re.S)
        return md, rapport_html.markdown_vers_html(md, decalage=2)

    def test_fiches_avec_blocs_sous_les_etapes(self):
        for nom in ("a11y-aria-noms-masquage.md", "convex-collect-non-borne.md", "secu-anti-clickjacking.md", "perf-images-responsives.md"):
            with self.subTest(nom):
                md, h = self.rendre(nom)
                self.assertNotIn("```", h)
                self.assertNotIn("<script", h.lower())
                self.assertEqual(h.count("<pre>"), h.count("</pre>"))
                self.assertGreaterEqual(h.count("<pre>"), md.count("```") // 2)
                self.assertNotRegex(h, r"<pre><code>[ \t]")  # pas de retrait résiduel en tête de bloc
                self.assertNotRegex(h, r"<code>[^<]*<(?!/code)")  # le code est échappé : jamais de balise dans <code>
                self.assertNotIn("**", re.sub(r"<pre>.*?</pre>|<code>.*?</code>", "", h, flags=re.S))
                self.assertNotIn("[ ]", h)
                # numérotation continue : « 1. » n'ouvre une liste que là où le Markdown recommence à 1 ; une liste
                # interrompue par un bloc ou un paragraphe hors étape reprend avec <ol start="N">, jamais à 1
                self.assertEqual(h.count("<ol>"), len(re.findall(r"(?m)^\s*1\. ", md)))
                for debut in re.findall(r'<ol start="(\d+)">', h):
                    self.assertRegex(md, rf"(?m)^\s*{debut}\. ")

    def test_etapes_numerotees_et_code_rattache_a_l_etape(self):
        _, h = self.rendre("a11y-aria-noms-masquage.md")
        correction = h[h.index("Correction</h4>"):h.index("Critères d")]
        self.assertEqual(correction.count("<ol"), 1)
        self.assertEqual(correction.count("<li>"), 7)
        self.assertNotIn("start=", correction)
        premiere = correction[correction.index("<li>"):correction.index("</li><li>")]
        self.assertIn("<pre><code>&lt;div role=&quot;dialog&quot;", premiere)
        self.assertIn("&lt;button type=&quot;button&quot; role=&quot;switch&quot;", premiere)

    def test_fiche_serveur_nginx_echappee(self):
        md, h = self.rendre("secu-anti-clickjacking.md")
        self.assertIn("nginx", md)
        code = "".join(re.findall(r"<pre><code>(.*?)</code></pre>", h, flags=re.S))
        self.assertIn("add_header", code)
        self.assertIn("&quot;", code)
        self.assertNotRegex(code, r'add_header [^\n]*"')  # guillemets échappés

    def test_case_a_cocher_des_criteres_d_acceptation(self):
        _, h = self.rendre("a11y-aria-noms-masquage.md")
        self.assertIn("<li>☐ ", h)
        self.assertNotIn("<input", h)


if __name__ == "__main__":
    unittest.main()
