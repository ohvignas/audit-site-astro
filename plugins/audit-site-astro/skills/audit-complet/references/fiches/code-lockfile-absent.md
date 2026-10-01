---
id: code-lockfile-absent
titre: Aucun fichier de verrouillage des dépendances (lockfile)
domaine: Code
severite_type: moyenne
effort: S
declencheurs:
  - "code:Aucun lockfile"
sources:
  - https://docs.npmjs.com/cli/v10/configuring-npm/package-lock-json
  - https://docs.astro.build/en/install-and-setup/
---

# Aucun fichier de verrouillage des dépendances (lockfile)

> **En une phrase** : sans lockfile versionné, chaque installation peut récupérer d'autres versions des dépendances, donc le site déployé n'est pas celui qu'on a testé.

## Pourquoi c'est important

`package.json` n'indique que des plages de versions (`^7.3.5`). Sans lockfile, deux `npm install` faits à des dates différentes peuvent produire deux arbres de dépendances différents : un build qui passait hier peut casser aujourd'hui sans qu'une ligne de code ait changé, et une dépendance compromise peut entrer sans être remarquée. Le lockfile fige l'arbre exact, permet `npm ci` (installation reproductible et rapide) et rend `npm audit` fiable.

## Comment le constater soi-même

```bash
ls package-lock.json pnpm-lock.yaml yarn.lock bun.lock bun.lockb 2>/dev/null   # aucun résultat = problème
git ls-files | grep -E '(package-lock\.json|pnpm-lock\.yaml|yarn\.lock|bun\.lockb?)$'   # doit lister un fichier
grep -n "lock" .gitignore                                                       # le lockfile ne doit pas être ignoré
```

## Correction

1. Choisir **un seul** gestionnaire de paquets (celui déjà utilisé par l'équipe ou la CI). Ne pas mélanger `npm` et `pnpm` : deux lockfiles se contredisent.
2. Générer le lockfile sans changer les versions de `package.json` :
   ```bash
   npm install            # crée package-lock.json ; pnpm install / yarn install / bun install selon le cas
   ```
3. Vérifier que le lockfile n'est pas dans `.gitignore`, puis le versionner :
   ```bash
   git add package-lock.json
   git commit -m "chore: versionner le lockfile"
   ```
4. Remplacer `npm install` par `npm ci` dans la CI, le Dockerfile et les scripts de déploiement (`npm ci` échoue si `package.json` et le lockfile divergent, ce qui est le comportement voulu).
5. Dans un Dockerfile, copier le lockfile avant le code pour profiter du cache :
   ```dockerfile
   COPY package.json package-lock.json ./
   RUN npm ci
   COPY . .
   ```

## Critères d'acceptation

- [ ] Un lockfile existe à la racine du projet et est suivi par Git (`git ls-files`)
- [ ] Un seul lockfile (pas de `package-lock.json` avec `pnpm-lock.yaml`)
- [ ] La CI et le déploiement utilisent `npm ci` (ou l'équivalent gelé : `pnpm install --frozen-lockfile`, `yarn install --immutable`, `bun install --frozen-lockfile`)
- [ ] Aucune régression : `npm run build` passe, pages clés en 200

## Vérification après correction

```bash
npm ci && npm run build   # npm ci supprime lui-même node_modules et réinstalle depuis le lockfile
python3 scripts/astro_scan.py . --out /tmp/verif   # le constat « Aucun lockfile » doit disparaître
```

## Pièges et retour arrière

- Le premier `npm install` sans lockfile résout toutes les versions au jour J : lancer build et `astro check` avant de commiter, pour repérer une dépendance qui aurait avancé.
- Ne jamais éditer un lockfile à la main ; en cas de conflit Git, le régénérer (`npm install`) puis relire le diff.
- Retour arrière : supprimer le fichier ajouté (`git rm package-lock.json`) revient à l'état antérieur, mais ce n'est pas recommandé.

## Pour aller plus loin

- https://docs.npmjs.com/cli/v10/configuring-npm/package-lock-json : rôle du `package-lock.json`.
- https://docs.astro.build/en/install-and-setup/ : installation d'un projet Astro et gestionnaires de paquets.
