---
name: audit-seo-contenu
description: Audit SEO du contenu d'un site — adéquation à l'intention de recherche, titles et meta descriptions, structure Hn, contenus faibles ou dupliqués, cannibalisation entre pages, maillage et ancres, E-E-A-T (auteurs, preuves, à propos), fraîcheur, pages légales, SEO local — avec réécritures proposées page par page. Utilise ce skill quand l'utilisateur veut améliorer ses textes pour Google, se demande pourquoi une page ne se positionne pas, veut une stratégie de contenu, des idées d'articles, optimiser ses titles/metas ou « mieux ranker », pour un site Astro ou tout autre site.
---

# Audit contenu SEO

Format : `../audit-complet/references/format-constat.md`. Sortie : `rapports/seo-contenu.md`.

## Données
- `data/crawl/pages.json` : title, meta_description, h1, headings (H1 à H6), content_words, inlinks, inlink_anchors, jsonld_types, dates.
- `data/crawl/issues.json` : `title_*`, `desc_*`, `h1_*`, `thin_content`, `near_dup_titles`.
- Le **contenu réel** : lire les pages (HTML rendu via `curl`, ou la source : fichiers `.md`/`.mdx`, collections de contenu Astro, ou données Convex du CMS).
- Contexte business : activité, cibles, requêtes visées (demandées au cadrage). Sans cela, déduire des pages principales et le dire.
- Si l'utilisateur fournit un export Search Console (requêtes × pages, 3 à 16 mois), c'est la meilleure source : l'utiliser pour la cannibalisation et les opportunités (positions 5 à 20, fort volume d'impressions, CTR faible).

## Sélection des pages à lire
Ne pas tout lire. Prendre : l'accueil, 1 ou 2 pages par gabarit (formation, métier, compétence, outil, article, catégorie), les pages business (offres, tarifs, contact), les 5 articles les plus liés et les 5 moins liés. Soit 15 à 25 pages.

## Checklist par page
1. **Intention** : quelle requête principale la page doit-elle gagner ? L'intention (informer, comparer, acheter, s'inscrire, se localiser) correspond-elle au format de la page ? Une page par intention.
2. **Title** (≈ 50-60 caractères) : requête principale au début, bénéfice ou élément différenciant, marque en fin si la place le permet. « Accueil » seul = title perdu.
3. **Meta description** (≈ 140-155 caractères) : promesse + preuve + appel à l'action. Unique par page.
4. **H1** unique, proche du title sans le copier. **H2/H3** qui découpent la page en questions et sous-thèmes réels. Pas de niveaux sautés par design (sinon Lighthouse et l'accessibilité le signalent).
5. **Profondeur** : le contenu couvre-t-il ce qu'un lecteur attend (prix, durée, prérequis, débouchés, financement, comparatifs, exemples, FAQ) ? Moins de 300 mots n'est pas un problème pour contact ou mentions légales, c'en est un pour une page formation ou métier.
6. **Preuves / E-E-A-T** : chiffres sourcés, cas concrets, avis vérifiables, formateurs ou auteurs nommés avec leur parcours, certifications (ex. Qualiopi, RNCP/RS pour la formation), date de mise à jour visible sur les contenus qui vieillissent.
7. **Maillage sortant** : 3 à 8 liens contextuels vers les pages sœurs et business, avec des ancres descriptives (pas « cliquez ici »).
8. **Appel à l'action** clair et placé au bon moment (SEO et conversion vont ensemble).

## Checklist site
- **Cannibalisation** : `near_dup_titles` + lecture. Deux pages visent la même requête → fusionner (301), différencier les intentions, ou désigner une page principale et faire pointer les autres vers elle. Cas typique : un article « devenir X » et une page métier « X » qui se font concurrence.
- **Contenus faibles ou dupliqués** : gabarits dynamiques où seul le nom change (pages outils/compétences générées) → enrichir avec du contenu propre à chaque page, ou `noindex` si la page n'a pas de valeur seule.
- **Pages de confiance** : à propos / équipe / formateurs, contact complet, mentions légales (obligatoires en France, LCEN), politique de confidentialité (RGPD), CGV si vente, page avis/témoignages.
- **Fraîcheur** : contenus datés (« en 2024 ») ou chiffres périmés ; articles sans `dateModified`.
- **Couverture thématique** : lister les sujets attendus par les cibles et absents du site. En déduire un plan de contenu de 8 à 15 sujets (requête visée, intention, format, page cible du maillage).
- **SEO local** (si adresse physique ou zone d'intervention) : NAP identique partout (nom, adresse, téléphone), fiche Google Business Profile, schema LocalBusiness ou EducationalOrganization, pages locales seulement si elles apportent un vrai contenu local.

## Livrables concrets (c'est ce qui rend l'audit utile)
- **Tableau de réécriture** des titles et metas pour les pages sélectionnées : URL | actuel | proposé | pourquoi.
- **Plan d'enrichissement** des 5 pages business prioritaires : sections à ajouter (H2 proposés), preuves à fournir, liens internes à créer (source → cible → ancre).
- **Plan de contenu** : sujets priorisés, avec la page business que chaque article doit alimenter.
- Où modifier : identifier la source de chaque texte (fichier `.astro`/`.md` avec son chemin, ou document Convex du CMS : table et champ) pour que l'agent sache où appliquer.

## Restitution
`rapports/seo-contenu.md` : constats `CONT-NNN` au format commun, puis les trois livrables ci-dessus en annexes.
