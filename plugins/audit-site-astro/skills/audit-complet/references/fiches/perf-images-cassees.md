---
id: perf-images-cassees
titre: Images cassées (URL d'image en erreur 404 ou 5xx)
domaine: Performance
severite_type: moyenne
effort: S
declencheurs:
  - "crawl:broken_images"
sources:
  - https://docs.astro.build/en/guides/images/
  - https://docs.astro.build/en/guides/troubleshooting/
  - https://developer.mozilla.org/en-US/docs/Web/HTML/Element/img
---

# Images cassées (URL d'image en erreur 404 ou 5xx)

> **En une phrase** : des pages référencent des images qui ne répondent pas (fichier supprimé, chemin faux, image de stockage détruite, endpoint `/_image` en erreur), ce qui laisse un cadre vide, fait sauter la page et gaspille des requêtes.

## Pourquoi c'est important

Une image cassée affiche une icône d'erreur ou un trou, dégrade la confiance et l'image de marque, et peut décaler la mise en page. Le navigateur perd aussi du temps à tenter de la charger. Pour Google, les images font partie de l'expérience de la page et de Google Images : une image en 404 disparaît de l'index. Côté Astro, les causes les plus fréquentes sont un fichier déplacé de `public/`, une image de Convex supprimée dont l'URL est restée en base, une transformation `/_image` qui échoue (domaine non autorisé, `sharp` absent) ou une URL mal construite derrière un proxy.

## Comment le constater soi-même

```bash
# Statut d'une image signalée par l'audit
curl -sI "URL_DE_L_IMAGE" | head -1
# Lister les images d'une page et leur statut
curl -s https://SITE/page | grep -oE '(src|srcset)="[^"]+"' | sed -E 's/^[a-z]+="//; s/"$//' | awk '{print $1}' | head -20 |
  while read -r u; do case "$u" in /*) u="https://SITE$u";; esac; printf '%s %s\n' "$(curl -s -o /dev/null -w '%{http_code}' "$u")" "$u"; done
```

Problème présent : des lignes `404`, `403`, `500` ou `000`. Corrigé : toutes en `200`.

## Correction

1. Lire, dans le fichier de données du crawl (`data/crawl/issues.json`, clé `broken_images`), la liste des URL cassées et les pages qui les contiennent.
2. Classer chaque cas selon l'URL :
   - **`/images/...` ou fichier de `public/`** : le fichier n'existe pas dans `public/` ou son nom a une casse différente (Linux distingue `Photo.JPG` de `photo.jpg`). Restaurer le fichier (`git log --diff-filter=D -- public/images/x.jpg`) ou corriger la référence.
   - **`/_astro/x.HASH.webp`** : ancien HTML en cache qui référence un fichier dont le hash a changé après un nouveau build. Purger le cache du CDN ou du proxy, et s'assurer que les pages HTML ne sont pas mises en cache plus longtemps que les déploiements.
   - **`/_image?href=...`** : la transformation échoue. Vérifier le journal du serveur Node ; causes usuelles : domaine distant non autorisé (`image.remotePatterns`, voir `perf-images-convex-storage`), `sharp` manquant en production, source introuvable.
   - **URL Convex `/api/storage/...`** : le fichier a été supprimé du storage alors que la ligne en base pointe encore vers lui. Recréer le fichier, ou mettre à jour l'enregistrement, et afficher une image par défaut si l'URL est absente.
   - **Domaine externe** : remplacer par une image locale (les images de sites tiers peuvent disparaître à tout moment).
3. **Prévoir une image de secours** pour les données dynamiques :

```astro
---
import { Image } from 'astro:assets';
import placeholder from '../assets/placeholder.jpg';
const { cours } = Astro.props;
---
{cours.couvertureUrl
  ? <Image src={cours.couvertureUrl} alt={cours.titre} width={800} height={450} />
  : <Image src={placeholder} alt="" width={800} height={450} />}
```

4. **Empêcher la récidive à la suppression** : dans la mutation Convex qui supprime un fichier, mettre aussi à jour ou supprimer les documents qui y font référence.
5. Si le proxy modifie l'URL (double slash, `http://` en dur), corriger la construction des URL avec `new URL(chemin, Astro.site)` (voir `seo-astro-site-et-proxy`).

## Critères d'acceptation

- [ ] Chaque URL listée dans `broken_images` répond `200`
- [ ] Un nouveau crawl avec `--check-images` ne remonte plus de `broken_images`
- [ ] Les pages avec données dynamiques affichent l'image de secours quand une URL manque
- [ ] Aucune erreur 404/500 d'image dans l'onglet Réseau de DevTools sur les pages clés

## Vérification après correction

```bash
python3 scripts/crawl_site.py https://SITE --out /tmp/verif/crawl --max-pages 200 --check-images 200
grep -c broken_images /tmp/verif/crawl/issues.json
```

## Pièges et retour arrière

- Ne pas « corriger » en supprimant l'image du HTML sans vérifier son rôle (logo, produit) : chercher d'abord le fichier d'origine.
- Un même fichier peut être cassé sur une seule des variantes `http`/`https` ou `www` : tester l'URL exacte du HTML.
- Retour arrière : `git revert` du commit de correction ; le contenu supprimé reste dans l'historique Git.

## Pour aller plus loin

- https://docs.astro.build/en/guides/images/ : utilisation d'images locales et distantes.
- https://docs.astro.build/en/guides/troubleshooting/ : diagnostiquer une erreur de build ou d'exécution.
- https://developer.mozilla.org/en-US/docs/Web/HTML/Element/img : comportement de l'élément `<img>`.
