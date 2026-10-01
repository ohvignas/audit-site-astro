---
id: code-actions-sans-validation
titre: Actions Astro sans validation des données reçues (input), corps ou sessions trop permissifs
domaine: Sécurité
severite_type: moyenne
effort: S
declencheurs:
  - "code:Action Astro sans validation input"
  - "code:actionBodySizeLimit relevé"
  - "code:session configurée sans ttl"
sources:
  - https://docs.astro.build/en/guides/actions/
  - https://docs.astro.build/en/reference/configuration-reference/#security
  - https://docs.astro.build/en/reference/configuration-reference/#session
  - https://docs.astro.build/en/reference/modules/astro-actions/
---

# Actions Astro sans validation des données reçues (input), corps ou sessions trop permissifs

> **En une phrase** : une action Astro est un point d'entrée public ; sans schéma `input`, n'importe quelle donnée atteint votre code, et une session sans `ttl` ne s'expire jamais.

## Pourquoi c'est important

Chaque action est exposée comme un endpoint public (`/_actions/nom-de-l-action`) : le navigateur n'est pas le seul à pouvoir l'appeler, un script le peut aussi, avec le contenu de son choix. Sans `input`, le handler reçoit les données brutes (un `FormData` pour `accept: 'form'`) : rien ne garantit qu'un e-mail est un e-mail, qu'un nombre est un nombre ni que la taille est raisonnable. Ces données finissent en base Convex, dans un e-mail ou dans une requête, avec les risques d'injection et de données invalides qui vont avec. Deux réglages voisins relèvent de la même hygiène : `security.actionBodySizeLimit` (1 Mo par défaut, depuis Astro 5.18) agrandi expose à des corps volumineux, et `session` sans `ttl` (en secondes, infini par défaut, depuis Astro 5.7) garde les sessions valides pour toujours.

## Comment le constater soi-même

```bash
grep -n "defineAction" -A4 src/actions/*.ts       # chaque defineAction doit avoir une ligne « input: … »
grep -n -A3 "actionBodySizeLimit\|session:" astro.config.*
```

Présent : un `defineAction({ … })` sans `input`, un `actionBodySizeLimit` supérieur à `1048576`, un bloc `session: { … }` sans `ttl`. Corrigé : tous les `defineAction` ont un `input`, la limite est celle par défaut (ou justifiée), la session a un `ttl`.

## Correction

1. Ajouter un schéma Zod `input` à chaque action (le `z` s'importe depuis `astro/zod`, pas depuis `astro:schema` ni `astro:content`, retirés en Astro 6) :

   ```ts
   // src/actions/index.ts
   import { defineAction } from 'astro:actions';
   import { z } from 'astro/zod';

   export const server = {
     inscrire: defineAction({
       accept: 'form',
       input: z.object({ email: z.email() }),   // Zod 4 (Astro 6+) ; avant : z.string().email()
       handler: async ({ email }, ctx) => {
         // données déjà validées ici
         return { ok: true };
       },
     }),
   };
   ```
2. Pour une action réservée à des utilisateurs connectés, contrôler l'identité **dans le handler** : les actions demandent les mêmes contrôles d'autorisation qu'un endpoint d'API.

   ```ts
   import { ActionError, defineAction } from 'astro:actions';

   handler: async (input, ctx) => {
     if (!ctx.locals.user) throw new ActionError({ code: 'UNAUTHORIZED' });
     // …
   }
   ```
3. Une action qui ne reçoit aucune donnée (handler sans paramètre) n'a pas besoin d'`input`.
4. Ne relever `security.actionBodySizeLimit` que pour une action d'envoi de fichiers, et vérifier l'identité avant de lire le corps. Sinon, supprimer la ligne (défaut : 1 Mo).
5. Donner une durée de vie aux sessions (en secondes) :

   ```js
   // astro.config.mjs
   export default defineConfig({
     session: { ttl: 604800 },   // 7 jours ; en plus de driver: … si votre adaptateur n'en fournit pas par défaut
   });
   ```

## Critères d'acceptation

- [ ] Chaque `defineAction` qui reçoit des données a un `input`.
- [ ] Un envoi invalide (e-mail mal formé, champ manquant) reçoit une erreur de validation (`error.code === 'BAD_REQUEST'`), pas un traitement.
- [ ] Une action réservée répond `UNAUTHORIZED` sans session.
- [ ] `actionBodySizeLimit` est absent ou justifié ; `session` a un `ttl`.

## Vérification après correction

```bash
grep -n "defineAction" -A4 src/actions/*.ts
python3 scripts/astro_scan.py . --out /tmp/verif   # les constats « Action Astro sans validation input » et « session configurée sans ttl » doivent disparaître
```

## Pièges et retour arrière

- Avec `accept: 'form'`, Astro convertit les champs avant validation : les champs `type="number"` se valident avec `z.number()` (sans coercition), les cases à cocher avec `z.coerce.boolean()`, les fichiers avec `z.instanceof(File)`, les champs répétés avec `z.array(…)`, les autres avec `z.string()`. Un champ vide devient `null` : un champ facultatif se déclare `.nullish()`.
- Un `input` ajouté après coup peut refuser des envois qui passaient (champ absent, vide) : tester le formulaire réel.
- Un `ttl` court déconnecte les visiteurs plus souvent : choisir selon la sensibilité (administration : quelques heures ; espace client : quelques jours).
- Retour arrière : retirer la ligne `input` ou `ttl` (le comportement précédent revient, sans la protection).

## Pour aller plus loin

- https://docs.astro.build/en/guides/actions/ : définir, valider et sécuriser des actions.
- https://docs.astro.build/en/reference/configuration-reference/#security : `security.actionBodySizeLimit` et `security.checkOrigin`.
- https://docs.astro.build/en/reference/configuration-reference/#session : `session.driver` et `session.ttl`.
- https://docs.astro.build/en/reference/modules/astro-actions/ : `ActionError`, codes d'erreur (`BAD_REQUEST`, `UNAUTHORIZED`) et `isInputError()`.
