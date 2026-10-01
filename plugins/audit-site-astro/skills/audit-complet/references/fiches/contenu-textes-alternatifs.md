---
id: contenu-textes-alternatifs
titre: Images sans texte alternatif (attribut alt)
domaine: Contenu
severite_type: moyenne
effort: M
declencheurs:
  - "crawl:img_no_alt"
  - "code:\\d+ <img> sans attribut alt"
  - "lighthouse:image-alt|n'ont pas d'attributs .?\\[alt\\]"
sources:
  - https://developers.google.com/search/docs/appearance/google-images
  - https://docs.astro.build/en/guides/images/
  - https://www.w3.org/WAI/tutorials/images/decision-tree/
---

# Images sans texte alternatif (attribut alt)

> **En une phrase** : des images n'ont pas d'attribut `alt`, donc elles sont muettes pour Google Images, les lecteurs d'écran et les IA.

## Pourquoi c'est important

L'attribut `alt` décrit l'image à ceux qui ne la voient pas (déficience visuelle, image non chargée) et à Google, qui s'en sert avec le texte environnant pour comprendre l'image et la classer dans Google Images. Google recommande un texte court, descriptif, en rapport avec la page, sans bourrage de mots-clés. Sans `alt`, un lecteur d'écran lit le nom du fichier (`IMG_2043.jpg`), et une image cliquable (logo, bouton) devient un lien sans nom. Attention à la nuance : l'outil signale l'absence de l'attribut, pas un `alt=""` vide, qui est **correct** pour une image purement décorative. Cette fiche traite la qualité du texte ; les aspects lecteurs d'écran sont dans les fiches d'accessibilité.

## Comment le constater soi-même

```bash
# pages et nombre d'images sans alt vus par le crawler
python3 -c "import json;d=json.load(open('data/crawl/issues.json'));[print(e['n'],e['url']) for e in d['img_no_alt']['examples']]"
# dans le code : balises img sans alt
grep -rnE "<img\b" src --include=*.astro --include=*.tsx --include=*.jsx --include=*.mdx | grep -v "alt=" | head -30
# dans le Markdown : images avec texte vide
grep -rn '!\[\](' src/content | head
```

Présent : des lignes retournées. Corrigé : aucune `<img>` sans `alt`.

## Correction

1. **Composants d'image Astro** : `<Image>` et `<Picture>` d'`astro:assets` exigent `alt` et le build signale son oubli. Une `<img>` brute n'a pas cette protection : la convertir en `<Image>` (bénéfice supplémentaire : redimensionnement et formats modernes).

```astro
---
import { Image } from 'astro:assets';
import formateur from '../assets/formateur-marie-dupont.jpg';
---
<Image src={formateur} alt="Marie Dupont, formatrice Excel, animant une session à Lyon" width={800} height={533} />
```

2. **Choisir le texte selon le rôle de l'image** (arbre de décision W3C) :

| Rôle | Que mettre dans `alt` | Exemple |
|---|---|---|
| Informative (photo d'équipe, schéma, capture) | Ce que l'image apprend, en 5 à 15 mots, sans « image de » | `Tableau croisé dynamique montrant les ventes par région` |
| Logo qui est un lien | Le nom de la destination | `Exemple, retour à l'accueil` |
| Icône à côté d'un texte identique | `alt=""` (redondant) | `alt=""` |
| Purement décorative (fond, filet, ornement) | `alt=""` | `alt=""` |
| Graphique porteur de données | Résumé du message et données dans le texte voisin | `Hausse de 40 % des inscriptions entre 2024 et 2025` (seulement si c'est vrai et sourcé dans la page) |

   Ne jamais décrire ce que l'agent ne voit pas : si l'image ne peut pas être vue, demander la description au propriétaire au lieu de deviner. Pas de nom de fichier, pas de liste de mots-clés (« formation excel lyon cpf pas cher »).
3. **Collections de contenu** : séparer l'image et son texte dans le schéma (l'assistant `image()` valide le fichier, un champ dédié porte le `alt`) :

```ts
// src/content.config.ts (extrait ; Astro 6+ : z vient de 'astro/zod')
import { defineCollection } from 'astro:content';
import { glob } from 'astro/loaders';
import { z } from 'astro/zod';

const blog = defineCollection({
  loader: glob({ pattern: '**/*.{md,mdx}', base: './src/content/blog' }),
  schema: ({ image }) => z.object({
    titre: z.string(),
    cover: image(),
    coverAlt: z.string().min(5),   // obligatoire : le build échoue s'il manque
  }),
});
export const collections = { blog };
```

   Puis dans le layout : `<Image src={data.cover} alt={data.coverAlt} />`.
4. **Markdown** : `![Tableau croisé dynamique montrant les ventes par région](./tcd.png)` ; le texte entre crochets devient l'`alt`. Pour une image décorative : `![](./filet.svg)` est acceptable.
5. **Convex (CMS)** : chaque champ image (identifiant de stockage) a un champ frère `xxxAlt` (`v.optional(v.string())`) ; l'éditeur doit le renseigner à l'envoi. Côté Astro : `alt={doc.imageAlt ?? ""}` évite un attribut absent, mais un `alt` vide n'est correct que pour une image décorative : renseigner les vrais textes.
6. **Images d'un composant React/Vue/Svelte** (`<img>` en JSX) : la règle est la même ; `alt` en propriété obligatoire du composant (`alt: string` dans les props TypeScript).

## Critères d'acceptation

- [ ] Aucune `<img>` sans attribut `alt` dans le HTML rendu.
- [ ] Les images informatives ont un `alt` descriptif de 5 à 15 mots, propre à la page.
- [ ] Les images décoratives ont `alt=""`.
- [ ] Pas de nom de fichier ni de liste de mots-clés dans les `alt`.
- [ ] Le schéma de collection ou de layout rend le `alt` obligatoire ; build OK.

## Vérification après correction

```bash
npx astro check && npx astro build
grep -rnE "<img\b" dist --include=*.html | grep -v "alt=" | head      # ne doit rien lister
python3 scripts/crawl_site.py https://SITE/ --out /tmp/verif/crawl
python3 -c "import json;d=json.load(open('/tmp/verif/crawl/issues.json'));print(d.get('img_no_alt',{}).get('count',0))"   # attendu : 0
```

## Pièges et retour arrière

- Ne pas remplir `alt` avec le titre de la page sur toutes les images : c'est du bruit pour un lecteur d'écran.
- Un `alt=""` posé par facilité sur une image informative masque l'information : le réserver au décoratif.
- Les images en fond CSS (`background-image`) n'ont pas d'`alt` : si elles portent une information, la mettre en texte.
- Retour arrière : `git revert` ; aucun effet visuel.

## Pour aller plus loin

- https://developers.google.com/search/docs/appearance/google-images : texte alternatif et bonnes pratiques Google Images.
- https://docs.astro.build/en/guides/images/ : `alt` obligatoire sur `<Image>`/`<Picture>`, `alt=""` décoratif, champ `coverAlt`.
- https://www.w3.org/WAI/tutorials/images/decision-tree/ : que mettre dans `alt` selon le rôle de l'image.
