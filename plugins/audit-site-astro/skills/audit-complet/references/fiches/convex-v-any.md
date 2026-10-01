---
id: convex-v-any
titre: Validateur v.any() dans le schéma ou les arguments Convex
domaine: Code
severite_type: basse
effort: S
declencheurs:
  - "code:validateur\\(s\\) v\\.any\\(\\)"
sources:
  - https://docs.convex.dev/functions/validation
  - https://docs.convex.dev/database/schemas
---

# Validateur v.any() dans le schéma ou les arguments Convex

> **En une phrase** : `v.any()` désactive la vérification de type pour un champ ou un argument : n'importe quelle valeur est acceptée et TypeScript ne protège plus le code qui l'utilise.

## Pourquoi c'est important

Sur un argument de fonction publique, `v.any()` rend la validation inutile : l'appelant envoie ce qu'il veut. Sur un champ du schéma, il autorise des données incohérentes qui cassent plus tard l'affichage ou les requêtes, et fait perdre l'autocomplétion. C'est souvent un raccourci pris « en attendant », resté en place.

## Comment le constater soi-même

```bash
grep -rn "v\.any()" convex --include=*.ts | grep -v _generated
```

Chaque ligne est un candidat. Pour chacune, demander : quelles formes de valeur sont réellement possibles ?

## Correction

1. Déterminer la forme réelle de la donnée (regarder les valeurs en base via le tableau de bord Convex, ou l'usage dans le code).
2. Remplacer par un validateur précis :
   ```ts
   // Avant
   leads: defineTable({ email: v.string(), source: v.any() }),

   // Après : les sources connues, sous forme d'union de littéraux
   leads: defineTable({
     email: v.string(),
     source: v.union(v.literal('site'), v.literal('salon'), v.literal('parrainage')),
   }),
   ```
   Autres cas : objet libre à clés inconnues → `v.record(v.string(), v.string())` ; tableau → `v.array(v.string())` ; structure imbriquée → `v.object({...})` ; absence possible → `v.optional(...)` ; deux formes → `v.union(...)`.
3. **Si des documents existants ne respectent pas le nouveau validateur**, le déploiement du schéma échoue (Convex vérifie les données existantes). Procéder ainsi :
   - passer d'abord temporairement le champ en `v.optional(...)` ou en union large, et le pousser sur le déploiement de développement (`npx convex dev --once`) ;
   - corriger les documents avec une migration (mutation interne qui parcourt la table par lots avec `.paginate()`, voir le skill `convex-migration-helper`), mise au point sur le déploiement de développement ;
   - resserrer ensuite le validateur.

   En production, chaque étape (déploiement du schéma, exécution de la migration, qui modifie des données) est lancée **par l'humain**, dans cet ordre et après sauvegarde : lui remettre la liste des commandes, ne pas les exécuter.
4. Cas où `v.any()` reste légitime (charge utile JSON de webhook stockée telle quelle) : le limiter au champ de stockage, ne jamais l'utiliser dans `args` d'une fonction publique, et parser/valider avant usage.

## Critères d'acceptation

- [ ] Plus aucun `v.any()` dans `args` d'une fonction publique
- [ ] Les champs du schéma ont un type précis, ou une exception `v.any()` est commentée dans le code
- [ ] `npx convex dev --once` déploie le schéma sans erreur de validation des données existantes
- [ ] Aucune régression : les écrans qui lisent ces champs affichent les mêmes données

## Vérification après correction

```bash
grep -rn "v\.any()" convex --include=*.ts | grep -v _generated | wc -l
npx convex dev --once
python3 scripts/astro_scan.py . --out /tmp/verif
```

## Pièges et retour arrière

- Un validateur plus strict fait échouer le déploiement si la base contient déjà des valeurs qui n'y correspondent pas : demander à l'humain d'exporter une sauvegarde de la production (`npx convex export --prod --path sauvegarde.zip`) avant.
- Les types TypeScript changent : les appelants qui passaient une valeur libre doivent être corrigés.
- Retour arrière : restaurer le validateur précédent (`git revert`) et le pousser sur le déploiement de développement ; la production est redéployée par l'humain.

## Pour aller plus loin

- https://docs.convex.dev/functions/validation : liste des validateurs (`v.union`, `v.literal`, `v.record`, `v.object`…).
- https://docs.convex.dev/database/schemas : définir et faire évoluer le schéma d'une table.
