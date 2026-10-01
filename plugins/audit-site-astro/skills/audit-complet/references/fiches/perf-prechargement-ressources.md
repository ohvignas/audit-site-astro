---
id: perf-prechargement-ressources
titre: Chaînes de requêtes critiques et connexions tierces tardives (preload, preconnect)
domaine: Performance
severite_type: basse
effort: S
declencheurs:
  - "lighthouse:critical-request-chains|network-dependency-tree-insight|uses-rel-preload|uses-rel-preconnect|Évitez de créer des chaînes de requêtes critiques|Arborescence du réseau|Préchargez les demandes clés|Connectez-vous à l'avance aux origines souhaitées"
sources:
  - https://web.dev/articles/preconnect-and-dns-prefetch
  - https://web.dev/articles/preload-critical-assets
  - https://web.dev/articles/critical-rendering-path
  - https://developer.mozilla.org/en-US/docs/Web/HTML/Attributes/rel/preconnect
---

# Chaînes de requêtes critiques et connexions tierces tardives (preload, preconnect)

> **En une phrase** : le navigateur découvre des ressources indispensables (police, image, script) trop tard, parce qu'elles dépendent d'une autre ressource, ou ouvre trop tard la connexion vers un domaine externe.

## Pourquoi c'est important

Le navigateur ne peut télécharger une ressource que lorsqu'il en connaît l'existence. Si une police n'est citée que dans un CSS qui lui-même est cité par un autre CSS (`@import`), il faut trois allers-retours réseau successifs avant le texte final : c'est une « chaîne de requêtes critiques ». Chaque maillon ajoute une latence complète. Pour un domaine externe indispensable au premier écran, l'ouverture de connexion (DNS, TCP, TLS) coûte souvent 100 à 500 ms sur mobile. Lighthouse le signale par « Évitez de créer des chaînes de requêtes critiques », « Préchargez les demandes clés », « Connectez-vous à l'avance aux origines souhaitées » et l'analyse « Arborescence du réseau ».

## Comment le constater soi-même

```bash
# Ressources déclarées dans le <head>
curl -s https://SITE/ | grep -oE '<link[^>]*(preload|preconnect|dns-prefetch|modulepreload|stylesheet)[^>]*>' | head -20
# CSS qui en importe d'autres, polices déclarées dans le CSS
grep -rn "@import" src public | head
# Domaines tiers appelés au chargement
curl -s https://SITE/ | grep -oE '(src|href)="https?://[^"/]+' | sed -E 's/.*:\/\///' | sort | uniq -c | sort -rn
```

Problème présent : des `@import` en cascade, une police citée uniquement dans un CSS, un domaine externe important sans `preconnect`. Corrigé : chaîne de 1 ou 2 niveaux au maximum, ressources critiques annoncées dans le HTML.

## Correction

1. **Supprimer les `@import` CSS** : remplacer par des `import` dans le layout ou le frontmatter (Vite regroupe alors le CSS).

```astro
---
import '../styles/reset.css';
import '../styles/global.css';
---
```

2. **Polices** : utiliser l'API Fonts d'Astro avec `preload` restreint, ou précharger le fichier woff2 principal (voir `perf-polices`). Ne pas précharger plus de deux polices.
3. **Image LCP** : `priority` sur `<Image />` (voir `perf-image-lcp-priorite`) plutôt qu'un `<link rel="preload">` manuel, sauf pour un fond CSS.
4. **Connexion anticipée vers un tiers indispensable** (CDN d'images, API d'analytics utilisée dès le chargement, fournisseur de polices non auto-hébergé), dans le `<head>` du layout :

```astro
<link rel="preconnect" href="https://cdn.exemple-tiers.com" crossorigin />
<link rel="dns-prefetch" href="https://cdn.exemple-tiers.com" />
```

   N'en déclarer que 2 ou 3 : au-delà, elles se concurrencent. Ne pas en déclarer pour un tiers chargé après interaction (`perf-js-tiers`).
5. **Ne pas précharger à tout va** : chaque `preload` retire de la bande passante aux autres ressources. Le précharger seulement si la ressource est utilisée dès le premier écran et n'est pas découvrable dans le HTML.
6. **Scripts qui en chargent d'autres** : éviter les `import()` dynamiques en cascade pour du code nécessaire dès le chargement (chaque niveau ajoute un aller-retour) ; les réserver au code chargé à la demande (`perf-js-inutilise-bundle`).
7. **Compléter par la réduction des ressources** : moins de feuilles, moins de scripts tiers, moins d'îlots `client:load`.

## Critères d'acceptation

- [ ] Aucune règle `@import` dans le CSS de production
- [ ] Profondeur maximale de la chaîne de requêtes critiques : 2 niveaux en dehors des tiers
- [ ] 0 à 3 `preconnect`, tous vers des domaines utilisés au chargement
- [ ] Pas de `preload` inutilisé (avertissement « preloaded but not used » absent de la console)

## Vérification après correction

```bash
curl -s https://SITE/ | grep -oE '<link[^>]*(preload|preconnect)[^>]*>'
bash scripts/lighthouse_run.sh /tmp/verif https://SITE/
```

## Pièges et retour arrière

- Un `preload` avec un mauvais `as` ou sans `crossorigin` (pour les polices) est ignoré et le fichier est téléchargé deux fois.
- Un `preconnect` vers un domaine non utilisé gaspille une connexion.
- Retour arrière : retirer les balises `<link>` ajoutées.

## Pour aller plus loin

- https://web.dev/articles/preconnect-and-dns-prefetch : préconnexion et résolution DNS anticipée.
- https://web.dev/articles/preload-critical-assets : précharger les ressources critiques.
- https://web.dev/articles/critical-rendering-path : chemin critique de rendu.
- https://developer.mozilla.org/en-US/docs/Web/HTML/Attributes/rel/preconnect : `rel="preconnect"`.
