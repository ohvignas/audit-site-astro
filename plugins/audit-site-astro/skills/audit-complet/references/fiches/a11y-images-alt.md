---
id: a11y-images-alt
titre: "Images sans texte alternatif ou avec un alt inadapté (absent, redondant, SVG, input image)"
domaine: Accessibilité
severite_type: haute
effort: S
declencheurs:
  - "crawl:img_no_alt"
  - "code:\\d+ <img> sans attribut alt"
  - "lighthouse:image-alt|image-redundant-alt|input-image-alt|svg-img-alt|object-alt"
  - "lighthouse:Des éléments d'image n'ont pas d'attribut|attributs `\\[alt\\]` qui correspondent à du texte redondant|`<input type=\"image\">` ne contiennent pas|SVG avec un rôle `img` n'ont pas|`<object>` ne contiennent pas de texte"
  - "crawl:alt_suspect"
  - "crawl:alt_redondant"
sources:
  - https://www.w3.org/WAI/WCAG22/Understanding/non-text-content.html
  - https://www.w3.org/WAI/tutorials/images/decision-tree/
  - https://docs.astro.build/en/guides/images/#alt-text
  - https://dequeuniversity.com/rules/axe/4.10/image-alt
  - https://accessibilite.numerique.gouv.fr/methode/criteres-et-tests/#1.1
---

# Images sans texte alternatif ou avec un alt inadapté (absent, redondant, SVG, input image)

> **En une phrase** : des images n'ont pas de description pour les lecteurs d'écran, ou ont une description qui répète le texte voisin, ou sont des SVG sans nom ; c'est aussi une perte pour le référencement des images.

## Pourquoi c'est important

Une image sans attribut `alt` est annoncée par son nom de fichier (« IMG_4032.jpg ») ou ignorée, et l'information qu'elle porte disparaît pour une personne aveugle. À l'inverse, une image décorative avec un `alt` bavard pollue la lecture. WCAG 1.1.1 (niveau A) et RGAA thématique 1 (Images) l'exigent. L'`alt` sert aussi à Google Images et à l'affichage quand l'image ne charge pas. C'est l'une des corrections les plus rapides et les plus visibles d'un audit d'accessibilité.

## Comment le constater soi-même

```bash
# Balises <img> sans alt dans le code
grep -rnE "<img\b" src --include=*.astro --include=*.tsx --include=*.jsx --include=*.svelte --include=*.vue | grep -v "alt=" | head -30
# Sur le site en ligne
curl -s https://exemple.fr/ | grep -oE '<img[^>]*>' | grep -v ' alt=' | head
```

`alt=""` est valide et voulu pour les images décoratives : ne le comptez pas comme une erreur. Lighthouse donne le sélecteur des images en échec.

## Correction

Pour chaque image, posez la question : « si l'image disparaissait, qu'est-ce qui manquerait à la page ? »

| Cas | Attribut |
|---|---|
| L'image apporte une information (photo produit, schéma, portrait) | `alt="description utile, courte"` |
| Décorative (fond, filet, ambiance) ou déjà décrite par le texte voisin | `alt=""` |
| Image seule dans un lien ou un bouton | `alt` = destination ou action (« Retour à l'accueil ») |
| Graphique complexe | `alt` bref + description détaillée dans le texte ou un tableau |
| Image contenant du texte | `alt` = ce texte, et évitez ce procédé |

1. **Astro `<Image />` / `<Picture />`** : `alt` est obligatoire (le build échoue sans lui). Mettez `alt=""` pour une image décorative.

   ```astro
   ---
   import { Image } from 'astro:assets';
   import portrait from '../assets/portrait.jpg';
   ---
   <Image src={portrait} alt="Claire Martin, formatrice, devant un tableau blanc" />
   <Image src={portrait} alt="" />
   ```
2. **`<img>` brut** : ajoutez `alt` à chaque balise (voir la sortie du `grep`). Ne l'omettez jamais : sans attribut, le lecteur d'écran lit le fichier.
3. **Contenu venant d'un CMS, de Markdown ou de Convex** : rendez le champ `alt` obligatoire dans le schéma.

   ```ts
   // src/content.config.ts
   import { defineCollection, z } from 'astro:content';

   const articles = defineCollection({
     schema: ({ image }) => z.object({
       titre: z.string(),
       couverture: z.object({ src: image(), alt: z.string() /* '' autorisé pour une image décorative */ }),
     }),
   });
   export const collections = { articles };
   ```

   Markdown : `![Description de l'image](./photo.jpg)` ; image décorative : `![](./motif.svg)`.
4. **Alt redondant** (`image-redundant-alt`) : l'image est dans un lien ou à côté d'une légende qui dit déjà la même chose. Mettez `alt=""` ou reformulez.

   ```astro
   <a href="/formations/seo">
     <Image src={vignette} alt="" />   <!-- le texte du lien suffit -->
     Formation SEO
   </a>
   ```
5. **SVG** : SVG informatif → `role="img"` et un nom (`aria-label` ou `<title>`), SVG décoratif → `aria-hidden="true" focusable="false"`.

   ```html
   <svg role="img" aria-label="Note moyenne : 4,8 sur 5" viewBox="0 0 100 20">...</svg>
   <svg aria-hidden="true" focusable="false" viewBox="0 0 24 24">...</svg>
   ```
6. **`<input type="image">`** : `alt` = action du bouton (« Rechercher »). **`<object>`, `<embed>`** : contenu de repli ou `aria-label`.
7. Règles de rédaction : 125 caractères environ au maximum, pas de « image de », « photo de » ; pas de nom de fichier ; ne pas bourrer de mots-clés (nuit à l'accessibilité et au SEO).
8. Cette fiche se recoupe avec la fiche de contenu `contenu-textes-alternatifs` (angle référencement) ; corrigez une fois, les deux constats sont levés.

## Critères d'acceptation

- [ ] Aucune balise `<img>`, `<input type="image">`, `<area>` sans attribut `alt`.
- [ ] Les images décoratives ont `alt=""` ; les informatives ont un texte utile.
- [ ] Lighthouse : « Les éléments d'image possèdent des attributs `[alt]` » et l'audit de texte redondant réussis.
- [ ] Les SVG informatifs ont un nom, les décoratifs sont masqués.
- [ ] Le crawl ne remonte plus `img_no_alt`.

## Vérification après correction

```bash
grep -rnE "<img\b" src | grep -v "alt=" | wc -l        # attendu : 0
python3 scripts/crawl_site.py https://exemple.fr/ --out /tmp/verif-crawl && grep -c img_no_alt /tmp/verif-crawl/*.json || true
python3 scripts/astro_scan.py . --out /tmp/verif-code && grep -i "sans attribut alt" /tmp/verif-code/code-scan.md || echo "constat levé"
```

## Pièges et retour arrière

- Ne remplissez pas les `alt` automatiquement avec le nom du fichier ou le titre de la page : c'est pire qu'un `alt=""` honnête.
- Les images d'arrière-plan CSS (`background-image`) n'ont pas d'alt : si elles portent une information, utilisez une balise `<img>`.
- Retour arrière : retirer l'attribut modifié ; aucun effet visuel.

## Pour aller plus loin

- WCAG 1.1.1 (contenu non textuel) et arbre de décision d'alt du W3C.
- Astro, guide des images : texte alternatif obligatoire.
- Lighthouse, audit `image-alt`.
- RGAA, thématique Images (critères 1.1 à 1.9).
