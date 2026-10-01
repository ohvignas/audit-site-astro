---
id: code-modules-audit-en-erreur
titre: Des contrôles du crawl n'ont pas tourné (module d'analyse en erreur)
domaine: Code
severite_type: haute
effort: S
declencheurs:
  - "crawl:modules_en_erreur"
sources:
  - https://docs.python.org/3/library/html.parser.html
  - https://docs.python.org/3/using/cmdline.html
---

# Des contrôles du crawl n'ont pas tourné (module d'analyse en erreur)

> **En une phrase** : un des modules d'analyse HTML de l'outil s'est arrêté sur une erreur (import, lecture d'une page, sérialisation) ; le rapport ne montre donc pas ses constats, et leur absence ne prouve pas que le site est sain.

## Pourquoi c'est important

Le crawl continue quand un module échoue, mais les contrôles de ce module (accessibilité, contenu de démonstration, sécurité des scripts, liens externes, ressources lourdes, données structurées) manquent au rapport. Un audit « propre » sur ces points serait un faux négatif. L'erreur vient de l'outil ou de la version de Python qui l'exécute, pas du site audité : il faut la corriger ou la signaler avant de s'appuyer sur le rapport.

## Comment le constater soi-même

```bash
grep "module .* désactivé" AUDIT_DIR/.log-crawl.txt      # une ligne par module en erreur
sed -n '/## Modules en erreur/,/^## /p' AUDIT_DIR/data/crawl/summary.md
python3 -c "import json;print(json.load(open('AUDIT_DIR/data/crawl/pages.json'))['meta']['modules'])"
python3 --version                                          # l'outil demande Python 3.9 ou plus
```

## Correction

1. Lire le nom du module et le type d'erreur dans `summary.md` (`ImportError` ou `SyntaxError` : version de Python ou installation incomplète ; `KeyError`, `TypeError` : défaut du module sur une page précise).
2. Installer ou mettre à jour Python (3.9 ou plus) puis relancer l'audit complet.
3. Si l'erreur persiste avec une version récente, relancer sur un échantillon (`--max-pages 20`) pour repérer la page en cause et signaler le défaut avec l'URL, le nom du module et le texte de l'erreur.

## Critères d'acceptation

- [ ] Aucune ligne « module … désactivé » dans le journal du crawl
- [ ] Pas de section « Modules en erreur » dans `summary.md`, pas de constat `modules_en_erreur`
- [ ] `meta.modules.erreurs_modules` absent ou vide dans `pages.json`

## Vérification après correction

Relancer le crawl (`python3 scripts/crawl_site.py https://SITE/ --out /tmp/verif --max-pages 20`) puis vérifier les trois points ci-dessus.

## Pièges et retour arrière

- Ne pas masquer l'erreur en retirant le module de la liste : les contrôles correspondants disparaîtraient du rapport sans avertissement.
- Aucune modification du site audité n'est nécessaire ni utile.

## Pour aller plus loin

- Documentation Python de l'analyseur HTML utilisé par les modules.
- Options de la ligne de commande de Python (choix de l'interpréteur).
