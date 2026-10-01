---
id: geo-pages-confiance-manquantes
titre: Pages de confiance introuvables (à propos, contact, mentions légales, confidentialité)
domaine: GEO / IA
severite_type: moyenne
effort: M
declencheurs:
  - "geo:Page « (a propos|contact|mentions legales|confidentialite) » introuvable"
sources:
  - https://developers.google.com/search/docs/fundamentals/creating-helpful-content
  - https://www.legifrance.gouv.fr/loda/id/JORFTEXT000000801164/
  - https://docs.astro.build/en/basics/astro-pages/
---

# Pages de confiance introuvables

> **En une phrase** : l'outil n'a trouvé aucune page « à propos », « contact », « mentions légales » ou « confidentialité » parmi les URL explorées ; les IA et les visiteurs ne peuvent pas vérifier qui édite le site, ce qui affaiblit la confiance.

## Pourquoi c'est important

Pour décider de citer une source, un assistant IA (et Google, via les critères E-E-A-T) cherche à savoir **qui** publie, où, et comment le joindre. Une page « à propos » substantielle, une page contact avec des coordonnées réelles, des mentions légales et une politique de confidentialité sont des signaux d'entreprise réelle et fiable. Les mentions légales sont **obligatoires en France** pour un site édité professionnellement (loi LCEN n° 2004-575 du 21 juin 2004 : l'identification de l'éditeur figure à l'article 1-1 dans la version consolidée, elle relevait auparavant de l'article 6-III) ; la politique de confidentialité découle du RGPD dès que des données personnelles sont collectées (formulaire, statistiques, cookies). Ce document n'est pas un avis juridique : faire valider le texte final par le propriétaire ou son conseil.

**Cause fréquente de faux positif** : l'outil détecte ces pages par le **chemin de l'URL** (`a-propos`, `about`, `qui-sommes-nous`, `contact`, `mentions-legales`, `legal-notice`, `confidentialite`, `privacy`, `rgpd`…). Une page existante nommée autrement (`/societe/`, `/legal/`) n'est pas reconnue. Sans crawl préalable, la recherche se limite à quelques slugs et la confidentialité est toujours signalée.

## Comment le constater soi-même

```bash
for p in a-propos contact mentions-legales politique-de-confidentialite; do
  printf '%s ' "$(curl -s -o /dev/null -w '%{http_code}' https://SITE/$p/)"; echo "/$p/"
done
curl -s https://SITE/ | grep -oiE 'href="[^"]*(propos|contact|mentions|confidentialit|privacy|legal)[^"]*"' | sort -u
ls src/pages | grep -iE 'propos|about|contact|mention|confid|privacy|legal'
```

Présent (problème) : `404` sur les quatre slugs et aucun lien dans le pied de page. Corrigé : `200` et liens visibles en pied de page.

## Correction

1. Créer une branche Git. Lister avec le propriétaire les informations réelles (raison sociale, forme juridique, capital, SIREN/SIRET, adresse du siège, e-mail, téléphone, directeur de la publication, hébergeur, TVA intracommunautaire, référence d'assurance/ordre professionnel le cas échéant).
2. Créer les pages dans `src/pages/`, avec des slugs reconnus par l'outil :

| Page | Fichier | Contenu minimal |
|---|---|---|
| À propos | `src/pages/a-propos.astro` | Qui vous êtes, histoire, équipe (noms, postes, photos), chiffres, certifications, presse, méthode |
| Contact | `src/pages/contact.astro` | Adresse, e-mail, téléphone, horaires, formulaire ou moyen de contact |
| Mentions légales | `src/pages/mentions-legales.astro` | Identité de l'éditeur, directeur de publication, hébergeur (nom, adresse, téléphone) |
| Confidentialité | `src/pages/politique-de-confidentialite.astro` | Données collectées, finalités, base légale, durée, droits (accès, rectification, effacement), contact, cookies |

```astro
---
// src/pages/mentions-legales.astro
import Base from '../layouts/Base.astro';
---
<Base titre="Mentions légales" description="Informations légales sur l'éditeur et l'hébergeur du site exemple.fr.">
  <main>
    <h1>Mentions légales</h1>
    <h2>Éditeur du site</h2>
    <p>Exemple SAS, capital de 10 000 €, RCS Lyon 000 000 000, 1 rue Exemple, 69000 Lyon.</p>
    <p>Directrice de la publication : Marie Dupont, contact@exemple.fr</p>
    <h2>Hébergeur</h2>
    <p>Nom de l'hébergeur, adresse, téléphone.</p>
  </main>
</Base>
```

   Remplacer tous les exemples par les vraies informations : ne pas laisser de champ fictif en ligne.
3. **Lier** ces pages depuis le pied de page de tous les gabarits (`src/components/Footer.astro`) et les inclure dans le sitemap (elles le sont automatiquement avec `@astrojs/sitemap` si elles ne sont pas exclues).
4. Page « à propos » : donner des preuves (années d'expérience, clients, chiffres, adresse, équipe avec liens LinkedIn), y relier l'entité (`Organization`, voir `geo-entite-organization-jsonld`) et les auteurs (`geo-articles-auteur-date-maj`).
5. Si ces pages existent sous d'autres URL : ne pas les renommer à la légère (redirections 301 dans `astro.config.mjs` → `redirects`) ; l'intérêt est d'abord humain. Le signalement peut alors être un faux positif à documenter.
6. Politique de confidentialité : refléter les traitements **réels** (formulaires, outils d'analyse, cookies). Ne pas copier un texte générique qui décrit des traitements inexistants.

## Critères d'acceptation

- [ ] Les quatre pages répondent `200`, sont indexables (pas de `noindex`) et liées depuis le pied de page
- [ ] Les informations légales sont réelles, complètes et validées par le propriétaire
- [ ] La page « à propos » présente l'entreprise et son équipe avec des éléments vérifiables
- [ ] Aucune régression : build OK, liens du pied de page valides (pas de 404)

## Vérification après correction

```bash
for p in a-propos contact mentions-legales politique-de-confidentialite; do printf '%s ' "$(curl -s -o /dev/null -w '%{http_code}' https://SITE/$p/)"; echo "/$p/"; done
python3 scripts/crawl_site.py https://SITE/ --out /tmp/verif/crawl --max-pages 150
python3 scripts/geo_check.py https://SITE/ --out /tmp/verif/geo --crawl /tmp/verif/crawl/pages.json --sample 8
grep -iE 'introuvable|Pages de confiance' -A8 /tmp/verif/geo/geo-summary.md
```

## Pièges et retour arrière

- Ne pas mettre de mentions légales inexactes : c'est plus risqué que de ne pas en avoir.
- Un `trailingSlash` différent de celui des liens crée des redirections : garder des liens cohérents avec `trailingSlash` de `astro.config.mjs`.
- Retour arrière : supprimer les fichiers de `src/pages/` et les liens du pied de page (Git).

## Pour aller plus loin

- https://developers.google.com/search/docs/fundamentals/creating-helpful-content : qui, comment et pourquoi du contenu.
- https://www.legifrance.gouv.fr/loda/id/JORFTEXT000000801164/ : loi pour la confiance dans l'économie numérique (LCEN), texte consolidé (identité de l'éditeur, article 1-1).
- https://docs.astro.build/en/basics/astro-pages/ : création de pages Astro.
