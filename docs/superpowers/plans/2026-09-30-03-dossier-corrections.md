# Dossier CORRECTIONS/ relié au rapport — plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Chaque audit produit un dossier `CORRECTIONS/` autonome qu'on donne tel quel à un agent de code (Claude Code, Cursor…) : consignes, plan priorisé à cocher et une fiche par correction contenant l'explication, les preuves relevées sur ce site, les étapes, les critères d'acceptation et la vérification. Le rapport HTML/PDF renvoie vers ces fiches et les intègre en annexe.

**Architecture:** Les fiches génériques (`references/fiches/*.md`, frontmatter + sections, rédigées par domaine) déclarent leurs `declencheurs` (source + motif). `signaux.collecter` expose la source et la clé de chaque signal. `corrections.py` associe signaux et fiches, puis écrit `CORRECTIONS/` (LISEZ-MOI, 00-PLAN, NN-<id>.md, index.json). `rapport_html.py` lit `CORRECTIONS/index.json` pour ajouter les liens « Comment corriger → » et une annexe « Guides de correction » (le PDF est donc complet).

**Tech Stack:** Python 3.9+ stdlib, Bash.

**Spec:** demandes utilisateur du 2026-09-30 : « les documents pour expliquer tout ce qu'il faut modifier et comment le faire, liés au rapport » ; « pas un prompt à coller : on donne le fichier ou le dossier complet à l'agent et tout est expliqué dedans ». Modèle de fiche : `references/fiches/_MODELE.md`.

## Global Constraints
- Python ≥ 3.9, stdlib uniquement (parseur de frontmatter maison : scalaires, listes de chaînes entre guillemets, `[]`) ; bash 3.2.
- Pas de Chrome/docker/npm en local (Mac 16 Go, a planté le 2026-09-30).
- Sorties déterministes (même audit → mêmes fichiers, même ordre).
- Le rapport HTML reste sans JavaScript, tout texte dynamique échappé ; les fiches Markdown sont rendues par `markdown_vers_html` (liste blanche d'URL).
- Commits terminés par `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

---

### Task 1 : source et clé des signaux

**Files:** Modify `scripts/signaux.py`, `tests/unit/test_signaux.py`.
**Interfaces — Produces:** chaque signal gagne `source` ∈ {`crawl`, `geo`, `code`, `http`, `securite`, `lighthouse`} et `cle` (crawl : clé d'issue ; geo : texte du signal ; code : texte du constat ; http/securite : ligne brute du fichier ; lighthouse : `"<id> <titre>"` ou le titre de l'échec). `rapport_brut.py` ignore ces champs (sortie inchangée : le test d'égalité doit rester vert).
- [ ] Test : chaque signal de la fixture a `source` et `cle` non vides et cohérents avec sa provenance ; le test « clés exactes du dict » passe à `{severite, domaine, texte, exemples, source, cle}`.
- [ ] Implémentation, suite verte, commit `feat(signaux): source et clé de chaque signal`.

### Task 2 : `fiches.py` — chargement et association

**Files:** Create `scripts/fiches.py`, `tests/unit/test_fiches.py`, `tests/unit/fixtures/fiches/` (3-4 fiches minimales).
**Interfaces — Produces:** `charger_fiches(dossier: Path) -> list[dict]` (clés du frontmatter + `corps` sans frontmatter + `chemin` ; ignore `_MODELE.md` et les fichiers commençant par `_`) ; `associer(signaux: list[dict], fiches: list[dict]) -> tuple[dict[str, list[dict]], list[dict]]` = (fiche id → signaux déclencheurs, signaux sans fiche). Règles : déclencheur `crawl:<clé>` = égalité exacte ; autres = `re.search(motif, cle, re.I)` sur la source correspondante ; un signal peut déclencher plusieurs fiches (toutes sont retenues) ; fiches à `declencheurs: []` jamais retenues automatiquement.
- [ ] Tests : parseur (scalaires, listes, `[]`, guillemets, antislashs échappés `\\.` → `\.`), association exacte vs regex, multi-fiches, fiche sans déclencheur, signal sans fiche.
- [ ] **Test de validité de la vraie base** (`references/fiches/`) : chaque fiche se charge ; `id` = nom de fichier ; préfixe de domaine valide ; `severite_type` et `effort` dans les listes autorisées ; chaque déclencheur a un préfixe connu et une regex compilable ; les sections du modèle existent dans l'ordre (`## Pourquoi c'est important`, `## Comment le constater soi-même`, `## Correction`, `## Critères d'acceptation`, `## Vérification après correction`, `## Pièges et retour arrière`).
- [ ] **Tests de couverture** : (a) chaque clé d'issue produite par `crawl_site.py` (extraite du source par regex sur `add("<clé>"` et les clés ajoutées dans `crawl()`) est couverte par au moins une fiche `crawl:` ; (b) chaque constat d'`astro_scan.py` obtenu en scannant `tests/cobaye/casse` et `tests/cobaye/propre` est couvert ; (c) chaque signal de la fixture `audit-exemple` est couvert. Les trous éventuels sont listés dans le message d'échec.
- [ ] Commit `feat(corrections): chargement et association des fiches`.

### Task 3 : `corrections.py` — le dossier pour l'agent

**Files:** Create `scripts/corrections.py`, `tests/unit/test_corrections.py`; Modify `scripts/collect_all.sh` (étape `corrections` après `rapport brut`, avant `rapport-html`), `docker/entrypoint.sh` (ligne « 🛠️ Corrections : audits/…/CORRECTIONS/ »).
**Interfaces — Produces:** `python3 corrections.py DOSSIER_AUDIT [--fiches DIR] [--projet CHEMIN]` → `DOSSIER_AUDIT/CORRECTIONS/{LISEZ-MOI.md, 00-PLAN.md, NN-<id>.md…, index.json}` ; `index.json` = `{"version": 1, "corrections": [{"num": "01", "id", "titre", "domaine", "severite", "effort", "fichier", "signaux": [{"texte", "source", "cle"}]}], "sans_fiche": [...]}`.

Contenu :
- **Ordre / priorité** : sévérité constatée (la plus haute parmi ses signaux ; `critique` > `haute` > `moyenne` > `basse` > `info`), puis effort (S < M < L), puis domaine, puis id. Numérotation `01`, `02`… sur 2 chiffres (3 si > 99).
- **`NN-<id>.md`** = en-tête (titre, bloc « Domaine · Sévérité constatée · Effort · Version d'Astro requise · Priorité NN/total ») + **section insérée juste après le titre : `## Constat sur ce site`** (pour chaque signal déclencheur : texte, jusqu'à 10 exemples — URL, fichier:ligne, mesures —, puis « … et N autres ») + le corps de la fiche générique + `## Suivi` (cases : corrigé, vérifié, date, commit).
- **`00-PLAN.md`** : titre, site, date, légende ; liste à cocher `- [ ] **01** — Titre · domaine · sévérité · effort → [01-id.md](01-id.md)` ; section « Constats sans fiche dédiée » (texte + exemples) ; section « Fiches utiles sans détection automatique » (fiches à `declencheurs: []`, citées avec un lien vers leur chemin dans le plugin).
- **`LISEZ-MOI.md`** (destiné à l'agent de code et à l'humain) : ce qu'est ce dossier ; le site et la date ; le chemin du projet si fourni ; si `RAPPORT-AUDIT.md` existe, il fait foi pour la priorisation ; **méthode** : lire `00-PLAN.md`, traiter dans l'ordre, une correction = une branche `corrections/<date>` + un commit par fiche (message `fix(audit): NN <titre>`), lire « Constat sur ce site » puis appliquer « Correction », valider par « Critères d'acceptation » et « Vérification après correction », cocher `00-PLAN.md` et `## Suivi` ; **règles** : ne jamais modifier `dist/` ni la production directement, sauvegarde/branche avant tout, aucune valeur de secret dans les commits ou messages, s'arrêter et demander à l'humain pour les fiches de sévérité `critique`, les changements d'infrastructure (proxy, DNS, CDN), les textes éditoriaux et juridiques (proposer, ne pas publier) ; **à la fin** : relancer l'audit (commande `collect_all.sh` exacte avec l'URL et le projet) et comparer avec l'historique (`../index.html`).
- **Idempotence** : le dossier est recréé à chaque exécution (supprimer puis réécrire), sauf si `CORRECTIONS/.garder` existe (alors écrire dans `CORRECTIONS-<horodatage>/` et le signaler).
- [ ] Tests : structure complète sur la fixture + fiches de fixture ; ordre de priorité ; section « Constat sur ce site » avec exemples ; `index.json` valide ; « sans fiche » ; idempotence et `.garder` ; LISEZ-MOI mentionne RAPPORT-AUDIT.md seulement s'il existe ; étape `corrections` dans `collect_all.sh` (test de collecte existant mis à jour).
- [ ] Commit `feat(corrections): dossier CORRECTIONS/ autonome pour l'agent de code`.

