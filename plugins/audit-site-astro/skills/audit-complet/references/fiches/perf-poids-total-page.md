---
id: perf-poids-total-page
titre: Page trop lourde au total (charge réseau de plusieurs Mo)
domaine: Performance
severite_type: moyenne
effort: M
declencheurs:
  - "lighthouse:total-byte-weight|Évitez d'énormes charges utiles de réseau|Éviter d'énormes charges utiles de réseau"
sources:
  - https://developer.chrome.com/docs/lighthouse/performance/total-byte-weight
  - https://web.dev/articles/incorporate-performance-budgets-into-your-build-tools
  - https://developer.mozilla.org/en-US/docs/Web/HTML/Element/video#preload
---

# Page trop lourde au total (charge réseau de plusieurs Mo)

> **En une phrase** : l'ensemble des fichiers téléchargés pour afficher la page dépasse plusieurs Mo, ce qui coûte du temps et des données mobiles aux visiteurs.

## Pourquoi c'est important

Lighthouse signale ce point lorsque la charge réseau totale devient très élevée (plusieurs Mo) et affiche les fichiers les plus lourds. Sur une connexion mobile moyenne, chaque Mo prend de l'ordre d'une seconde à télécharger, et l'utilisateur peut payer sa consommation de données. Le poids total est un symptôme : la cause est presque toujours une ou deux familles de fichiers (images, vidéos, JavaScript, polices) qui pèsent la plus grande part.

## Comment le constater soi-même

```bash
# Poids de chaque ressource du HTML, trié (approximation sans navigateur)
curl -s https://SITE/ | grep -oE '(src|href)="[^"]+\.(js|css|woff2?|jpe?g|png|webp|avif|svg|mp4|webm)[^"]*"' \
  | sed -E 's/^[a-z]+="//; s/"$//' | sort -u | while read -r u; do
    case "$u" in /*) u="https://SITE$u";; esac
    printf '%10s %s\n' "$(curl -sI "$u" | grep -i '^content-length:' | tr -dc '0-9')" "$u"
  done | sort -rn | head -10
# Résumé Lighthouse
grep -iE "poids_total_ko|requetes" /tmp/verif/pagespeed-summary.md
```

Dans DevTools : onglet Réseau, filtre « Img », « JS », « Media » ; la colonne « Taille » indique les plus gros fichiers. Problème présent : plusieurs fichiers de plus de 300 Ko, ou un total supérieur à 2 Mo. Corrigé : total sous 1,5 Mo pour une page courante, aucun fichier isolé de plus de 250 Ko.

## Correction

Traiter les familles dans l'ordre de leur poids réel :

1. **Images** (le plus fréquent) : passer par `<Image />`/`<Picture />`, AVIF/WebP, tailles adaptées (`perf-images-brutes-public`, `perf-images-formats-modernes`, `perf-images-responsives`). Différer celles hors écran (`perf-images-chargement-differe`).
2. **Vidéos** : ne pas les précharger. Sans lecture automatique, `preload="none"` et une affiche :

```html
<video controls preload="none" poster="/video-poster.webp" width="960" height="540">
  <source src="/demo.mp4" type="video/mp4" />
</video>
```

   Pour une vidéo de fond, compresser (MP4/WebM, 1 à 2 Mo), sans son, et ne pas la charger sur mobile si elle est décorative. Un long contenu vidéo doit être hébergé sur un service spécialisé, avec une façade (`perf-js-tiers`).
3. **JavaScript** : supprimer le code inutile, différer les îlots (`perf-js-inutilise-bundle`, `perf-ilots-hydratation`, `perf-js-tiers`).
4. **Polices** : peu de graisses, woff2, sous-ensemble latin (`perf-polices`).
5. **Fichiers de `public/` énormes** (PDF, archives, images brutes) référencés dans le HTML : les déplacer ou les rendre à la demande (lien de téléchargement).
6. **Compression réseau** : vérifier que HTML, CSS, JS et SVG sortent en `br` ou `gzip` (fiches serveur).
7. **Cache** : les fichiers hashés de `/_astro/` doivent porter `Cache-Control: public, max-age=31536000, immutable` : les visites suivantes ne retéléchargent rien (fiches serveur).
8. **Fixer un budget** pour éviter la dérive : par exemple 1,5 Mo au total et 200 Ko de JavaScript compressé par page, contrôlés à chaque revue (`scripts/lighthouse_run.sh`).

## Critères d'acceptation

- [ ] Le total téléchargé d'une page courante est inférieur à 1,5 Mo (mobile)
- [ ] Aucun fichier d'image supérieur à 250 Ko dans une page de contenu
- [ ] Les vidéos ne se téléchargent pas avant que l'utilisateur les lance (sauf besoin justifié)
- [ ] Lighthouse : « Évitez d'énormes charges utiles de réseau » réussi

## Vérification après correction

```bash
bash scripts/lighthouse_run.sh /tmp/verif https://SITE/
grep -iE "poids_total_ko|requetes" /tmp/verif/pagespeed-summary.md
bash scripts/http_checks.sh https://SITE/ /tmp/verif
```

## Pièges et retour arrière

- Alléger sans regarder le rendu réel : comparer les captures avant et après.
- Un poids bas après un premier chargement peut cacher un cache navigateur : mesurer avec un profil vierge (navigation privée).
- Retour arrière : restaurer les fichiers d'origine (Git).

## Pour aller plus loin

- https://developer.chrome.com/docs/lighthouse/performance/total-byte-weight : pourquoi éviter les charges utiles énormes.
- https://web.dev/articles/incorporate-performance-budgets-into-your-build-tools : budgets de performance.
- https://developer.mozilla.org/en-US/docs/Web/HTML/Element/video#preload : attribut `preload` des vidéos.
