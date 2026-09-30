---
id: secu-env-versionne-git
titre: "Fichier .env versionné dans Git ou absent du .gitignore"
domaine: Sécurité
severite_type: critique
effort: M
declencheurs:
  - "code:Fichiers \\.env versionnés dans git"
  - "code:\\.env absent du \\.gitignore"
sources:
  - https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository
  - https://github.com/newren/git-filter-repo
  - https://git-scm.com/docs/gitignore
  - https://docs.astro.build/en/guides/environment-variables/
---

# Fichier .env versionné dans Git ou absent du .gitignore

> **En une phrase** : les secrets sont enregistrés dans l'historique Git (ou risquent de l'être au prochain `git add .`), donc lisibles par toute personne ayant accès au dépôt.

## Pourquoi c'est important

Un fichier `.env` commité reste dans l'historique même après suppression. Toute personne qui clone le dépôt, tout service tiers connecté (CI, hébergeur) et tout futur collaborateur peut le retrouver, et si le dépôt devient public un jour, les robots trouvent les clés en quelques minutes. Un `.env` absent du `.gitignore` est un accident qui attend d'arriver. La seule protection fiable est de **faire tourner les secrets**, puis d'empêcher la récidive.

## Comment le constater soi-même

```bash
git ls-files | grep -E '(^|/)\.env' | grep -v '\.example$'      # doit être vide
grep -nE '^\.env' .gitignore                                    # doit afficher .env, .env.*
git log --all --oneline -- .env .env.local .env.production | head   # présent : historique touché
```

## Correction

1. **Créer une branche de sécurité et sauvegarder** : `git switch -c securite-env && git bundle create ../sauvegarde-depot.bundle --all`.
2. **Faire tourner tous les secrets** contenus dans les fichiers concernés (liste des noms de variables uniquement) : voir la table de rotation de `secu-secret-dans-js-client`. À faire en premier : la purge de l'historique ne rend pas une clé déjà copiée inoffensive.
3. **Retirer le fichier du suivi sans le supprimer du disque** :

   ```bash
   git rm --cached .env .env.local .env.production   # adaptez à la liste de `git ls-files`
   ```
4. **Ignorer définitivement** et fournir un modèle sans valeur :

   ```gitignore
   # .gitignore
   .env
   .env.*
   !.env.example
   ```

   ```bash
   # .env.example : uniquement les noms, jamais de vraies valeurs
   printf 'PUBLIC_CONVEX_URL=\nRESEND_API_KEY=\nCONVEX_DEPLOY_KEY=\n' > .env.example
   git add .gitignore .env.example
   git commit -m "Retirer .env du suivi Git, ajouter .env.example"
   ```
5. **Purger l'historique** si le dépôt est partagé, distant ou peut le devenir (réécrit l'historique : prévenez l'équipe). Étape irréversible sur le dépôt distant : la proposer à l'humain, qui la lance lui-même ; l'agent ne pousse jamais avec `--force`. Avec `git-filter-repo` (outil à installer, voir sa page) :

   ```bash
   git clone --mirror git@github.com:organisation/depot.git depot-purge.git
   cd depot-purge.git
   git filter-repo --invert-paths --path .env --path .env.local --path .env.production
   git push --force --mirror
   ```

   Ensuite, chaque collaborateur reclone le dépôt (les anciens clones contiennent encore l'historique). Sur GitHub, contactez le support pour purger les vues en cache et les forks si le dépôt était public.
6. **Activer une détection automatique** : GitHub secret scanning et push protection, ou `gitleaks` en intégration continue.
7. Placer les vraies valeurs dans les secrets de l'hébergeur / de la CI et dans le `.env` du serveur (permissions `chmod 600`, propriétaire l'utilisateur de l'application).

## Critères d'acceptation

- [ ] `git ls-files | grep -E '(^|/)\.env' | grep -v example` ne renvoie rien.
- [ ] `.gitignore` contient `.env` et `.env.*` (avec l'exception `.env.example`).
- [ ] `git log --all -- .env` est vide après purge (si purge faite).
- [ ] Tous les secrets qui ont figuré dans un `.env` versionné sont révoqués et remplacés.
- [ ] Le site fonctionne avec les nouvelles valeurs (build et exécution).

## Vérification après correction

```bash
python3 scripts/astro_scan.py . --out /tmp/verif-code
grep -iE "\.env" /tmp/verif-code/code-scan.md || echo "constats .env levés"
git check-ignore -v .env
```

## Pièges et retour arrière

- **Réécrire l'historique est destructif** : sauvegarde (bundle) obligatoire, à ne faire qu'avec l'accord de l'équipe ; les branches et les Pull Requests ouvertes doivent être recréées.
- `.gitignore` n'agit pas sur un fichier déjà suivi : il faut `git rm --cached`.
- Sans purge, les secrets restent lisibles dans l'historique : la rotation reste l'unique vraie protection.
- Retour arrière de la purge : restaurer depuis le bundle (`git clone ../sauvegarde-depot.bundle`).

## Pour aller plus loin

- GitHub : retirer des données sensibles d'un dépôt.
- git-filter-repo : outil de réécriture d'historique recommandé.
- Documentation `gitignore` : syntaxe des motifs et exceptions.
- Astro, variables d'environnement : fichiers `.env` pris en charge.
