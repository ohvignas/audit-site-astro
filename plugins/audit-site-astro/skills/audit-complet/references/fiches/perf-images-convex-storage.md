---
id: perf-images-convex-storage
titre: Images du storage Convex (ou d'un CMS) servies en fichier original
domaine: Performance
severite_type: haute
effort: M
declencheurs:
  - "code:Images servies directement depuis le storage Convex"
  - "http:fichier original servi tel quel"
sources:
  - https://docs.astro.build/en/guides/images/
  - https://docs.astro.build/en/reference/configuration-reference/#imageremotepatterns
  - https://docs.convex.dev/file-storage/serve-files
---

# Images du storage Convex (ou d'un CMS) servies en fichier original

> **En une phrase** : les images téléversées par les utilisateurs ou l'équipe et stockées dans Convex sont envoyées telles quelles (souvent 2 à 8 Mo), sans redimensionnement ni compression.

## Pourquoi c'est important

Le storage Convex renvoie le fichier exactement comme il a été envoyé. Une photo de téléphone (4000 x 3000 px, 3 Mo) affichée dans une vignette de 300 px pèse dix fois trop et bloque le chargement. Lighthouse le montre en Mo sous « Dimensionnez correctement les images » et « formats nouvelle génération ». C'est souvent la première cause d'un LCP catastrophique sur un site à contenu géré par les utilisateurs. Astro sait optimiser des images distantes, mais seulement si leur domaine est autorisé.

## Comment le constater soi-même

```bash
# Repérer les images du storage dans le HTML
curl -s https://SITE/ | grep -oE '(src|srcset)="[^"]*(convex\.(cloud|site)|/api/storage)[^"]*"' | head
# Poids réel d'une de ces images
curl -sI "URL_TROUVEE" | grep -iE 'content-type|content-length'
# Dans le code
grep -rnE "storage\.getUrl|/api/storage|convex\.cloud/api/storage" src convex | head
```

Problème présent : `content-length` de plusieurs centaines de Ko à plusieurs Mo, `image/jpeg` ou `image/png`, balise `<img>` sans `srcset`. Corrigé : l'URL de l'image commence par `/_image?` (rendu à la demande) ou `/_astro/` (prérendu), en WebP/AVIF avec `srcset`.

## Correction

1. **Autoriser le domaine Convex** dans `astro.config.mjs` (remplacer par le domaine réel de votre déploiement, celui qui apparaît dans les URL de `ctx.storage.getUrl`) :

```js
import { defineConfig } from 'astro/config';

export default defineConfig({
  image: {
    remotePatterns: [
      { protocol: 'https', hostname: 'exemple-deploiement.convex.cloud', pathname: '/api/storage/**' },
    ],
  },
});
```

Pour un Convex auto-hébergé, mettre le domaine public de votre stockage (par exemple `convex.exemple.fr`).

2. **Rendre l'image avec `<Image />`** au lieu de `<img>`. Une image distante a besoin de ses dimensions : les stocker en base à l'upload, ou laisser Astro les lire avec `inferSize`.

```astro
---
import { Image } from 'astro:assets';
const { cours } = Astro.props; // { titre: string, couvertureUrl: string }
---
<Image
  src={cours.couvertureUrl}
  alt={`Couverture du cours ${cours.titre}`}
  width={800}
  height={450}
  widths={[400, 800, 1200]}
  sizes="(max-width: 768px) 100vw, 800px"
  format="webp"
/>
```

Si les dimensions sont inconnues : `<Image src={url} alt="…" inferSize />` (Astro ≥ 4.4). `inferSize` télécharge l'image à la construction du HTML, à réserver aux pages prérendues ou mises en cache.

3. **Pages rendues à la demande (SSR)** : la transformation se fait via `/_image` avec `sharp`, à chaque requête si rien ne la met en cache. Vérifier `sharp` dans les dépendances de production (`npm ls sharp`), et lire `perf-image-endpoint-ssr` pour la mise en cache.
4. **Alternative à long terme** : générer des variantes redimensionnées (par exemple 400, 800, 1600 px en WebP) au moment de l'upload et stocker leurs identifiants dans la table Convex ; le site n'a alors plus qu'à choisir la bonne taille. Cela demande un traitement d'image dans une action Convex Node (bibliothèque `sharp`) : à planifier séparément.
5. **Limiter le poids à l'entrée** : refuser ou redimensionner côté navigateur les fichiers de plus de 2 Mo avant l'envoi au storage.
6. Ne pas oublier `priority` pour l'image LCP si elle vient du storage (`perf-image-lcp-priorite`).

## Critères d'acceptation

- [ ] Plus aucune `<img>` pointant vers `/api/storage/` dans le HTML final
- [ ] Les images de storage sont servies via `/_image` ou `/_astro/`, en WebP/AVIF, avec `srcset`
- [ ] Poids d'une vignette < 100 Ko, d'une image pleine largeur < 250 Ko
- [ ] Le TTFB de `/_image` reste correct au deuxième appel (voir `perf-image-endpoint-ssr`)

## Vérification après correction

```bash
curl -s https://SITE/ | grep -oE '<img[^>]*>' | head -5
bash scripts/http_checks.sh https://SITE/ /tmp/verif    # section 4 bis
python3 scripts/astro_scan.py /chemin/projet --out /tmp/verif
```

## Pièges et retour arrière

- Un domaine non autorisé ne fait pas échouer le build : l'image reste servie brute. Vérifier dans le HTML que l'URL passe bien par `/_image`.
- Les URL de storage Convex n'expirent pas, mais toute personne qui les connaît peut lire le fichier : ne pas y mettre de contenu privé.
- Le serveur travaille plus (sharp consomme CPU et mémoire) : surveiller la charge après déploiement.
- Retour arrière : remettre `<img src={url}>` ; retirer `remotePatterns` si inutile.

## Pour aller plus loin

- https://docs.astro.build/en/guides/images/ : images distantes, `inferSize`, autorisation des domaines.
- https://docs.astro.build/en/reference/configuration-reference/#imageremotepatterns : format de `remotePatterns`.
- https://docs.convex.dev/file-storage/serve-files : obtenir l'URL d'un fichier stocké.
