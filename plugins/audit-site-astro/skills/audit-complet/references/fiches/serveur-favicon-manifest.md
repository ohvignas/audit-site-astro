---
id: serveur-favicon-manifest
titre: Favicon absent ou non déclaré, manifeste d'application manquant
domaine: Serveur / HTTP
severite_type: basse
effort: S
declencheurs:
  - "http:\\| /favicon\\.(ico|svg) \\| (404|5\\d\\d)"
  - "http:\\| /(site|manifest)\\.webmanifest \\| (404|5\\d\\d)"
sources:
  - https://developers.google.com/search/docs/appearance/favicon-in-search
  - https://docs.astro.build/en/basics/project-structure/
  - https://developer.mozilla.org/en-US/docs/Web/Progressive_web_apps/Manifest
---

# Favicon absent ou non déclaré, manifeste d'application manquant

> **En une phrase** : le site n'a pas d'icône déclarée (ou le fichier renvoie une erreur) ; Google affiche une icône générique dans ses résultats et les navigateurs génèrent des 404 à chaque visite.

## Pourquoi c'est important

_Cette fiche complète `contenu-favicon` (qui traite l'absence de balise ou de fichier dans le projet) : ici l'angle est le service HTTP des fichiers d'icônes (404 sur `/favicon.ico`) et le manifeste._

Google affiche le favicon à côté du titre dans les résultats mobiles : un site sans icône paraît moins fiable et se distingue moins. Google demande une balise `<link rel="icon">` dans le `<head>` de l'**accueil**, une image carrée d'au moins 8x8 px (48x48 px ou plus recommandé), un fichier crawlable (non bloqué pour Googlebot-Image) et une URL stable. Les navigateurs réclament aussi `/favicon.ico` automatiquement : sans fichier, chaque première visite génère une requête en 404 (bruit dans les journaux, et dans les rapports de crawl).

Le manifeste (`manifest.webmanifest`) n'est utile que pour un site installable (PWA) ou pour définir le nom et la couleur d'application sur mobile. Sa 404 n'est pas un défaut en soi si vous n'en avez pas besoin : les lignes `manifest.webmanifest` et `site.webmanifest` de l'outil testent deux noms usuels, un seul peut exister.

## Comment le constater soi-même

```bash
curl -s https://SITE/ | grep -oiE '<link[^>]+rel="[^"]*(icon|manifest)[^"]*"[^>]*>'      # balises déclarées
for f in favicon.ico favicon.svg apple-touch-icon.png manifest.webmanifest; do
  printf '%s : ' "$f"; curl -s -o /dev/null -w '%{http_code} %{content_type}\n' "https://SITE/$f"
done
grep -rn 'rel="icon"' src/layouts src/components 2>/dev/null; ls public | grep -iE 'favicon|apple-touch|manifest'
```

Problème présent : aucune balise `rel="icon"`, ou une balise dont le fichier répond 404. Corrigé : balise présente et fichier en 200 avec un type `image/*`.

## Correction

1. **Créer les fichiers dans `public/`** (servis tels quels, à la racine du site) : `favicon.svg` (vectoriel) et `favicon.ico` (48x48, pour Google et les anciens navigateurs), plus `apple-touch-icon.png` (180x180, fond opaque). Les projets créés avec le gabarit d'Astro contiennent déjà `public/favicon.svg`.

2. **Déclarer les icônes dans le `<head>`** du layout commun (`src/layouts/BaseLayout.astro` ou équivalent) pour qu'elles soient présentes sur toutes les pages, accueil compris :

```astro
---
// src/layouts/BaseLayout.astro (extrait du <head>)
---
<link rel="icon" href="/favicon.ico" sizes="48x48" />
<link rel="icon" href="/favicon.svg" type="image/svg+xml" />
<link rel="apple-touch-icon" href="/apple-touch-icon.png" />
<link rel="manifest" href="/manifest.webmanifest" />
```

Google reconnaît `icon`, `shortcut icon`, `apple-touch-icon` et `apple-touch-icon-precomposed`. Omettre la ligne `manifest` si le fichier n'est pas créé.

3. **Manifeste (optionnel)** : créer `public/manifest.webmanifest` :

```json
{
  "name": "Exemple - nom complet du site",
  "short_name": "Exemple",
  "start_url": "/",
  "display": "browser",
  "background_color": "#ffffff",
  "theme_color": "#1a56db",
  "icons": [
    { "src": "/icon-192.png", "sizes": "192x192", "type": "image/png" },
    { "src": "/icon-512.png", "sizes": "512x512", "type": "image/png" }
  ]
}
```

Les images `icon-192.png` et `icon-512.png` doivent exister dans `public/`. `display: "browser"` évite de transformer le site en application plein écran sans y être prêt.

4. **Vérifier le type MIME servi** : `.webmanifest` doit sortir en `application/manifest+json` (ou `application/json`). nginx : ajouter `application/manifest+json webmanifest;` au fichier `mime.types` si absent ; Caddy et Node le gèrent.

5. **Ne pas bloquer** `/favicon.ico` ni les images d'icônes dans `robots.txt`, et ne pas les mettre derrière une authentification ou une règle de pare-feu.

6. **Site sans identité visuelle** : si le site n'a pas d'identité visuelle, créer au minimum un favicon simple (initiale de la marque sur fond uni) plutôt que de laisser des 404.

## Critères d'acceptation

- [ ] Une balise `<link rel="icon">` dans le `<head>` de l'accueil, pointant vers un fichier qui répond 200 avec un `content-type` `image/…`
- [ ] `/favicon.ico` répond 200 (ou la balise pointe vers un autre fichier valide et aucune requête n'est en 404)
- [ ] Si le manifeste est déclaré : il répond 200 en JSON valide et ses icônes existent
- [ ] Aucune régression : build OK, en-tête inchangé sur les autres pages

## Vérification après correction

```bash
curl -s https://SITE/ | grep -ci 'rel="icon"'                      # >= 1
curl -sI https://SITE/favicon.ico | head -3
bash scripts/http_checks.sh https://SITE/ /tmp/verif             # §3 « Favicon déclaré » en ✅, §6 favicon en 200
python3 scripts/astro_scan.py . --out /tmp/verif                 # plus de « Pas de favicon dans public/ »
```

Google met plusieurs jours à quelques semaines à actualiser un favicon ; l'outil « Inspection de l'URL » de la Search Console peut accélérer la demande.

## Pièges et retour arrière

- Changer souvent l'URL du favicon retarde sa prise en compte par Google : garder un nom stable.
- Le SVG ne figure pas dans la liste des formats acceptés par Google pour le favicon (BMP, GIF, ICO, PNG, JPEG, PPM, TIFF) : garder toujours un `.ico` ou `.png` d'au moins 48x48 en plus du `.svg`.
- Retour arrière : supprimer les balises ajoutées ; les fichiers dans `public/` sont inoffensifs.

## Pour aller plus loin

- https://developers.google.com/search/docs/appearance/favicon-in-search : consignes de Google pour le favicon.
- https://docs.astro.build/en/basics/project-structure/ : dossier `public/` servi à la racine.
- https://developer.mozilla.org/en-US/docs/Web/Progressive_web_apps/Manifest : membres du manifeste d'application web.
