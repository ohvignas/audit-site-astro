---
id: secu-astro-env-schema
titre: "Variables d'environnement sans schéma astro:env (aucun garde-fou contre les fuites)"
domaine: Sécurité
severite_type: basse
effort: S
declencheurs:
  - "code:Variables d'environnement sans schéma astro:env"
versions_astro: ">=5.0"
sources:
  - https://docs.astro.build/en/guides/environment-variables/#type-safe-environment-variables
  - https://docs.astro.build/en/reference/modules/astro-env/
  - https://docs.astro.build/en/reference/configuration-reference/#envvalidatesecrets
---

# Variables d'environnement sans schéma astro:env (aucun garde-fou contre les fuites)

> **En une phrase** : rien n'empêche aujourd'hui un secret d'être importé dans du code client par erreur ; `astro:env` transforme cette erreur en échec de build.

## Pourquoi c'est important

Avec `import.meta.env`, la seule protection est le préfixe `PUBLIC_` : une erreur de nommage ou un secret lu dans un composant client donne au mieux `undefined`, au pire une fuite silencieuse. Le schéma `astro:env` déclare chaque variable avec son contexte (`client` ou `server`) et son accès (`public` ou `secret`). Un secret déclaré `server` + `secret` ne peut pas être importé côté client : le build échoue au lieu de publier la clé. Les variables sont aussi validées (type, présence) au démarrage.

## Comment le constater soi-même

```bash
grep -n "schema" astro.config.* | grep -i env      # présent : env: { schema: { ... } }
grep -rn "astro:env" src | head                    # présent : imports depuis astro:env/server ou astro:env/client
grep -rn "import.meta.env\." src | grep -v PUBLIC_ # cas à migrer vers astro:env/server
```

## Correction

1. Astro 5.0 ou plus est requis (`npm ls astro`). Sur une version antérieure, mettez à jour Astro ou gardez `import.meta.env` en veillant à ne lire les secrets que dans du code exécuté côté serveur.
2. Déclarez toutes les variables dans `astro.config.mjs`. Lisez `.env.example` (noms uniquement) pour la liste.

   ```js
   // astro.config.mjs
   import { defineConfig, envField } from 'astro/config';

   export default defineConfig({
     env: {
       validateSecrets: true, // valide aussi les secrets au démarrage
       schema: {
         // Secrets : serveur uniquement, jamais envoyés au navigateur
         RESEND_API_KEY: envField.string({ context: 'server', access: 'secret' }),
         CONVEX_DEPLOY_KEY: envField.string({ context: 'server', access: 'secret', optional: true }),
         // Valeurs publiques envoyées au navigateur
         PUBLIC_CONVEX_URL: envField.string({ context: 'client', access: 'public' }),
         // Valeur serveur non secrète, avec valeur par défaut
         CONTACT_EMAIL: envField.string({ context: 'server', access: 'public', default: 'contact@exemple.fr' }),
       },
     },
   });
   ```

   Un secret avec `context: 'client'` et `access: 'secret'` est interdit par Astro (aucun moyen sûr de l'envoyer au client).
3. Remplacez les lectures `import.meta.env.NOM` par des imports typés.

   ```ts
   // côté serveur (endpoint, action, page .astro, middleware)
   import { RESEND_API_KEY } from 'astro:env/server';
   // côté client (composant hydraté)
   import { PUBLIC_CONVEX_URL } from 'astro:env/client';
   ```
4. Pour lire un secret non déclaré dans le schéma (cas rare) : `getSecret('NOM')` depuis `astro:env/server`.
5. Sur le serveur de production et en intégration continue, définissez toutes les variables `secret` obligatoires (sinon le build ou le démarrage échoue avec un message clair). Ajoutez des valeurs factices dans la CI pour le build.

## Critères d'acceptation

- [ ] `env.schema` déclare toutes les variables utilisées.
- [ ] Les secrets sont en `context: 'server'`, `access: 'secret'`.
- [ ] Importer un secret dans un composant client fait échouer `npm run build` (à tester une fois, puis annuler).
- [ ] Aucune régression : build OK, formulaires et intégrations fonctionnent en production.

## Vérification après correction

```bash
npm run build
grep -rn "import.meta.env\." src | grep -v PUBLIC_ || echo "plus de lecture directe de secret"
python3 scripts/astro_scan.py . --out /tmp/verif-code && (grep -i "schéma astro:env" /tmp/verif-code/code-scan.md || echo "constat levé")
```

## Pièges et retour arrière

- Le build échoue si une variable secrète obligatoire manque : fournissez-la ou marquez-la `optional: true`.
- `astro:env` ne remplace pas la rotation des clés déjà exposées (`secu-secret-dans-js-client`).
- Retour arrière : supprimer le bloc `env` et revenir aux `import.meta.env` (gardez une branche Git dédiée).

## Pour aller plus loin

- Guide Astro : variables d'environnement typées et sûres.
- Référence du module `astro:env` : `getSecret`, `astro:env/server`, `astro:env/client`.
- Option `env.validateSecrets` : validation au démarrage.
