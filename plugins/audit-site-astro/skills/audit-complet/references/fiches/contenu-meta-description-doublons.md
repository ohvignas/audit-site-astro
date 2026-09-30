---
id: contenu-meta-description-doublons
titre: Plusieurs pages ont la même meta description
domaine: Contenu
severite_type: moyenne
effort: M
declencheurs:
  - "crawl:desc_dup"
sources:
  - https://developers.google.com/search/docs/appearance/snippet
  - https://docs.astro.build/en/guides/content-collections/
---

# Plusieurs pages ont la même meta description

> **En une phrase** : une même phrase de présentation sert à plusieurs pages, souvent celle du site entier, donc aucune ne se distingue dans Google.

## Pourquoi c'est important

Google le dit explicitement : des descriptions identiques ou proches sur toutes les pages d'un site n'aident pas l'internaute quand chaque page s'affiche seule dans les résultats. Dans la pratique, Google ignore alors la description et prend un extrait du texte, ce qui fait perdre le contrôle du message. Sur un site Astro, la cause typique est une valeur par défaut dans le layout (`description = "Bienvenue sur Exemple…"`) utilisée par toutes les pages qui n'en transmettent pas.

## Comment le constater soi-même

```bash
grep -rn "description" src/layouts/*.astro | head
# descriptions des pages du sitemap, regroupées
curl -s https://SITE/sitemap-0.xml | grep -o '<loc>[^<]*</loc>' | sed 's/<[^>]*>//g' | while read u; do
  printf '%s\t%s\n' "$(curl -s "$u" | grep -io '<meta name="description" content="[^"]*"' | sed 's/.*content="//;s/"$//')" "$u"
done | sort | awk -F'\t' '{c[$1]++} END {for (d in c) if (c[d]>1) print c[d] " x " substr(d,1,90)}'
```

Présent : des lignes « N x … ». Corrigé : aucune sortie. Le détail figure dans `data/crawl/issues.json`, clé `desc_dup`.

## Correction

1. **Supprimer le repli global.** Dans `src/layouts/BaseLayout.astro`, une valeur par défaut du type `description = "Bienvenue sur Exemple"` est la cause. Rendre la prop obligatoire :

```astro
---
interface Props { title: string; description: string }
const { title, description } = Astro.props;
---
```

   Puis `npx astro check` liste toutes les pages qui n'en transmettent pas : elles sont à traiter.
2. **Pages générées depuis des données** : composer la description avec ce qui distingue la page (nom, durée, ville, niveau, tarif). Exemple pour une collection `formations` :

```ts
// src/utils/seo.ts
export function descriptionFormation(d: { titre: string; duree: string; ville?: string; financement?: string }): string {
  const lieu = d.ville ? ` à ${d.ville}` : "";
  const fin = d.financement ? ` ${d.financement}.` : "";
  return `${d.titre} : formation de ${d.duree}${lieu}.${fin} Consultez le programme, les dates et le tarif.`;
}
```

   La page l'utilise seulement si le champ `seoDescription` du frontmatter (ou du document Convex) est vide : `description={entry.data.seoDescription ?? descriptionFormation(entry.data)}`. Les champs `duree`, `ville`, `financement` doivent exister dans le schéma de collection (`src/content.config.ts`) ou la table Convex ; ne pas inventer une valeur absente.
3. **Pages listées ou paginées** (catégories, `/blog/2/`) : une description propre à la liste (« Articles sur Excel : … ») et, pour les pages 2 et suivantes, le numéro (« page 2 »).
4. **Pages dont le contenu est réellement identique** (deux URL pour le même texte) : ce n'est pas un problème de description mais de doublon, à régler par une redirection 301 ou une canonical (voir `contenu-cannibalisation`).
5. **Convex** : pour trouver les doublons dans le CMS, regrouper `seoDescription` (ou le repli) par valeur comme dans `contenu-title-doublons`, puis renseigner les champs manquants avec une `internalMutation` lancée via `npx convex run` (pas de mutation publique sans authentification).

## Critères d'acceptation

- [ ] Aucune paire de pages indexables avec la même meta description.
- [ ] `description` est une prop obligatoire du layout ; `npx astro check` passe.
- [ ] Les descriptions générées contiennent un élément propre à la page (nom, durée, ville, niveau).
- [ ] Build OK, pages clés en 200.

## Vérification après correction

```bash
npx astro check && npx astro build
python3 scripts/crawl_site.py https://SITE/ --out /tmp/verif/crawl
python3 -c "import json;d=json.load(open('/tmp/verif/crawl/issues.json'));print(d.get('desc_dup',{}).get('count',0))"   # attendu : 0
```

## Pièges et retour arrière

- Une description générée par gabarit reste acceptable pour des centaines de fiches, mais vérifier qu'elle est lisible par un humain (pas de « undefined », de double point, de champ vide).
- Ne pas changer un mot pour « faire différent » : le but est une description utile à cette page.
- Retour arrière : `git revert` ; le texte seul est concerné.

## Pour aller plus loin

- https://developers.google.com/search/docs/appearance/snippet : descriptions distinctes par page, génération programmatique acceptée si lisible.
- https://docs.astro.build/en/guides/content-collections/ : champs de schéma pour piloter les textes SEO.
