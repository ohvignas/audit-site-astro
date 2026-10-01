---
id: code-npm-audit-vulnerabilites
titre: Vulnérabilités connues dans les dépendances de production (npm audit)
domaine: Code
severite_type: haute
effort: M
declencheurs:
  - "projet:\\*\\*(critical|high)\\*\\* "      # lignes « **high** paquet — titre » de la section Vulnérabilités
  - "projet:\\*\\*moderate\\*\\* "
  - "projet:Total : .*(critical|high) [1-9]"
sources:
  - https://docs.npmjs.com/cli/v10/commands/npm-audit
  - https://docs.npmjs.com/cli/v10/configuring-npm/package-json#overrides
  - https://docs.astro.build/en/upgrade-astro/
---

# Vulnérabilités connues dans les dépendances de production (npm audit)

> **En une phrase** : `npm audit --omit=dev` signale des paquets de production avec une faille publiée ; il faut les mettre à jour, ou prouver que le chemin vulnérable n'est pas utilisé.

## Pourquoi c'est important

Une faille dans une dépendance de production (serveur Node, traitement d'images, analyse Markdown) peut permettre un déni de service, une lecture de fichiers ou une exécution de code, selon la bibliothèque. Les failles critiques et hautes s'exploitent vite une fois publiées. Beaucoup d'alertes sont en revanche théoriques (dépendance transitive d'un outil de build, fonction jamais appelée) : il faut trier avant de corriger, sans pour autant tout ignorer.

## Comment le constater soi-même

```bash
npm audit --omit=dev                    # dépendances de production seulement
npm audit --omit=dev --json > audit.json
npm why <paquet>                        # qui dépend du paquet vulnérable ?
npm ls <paquet>                         # quelle(s) version(s) installée(s) ?
```

Présent : `N vulnerabilities (… high, … critical)`. Corrigé : `found 0 vulnerabilities`, ou uniquement des alertes documentées comme non exploitables.

## Correction

1. Sauvegarde : `git switch -c fix/npm-audit` ; lockfile versionné (voir la fiche `code-lockfile-absent`).
2. **Trier** chaque alerte (critiques et hautes d'abord) : le paquet est-il chargé en production ? L'avis (GHSA) décrit-il une fonction que le site appelle ? Noter la décision.
3. **Correctif compatible** (même majeure) :
   ```bash
   npm audit fix --omit=dev
   ```
   Lire le diff du lockfile avant de commiter.
4. **Correctif qui exige une montée majeure** (ex. Astro, `@astrojs/node`, `sharp`) : la traiter comme une montée de version planifiée (fiche `code-astro-version-en-retard`), en installant explicitement la version corrigée :
   ```bash
   npm install astro@latest @astrojs/node@latest
   ```
5. **Dépendance transitive sans correctif dans le paquet parent** : forcer la version corrigée avec `overrides` dans `package.json`, puis tester :
   ```json
   {
     "overrides": {
       "paquet-vulnerable": "^2.3.4"
     }
   }
   ```
   (remplacer `paquet-vulnerable` et la version par celles de l'avis) puis `npm install` et `npm ls paquet-vulnerable`.
6. **Aucun correctif publié** : remplacer la dépendance, ou documenter le risque résiduel (chemin non utilisé) dans le dépôt avec la date de réexamen.
7. Automatiser : activer Dependabot ou Renovate, et lancer `npm audit --omit=dev --audit-level=high` en CI (échec si haute ou critique).

## Critères d'acceptation

- [ ] `npm audit --omit=dev --audit-level=high` sort avec le code 0
- [ ] Les alertes restantes (moyennes, basses) sont listées avec une décision écrite
- [ ] `npx astro check` et `npx astro build` passent après les mises à jour
- [ ] Aucune régression : pages clés en 200, formulaires et fonctions Convex opérationnels

## Vérification après correction

```bash
npm audit --omit=dev --audit-level=high; echo "code: $?"
bash scripts/project_checks.sh . /tmp/verif   # la section « Vulnérabilités connues » doit être vide en critical/high
```

## Pièges et retour arrière

- Ne jamais lancer `npm audit fix --force` sans relire : il peut monter plusieurs versions majeures d'un coup et casser le build.
- `--omit=dev` ignore les outils de build ; une faille de dev peut compter si le build tourne sur un serveur exposé ou en CI avec des secrets.
- Un `overrides` oublié masque de futures mises à jour : le commenter dans la description de la PR et le retirer quand le parent est corrigé.
- Retour arrière : `git checkout -- package.json package-lock.json && npm ci`.

## Pour aller plus loin

- https://docs.npmjs.com/cli/v10/commands/npm-audit : options de `npm audit` (`--omit`, `--audit-level`, `fix`).
- https://docs.npmjs.com/cli/v10/configuring-npm/package-json#overrides : forcer la version d'une dépendance transitive.
- https://docs.astro.build/en/upgrade-astro/ : monter Astro et ses intégrations ensemble.
