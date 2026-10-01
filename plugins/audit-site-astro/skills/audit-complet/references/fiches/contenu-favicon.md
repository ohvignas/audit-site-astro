---
id: contenu-favicon
titre: Favicon absent ou non déclaré
domaine: Contenu
severite_type: basse
effort: S
declencheurs:
  - "code:Pas de favicon dans public/"
  - "http:Favicon déclaré \\| aucun"
sources:
  - https://developers.google.com/search/docs/appearance/favicon-in-search
  - https://docs.astro.build/en/basics/project-structure/
---

# Favicon absent ou non déclaré

> **En une phrase** : le site n'a pas d'icône, donc Google affiche un globe générique à côté du résultat et l'onglet du navigateur est anonyme.

## Pourquoi c'est important

Google affiche le favicon du site à côté des résultats : c'est un repère de confiance et de marque. Sans favicon déclaré, il affiche une icône par défaut ; les navigateurs réclament aussi `/favicon.ico` (une 404 par visite, du bruit dans les journaux). Le gain est modeste, l'effort minime. Google demande une icône carrée (1:1), d'au moins 8x8 px et de préférence d'un multiple de 48 px (48x48, 96x96), une URL stable, accessible à Googlebot et Googlebot-Image, et déclarée dans le `<head>` de la page d'accueil. Formats acceptés par Google : ICO, PNG, GIF, JPEG, BMP, etc.

## Comment le constater soi-même

```bash
curl -s https://SITE/ | grep -oiE '<link[^>]+rel="[^"]*icon[^"]*"[^>]*>'
curl -sI https://SITE/favicon.ico | head -1
ls public/favicon.* public/apple-touch-icon.png 2>/dev/null
```

Présent : aucun `<link rel="icon">`, ou un fichier déclaré qui répond 404. Corrigé : au moins un `<link rel="icon">` dont l'URL répond 200.

## Correction

1. **Créer les fichiers** dans `public/` (servis tels quels à la racine, sans traitement) à partir du logo carré fourni par le propriétaire :
   - `public/favicon.svg` (icône vectorielle, navigateurs modernes),
   - `public/favicon.ico` (32x32 px, repli pour les anciens navigateurs et les robots qui l'appellent par défaut),
   - `public/apple-touch-icon.png` (180x180 px, iOS),
   - facultatif : `public/icon-192.png` et `public/icon-512.png` si un manifeste d'application web est ajouté.
   Si seul un PNG carré existe (par exemple 512x512), le déclarer avec `type="image/png"` en attendant les autres formats. Ne pas inventer un logo : demander l'image de marque.
2. **Déclarer dans le layout** (`src/layouts/BaseLayout.astro`, dans `<head>`) :

```astro
<link rel="icon" href="/favicon.ico" sizes="32x32" />
<link rel="icon" href="/favicon.svg" type="image/svg+xml" />
<link rel="apple-touch-icon" href="/apple-touch-icon.png" />
```

   Si le site est servi sous une base (`base: '/prefixe'` dans `astro.config.mjs`), préfixer avec `import.meta.env.BASE_URL`. Le fichier `favicon.svg` fourni par le gabarit de démarrage Astro est celui du logo Astro : le remplacer, sinon le site porte l'icône d'Astro.
3. **Un seul favicon par hôte** : Google en retient un par nom d'hôte ; garder la même URL d'icône sur toutes les pages.
4. **Ne pas bloquer** `/favicon.ico` ni le dossier de l'icône dans `robots.txt`, et ne pas la protéger derrière une authentification.
5. **Sur un site sans dossier `public/` géré par Astro** (ancien thème, CMS externe), l'icône se déclare dans le modèle de page ; la règle est la même.

## Critères d'acceptation

- [ ] Au moins un `<link rel="icon">` dans le `<head>` de l'accueil, dont l'URL répond 200 avec un type image.
- [ ] `/favicon.ico` répond 200 (plus de 404 dans les journaux).
- [ ] L'icône est carrée, nette à 16 px, et représente la marque (pas le logo Astro par défaut).
- [ ] `apple-touch-icon` de 180x180 px présent.

## Vérification après correction

```bash
curl -sI https://SITE/favicon.ico | head -1                 # HTTP/2 200
curl -sI https://SITE/favicon.svg | grep -i content-type    # image/svg+xml
bash scripts/http_checks.sh https://SITE/ /tmp/verif        # ligne « Favicon déclaré » avec ✅
```

## Pièges et retour arrière

- Le favicon de Google Search met plusieurs jours à semaines à se mettre à jour ; le navigateur met l'ancien en cache : tester en navigation privée.
- Le SVG n'est pas listé dans les formats de la doc Google : garder le `.ico` ou un PNG en plus.
- Ne pas changer l'URL du favicon à chaque déploiement (fichier au nom haché) : Google demande une URL stable.
- Retour arrière : `git revert` ; supprimer les balises `<link>` et les fichiers.

## Pour aller plus loin

- https://developers.google.com/search/docs/appearance/favicon-in-search : exigences de Google pour le favicon affiché dans les résultats.
- https://docs.astro.build/en/basics/project-structure/ : le dossier `public/` est servi tel quel.
