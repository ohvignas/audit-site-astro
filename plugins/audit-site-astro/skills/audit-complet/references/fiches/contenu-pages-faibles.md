---
id: contenu-pages-faibles
titre: Pages au contenu trop court ou sans valeur propre
domaine: Contenu
severite_type: moyenne
effort: L
declencheurs:
  - "crawl:thin_content"
sources:
  - https://developers.google.com/search/docs/fundamentals/creating-helpful-content
  - https://developers.google.com/search/docs/essentials/spam-policies
  - https://developers.google.com/search/docs/crawling-indexing/block-indexing
  - https://docs.astro.build/en/guides/content-collections/
---

# Pages au contenu trop court ou sans valeur propre

> **En une phrase** : des pages indexables contiennent moins de 300 mots dans leur zone principale, donc elles répondent mal à la recherche et peuvent tirer le site vers le bas si elles sont nombreuses et interchangeables.

## Pourquoi c'est important

Google ne compte pas les mots, mais il cherche du contenu utile, fait pour les gens, qui apporte plus que les autres résultats. Une page formation ou service de 120 mots (titre, un paragraphe, un bouton) n'explique ni le prix, ni la durée, ni le public, ni les débouchés : l'internaute repart et la page ne se positionne pas. Le pire cas est celui des pages générées en série (une par ville, par outil, par compétence) où seul le nom change : Google les traite comme du contenu de faible valeur, voire comme du spam si elles sont produites à grande échelle sans valeur ajoutée. Le seuil de 300 mots de l'outil est un signal d'alerte, pas une règle : un contact, des mentions légales ou une page de remerciement sont normalement courts.

## Comment le constater soi-même

```bash
# nombre de mots visibles d'une page (approximatif)
curl -s https://SITE/formations/excel/ | sed 's/<script[^>]*>.*<\/script>//g; s/<style[^>]*>.*<\/style>//g; s/<[^>]*>/ /g' | wc -w
# pages de la collection avec peu de texte (Markdown)
wc -w src/content/formations/*.md | sort -n | head -20
```

Présent : moins de 300 mots sur une page destinée à se positionner. Le détail (URL, mots) est dans `data/crawl/issues.json`, clé `thin_content`.

## Correction

1. **Trier les pages signalées en 3 familles** (lire les URL, ne pas traiter en aveugle) :
   - **Courtes par nature** (contact, mentions légales, remerciement, connexion, panier) : ne rien faire ; ajouter `noindex` pour remerciement, connexion et panier. Écarter du constat.
   - **Pages business trop maigres** (formation, service, métier, offre) : les enrichir.
   - **Pages générées interchangeables** (villes, outils, tags) : enrichir avec du contenu propre à chaque page, sinon `noindex` ou suppression avec redirection 301 vers la page mère.
2. **Enrichir une page formation ou service** avec les sections qu'un visiteur cherche (chacune en H2, contenu réel fourni par le propriétaire, jamais inventé) :

| Type | Sections à couvrir |
|---|---|
| Formation | Objectifs, public et prérequis, programme détaillé, durée et rythme, dates et lieux, modalités d'évaluation, tarif et financement (CPF, OPCO), certification (Qualiopi, RNCP ou RS le cas échéant), formateur, avis, questions fréquentes |
| Service | Problème résolu, méthode en étapes, livrables, délais, tarifs ou fourchettes, exemple client chiffré, questions fréquentes, appel à l'action |
| Métier / débouché | Missions, compétences, salaire indicatif sourcé, formations qui y mènent (liens internes), évolution |
| Ville / lieu | Adresse, accès, sessions réelles dans ce lieu, contact local ; sinon fusionner avec la page mère |

3. **Où ajouter le texte** :
   - Page `.astro` : dans le gabarit de la page, en sections `<section>` ayant chacune un `<h2>` réel (« Programme », « Tarif et financement »…) et un texte fourni par le propriétaire ; ne jamais publier de texte d'exemple.
   - Collection : ajouter des champs typés au schéma plutôt qu'un seul gros champ, pour que chaque fiche soit complète (`src/content.config.ts`, `z.object({ objectifs: z.array(z.string()).min(3), prerequis: z.string(), duree: z.string(), tarif: z.string().optional(), faq: z.array(z.object({ q: z.string(), r: z.string() })).optional() })`), puis afficher ces champs dans le layout.
   - Convex : ajouter les champs correspondants à la table dans `convex/schema.ts` (en `v.optional(...)` d'abord, puis obligatoires une fois les données migrées), et les afficher dans la page.
4. **Pages générées en série** : garder une page seulement si elle a du contenu unique (donnée locale, avis, chiffres, exemples). Sinon, en Astro, sortir la page de l'index : `<meta name="robots" content="noindex, follow" />` via une prop `noindex` du layout, et l'exclure du sitemap (option `filter` de `@astrojs/sitemap`).

```astro
---
// src/layouts/BaseLayout.astro (extrait)
interface Props { title: string; description: string; noindex?: boolean }
const { title, description, noindex = false } = Astro.props;
---
<head>
  <title>{title}</title>
  <meta name="description" content={description} />
  {noindex && <meta name="robots" content="noindex, follow" />}
</head>
```

```js
// astro.config.mjs (extrait) : retire du sitemap les pages en noindex
import sitemap from '@astrojs/sitemap';
export default {
  site: 'https://exemple.fr',
  integrations: [sitemap({ filter: (page) => !page.includes('/tags/') && !page.includes('/merci') })],
};
```

5. **Ne pas gonfler artificiellement** : pas de texte de remplissage, pas de répétition de mots-clés, pas de contenu copié d'une autre page. Mieux vaut 400 mots utiles que 1 200 de bourrage.

## Critères d'acceptation

- [ ] Chaque page business indexable dépasse 300 mots de contenu propre et couvre les questions listées ci-dessus.
- [ ] Les pages courtes par nature sont soit conservées telles quelles (contact, légal), soit en `noindex` (remerciement, connexion, panier).
- [ ] Les pages générées interchangeables sont enrichies, fusionnées (301) ou en `noindex` et hors sitemap.
- [ ] Aucun texte inventé : chaque chiffre, tarif, certification vient du propriétaire ou d'une source citée.

## Vérification après correction

```bash
python3 scripts/crawl_site.py https://SITE/ --out /tmp/verif/crawl
python3 -c "import json;d=json.load(open('/tmp/verif/crawl/issues.json'));print(d.get('thin_content',{}).get('count',0))"
```

Le nombre doit baisser ; les pages courtes par nature restantes sont attendues (les noter comme écartées dans le rapport).

## Pièges et retour arrière

- `noindex` sur une page qui reçoit du trafic la fait disparaître : vérifier dans Search Console avant.
- Fusionner des pages exige une redirection 301 de l'ancienne URL vers la nouvelle (`redirects` dans `astro.config.mjs`) et la mise à jour des liens internes.
- Ne pas retirer une page du sitemap sans la mettre en `noindex` ou la supprimer : signal contradictoire sinon.
- Retour arrière : `git revert` ; une page en `noindex` redevient indexable en retirant la balise (délai de recrawl de quelques jours).

## Pour aller plus loin

- https://developers.google.com/search/docs/fundamentals/creating-helpful-content : ce que Google appelle un contenu utile.
- https://developers.google.com/search/docs/essentials/spam-policies : contenu généré à grande échelle sans valeur ajoutée.
- https://developers.google.com/search/docs/crawling-indexing/block-indexing : balise `noindex`.
- https://docs.astro.build/en/guides/content-collections/ : champs typés d'une collection.
