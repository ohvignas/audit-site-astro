---
id: geo-sameas-absent
titre: Aucun sameAs (profils officiels de la marque non déclarés)
domaine: GEO / IA
severite_type: moyenne
effort: S
declencheurs:
  - "geo:Aucun sameAs"
sources:
  - https://schema.org/sameAs
  - https://developers.google.com/search/docs/appearance/structured-data/organization
  - https://www.wikidata.org/wiki/Wikidata:Notability
---

# Aucun sameAs

> **En une phrase** : le JSON-LD ne relie pas le site à ses profils officiels (LinkedIn, Google Business Profile, YouTube, annuaires…), ce qui affaiblit l'identification de la marque.

## Pourquoi c'est important

`sameAs` indique « cette entité, c'est aussi celle-ci ailleurs sur le web » (schema.org). Les moteurs et assistants IA recoupent plusieurs sources pour décider si une marque existe et si elle est fiable : lier le site à ses profils vérifiés les aide à les rapprocher. Le signal est modeste mais gratuit. Il n'a de valeur que si les profils **existent réellement**, sont tenus à jour et mentionnent le même nom que le site (voir `geo-entite-doublons-nom-marque`). Pour une IA, la présence de la marque hors du site (avis, annuaires, presse) compte souvent plus que la balise elle-même : c'est un travail éditorial, pas de code.

## Comment le constater soi-même

```bash
curl -s https://SITE/ | grep -o '"sameAs"[^]]*]' | head
grep -rn "sameAs" src/ | head
```

Problème présent : aucun résultat, ou `sameAs` vide. Corrigé : une liste d'URL de profils qui répondent 200.

## Correction

1. Faire l'inventaire **avec le propriétaire** des profils qui existent : page LinkedIn de l'entreprise, fiche Google Business Profile (lien de partage de la fiche), chaîne YouTube, Instagram/Facebook/X si actifs, annuaires sectoriels réels, fiche Wikidata ou Wikipédia **seulement si elle existe déjà** (critères de notoriété stricts : ne pas en créer une promotionnelle).
2. Ajouter ces URL au fichier d'identité défini dans `geo-entite-organization-jsonld` :

```ts
// src/lib/entite.ts (extrait)
export const ENTITE = {
  // ...
  sameAs: [
    'https://www.linkedin.com/company/exemple',
    'https://www.youtube.com/@exemple',
    'https://www.wikidata.org/wiki/Q000000', // seulement si l'élément existe vraiment
  ],
};
```

   Le composant du layout injecte déjà `sameAs: ENTITE.sameAs`. Sans cette fiche appliquée, suivre d'abord `geo-entite-organization-jsonld`.
3. Pour une personne (fondateur, auteur), ajouter le même mécanisme à un bloc `Person` : `sameAs` avec son profil LinkedIn.
4. Afficher aussi ces liens dans le pied de page en HTML (`<a rel="me noopener" href="https://www.linkedin.com/company/exemple">LinkedIn</a>`) : les profils doivent renvoyer vers le site en retour (lien du site dans la bio).
5. Vérifier chaque URL avant publication.

```bash
for u in https://www.linkedin.com/company/exemple https://www.youtube.com/@exemple; do
  printf '%s ' "$(curl -s -o /dev/null -w '%{http_code}' -A 'Mozilla/5.0' "$u")"; echo "$u"
done
```

   Note : LinkedIn répond parfois 999 aux scripts ; ouvrir le lien dans un navigateur dans ce cas.

## Critères d'acceptation

- [ ] `sameAs` contient au moins 2 profils officiels réels (ou 1 s'il n'en existe qu'un)
- [ ] Chaque URL ouvre le bon profil dans un navigateur
- [ ] Les profils mentionnent le même nom de marque et un lien vers le site
- [ ] Aucune URL inventée, aucun profil d'un homonyme

## Vérification après correction

```bash
curl -s https://SITE/ | grep -o '"sameAs"[^]]*]'
python3 scripts/geo_check.py https://SITE/ --out /tmp/verif/geo --sample 6
grep -i 'sameas' /tmp/verif/geo/geo-summary.md
```

## Pièges et retour arrière

- Ne pas lister un profil abandonné ou vide : il envoie un mauvais signal.
- Ne pas y mettre des pages de simples annuaires sans rapport avec l'entreprise.
- Retour arrière : retirer l'entrée de `ENTITE.sameAs`.

## Pour aller plus loin

- https://schema.org/sameAs : définition de la propriété.
- https://developers.google.com/search/docs/appearance/structured-data/organization : Google lit `sameAs` pour l'organisation.
- https://www.wikidata.org/wiki/Wikidata:Notability : critères d'admission dans Wikidata.