### Task 4 : liens et annexe dans le rapport HTML/PDF

**Files:** Modify `scripts/rapport_html.py`, `tests/unit/test_rapport_html.py`.
- [ ] Si `CORRECTIONS/index.json` existe : chaque signal du rapport associé à une correction affiche « Comment corriger → NN » (ancre interne `#correction-NN`) ; nouvelle section **« Plan de correction »** (après la synthèse et avant Lighthouse : tableau NN, titre, domaine, sévérité, effort, lien d'ancre) ; **annexe « Guides de correction »** en fin de page : chaque fiche `NN-id.md` rendue par `markdown_vers_html`, précédée d'un saut de page à l'impression. Mention : « Le dossier CORRECTIONS/ contient ces mêmes fiches, à donner à votre agent de code. »
- [ ] Tests : ancres présentes et cohérentes, annexe rendue, pas de `<script`, contenu des fiches échappé, taille raisonnable ; sans `index.json` la page est identique à avant.
- [ ] Commit `feat(rapport): plan de correction et guides en annexe du rapport`.

### Task 5 : documentation
- [ ] `audit-complet/SKILL.md` : §5 — après `RAPPORT-AUDIT.md`, relancer `corrections.py` puis `rapport_html.py`, `rapport_pdf.sh`, `historique.py` ; §6 — restituer `CORRECTIONS/` (« à donner à ton agent ») ; §7 — appliquer les corrections en suivant `CORRECTIONS/LISEZ-MOI.md`.
- [ ] README : arborescence (RAPPORT.html, RAPPORT.pdf, CORRECTIONS/…, ../index.html), section « Corriger le site avec son agent » (une phrase : « donne le dossier CORRECTIONS/ à ton agent »), section Rapports.
- [ ] Commit `docs: dossier CORRECTIONS et rapports dans le skill et le README`.
