---
id: seo-contenu-mixte-https
titre: Contenu mixte — ressources http:// chargées sur des pages https
domaine: SEO technique
severite_type: haute
effort: S
declencheurs:
  - "crawl:mixed_content"
sources:
  - https://developer.mozilla.org/en-US/docs/Web/Security/Mixed_content
  - https://web.dev/articles/what-is-mixed-content
  - https://developers.google.com/search/docs/crawling-indexing/site-move-with-url-changes
---

# Contenu mixte — ressources http:// chargées sur des pages https

> **En une phrase** : des pages en https chargent encore des images, scripts ou styles en `http://`, que les navigateurs bloquent ou signalent.

## Pourquoi c'est important

Les navigateurs modernes bloquent le contenu mixte actif (scripts, feuilles de style, iframes) et mettent à niveau ou signalent le contenu passif (images, audio, vidéo). Résultat : éléments manquants, cadenas retiré, avertissements, et un signal de qualité dégradé. Une ressource en `http://` est aussi une fuite potentielle (un tiers non chiffré peut la modifier). La cause est presque toujours une URL écrite en dur avec `http://` dans un composant, du contenu Markdown, ou une donnée saisie dans Convex ou un CMS.

## Comment le constater soi-même

```bash
# Ressources http:// dans le HTML servi
curl -s https://SITE/page/ | grep -oE '(src|href|srcset|content)="http://[^"]+' | head
# Dans le code et les données
grep -rnE '(src|href)="http://' src/ public/ | head
grep -rn 'http://' src/content/ convex/ 2>/dev/null | grep -v 'w3.org\|sitemaps.org\|schema.org' | head
```

`data/crawl/issues.json` (clé `mixed_content`) donne la page et les 5 premières ressources.

## Correction

1. Pour chaque ressource listée, remplacer `http://` par `https://` (vérifier que l'hôte la sert bien en https : `curl -sI https://hote/fichier`).
2. Si l'hôte ne sert pas en https : héberger le fichier soi-même (images dans `src/assets/` avec `<Image>`, scripts via npm), ou supprimer la ressource.
3. Utiliser des chemins relatifs à la racine (`/images/logo.png`) pour les ressources du site.
4. **Contenu saisi dans une donnée** (Convex, CMS) : corriger la donnée, ou normaliser au rendu :

```ts
// src/lib/https.ts
export function enHttps(url: string): string {
  return url.replace(/^http:\/\//i, 'https://');
}
```

```astro
---
import { enHttps } from '../lib/https';
const { image } = Astro.props;
---
<img src={enHttps(image.url)} alt={image.alt} width={image.width} height={image.height} />
```

5. Les URL des espaces de noms (`http://www.w3.org/2000/svg`, `http://schema.org` dans du JSON-LD ancien) ne sont pas des ressources chargées : ne pas les modifier.
6. En complément, une politique CSP avec `upgrade-insecure-requests` peut mettre à niveau automatiquement les requêtes restantes (voir le domaine Sécurité). C'est un filet de sécurité, pas une correction de fond.
7. Vérifier `site` et l'origine des URL générées par le code (fiche `seo-astro-site-et-proxy`) : une origine `http://` construite depuis la requête produit exactement ce défaut.

## Critères d'acceptation

- [ ] Aucune requête `http://` sur les pages https (console du navigateur sans « Mixed Content »)
- [ ] `mixed_content` = 0 dans le crawl
- [ ] Toutes les ressources tierces sont servies en https et répondent 200
- [ ] Aucune régression : images et scripts toujours affichés

## Vérification après correction

```bash
curl -s https://SITE/page/ | grep -cE '(src|href)="http://'      # attendu : 0
python3 scripts/crawl_site.py https://SITE/ --out /tmp/verif       # mixed_content
```

Ouvrir la page dans le navigateur, console développeur : aucune erreur « Mixed Content ».

## Pièges et retour arrière

- Ne pas remplacer aveuglément `http://` par `https://` dans tout le dépôt : certaines URL (espaces de noms XML, liens de documentation) doivent rester telles quelles.
- Une ressource externe qui n'existe pas en https doit être remplacée, pas seulement réécrite.
- Retour arrière : `git revert` ; pour une donnée Convex, garder une copie avant la modification en masse.

## Pour aller plus loin

- https://developer.mozilla.org/en-US/docs/Web/Security/Mixed_content : types de contenu mixte et comportement des navigateurs.
- https://web.dev/articles/what-is-mixed-content : diagnostic et correction.
- https://developers.google.com/search/docs/crawling-indexing/site-move-with-url-changes : bonnes pratiques de migration http vers https.
