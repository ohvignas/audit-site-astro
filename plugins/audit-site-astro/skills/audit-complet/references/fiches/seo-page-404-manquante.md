---
id: seo-page-404-manquante
titre: Pas de page 404 personnalisée (src/pages/404.astro)
domaine: SEO technique
severite_type: moyenne
effort: S
declencheurs:
  - "code:Pas de src/pages/404\\.astro"
sources:
  - https://docs.astro.build/en/basics/astro-pages/
  - https://docs.astro.build/en/guides/routing/
  - https://developers.google.com/search/docs/crawling-indexing/http-network-errors
---

# Pas de page 404 personnalisée (src/pages/404.astro)

> **En une phrase** : le site n'a pas de page d'erreur 404 à lui, donc un visiteur qui suit un lien cassé tombe sur une page brute, sans navigation ni suggestion.

## Pourquoi c'est important

La page 404 est le filet de sécurité de tous les liens morts, internes comme externes. Une bonne 404 garde le visiteur (menu, recherche, liens vers les pages clés) et réduit le rebond. Côté SEO, l'essentiel est que l'URL réponde bien en **statut 404** (sinon soft 404, fiche `seo-soft-404`) : la page elle-même n'a pas besoin d'être indexée.

## Comment le constater soi-même

```bash
ls src/pages/404.astro src/pages/404.md 2>&1
curl -s -o /dev/null -w '%{http_code}\n' https://SITE/page-qui-nexiste-pas   # attendu : 404
curl -s https://SITE/page-qui-nexiste-pas | grep -oE '<title>[^<]*'
```

Présent : le fichier n'existe pas ; la réponse est une page générique du serveur ou du navigateur. Corrigé : une page du site, avec le menu, servie en 404.

## Correction

1. Créer `src/pages/404.astro` (ou `404.md`). Astro le compile en `404.html` pour un site statique ; la plupart des hébergeurs la servent automatiquement. En rendu à la demande, l'adaptateur la sert avec le statut 404.
2. Utiliser le layout du site (menu, pied de page), un message clair et 3 à 6 liens vers les pages importantes.

```astro
---
// src/pages/404.astro
import BaseLayout from '../layouts/BaseLayout.astro';
---
<BaseLayout title="Page introuvable" description="La page demandée n'existe pas ou a été déplacée.">
  <main>
    <h1>Page introuvable</h1>
    <p>Cette adresse n'existe pas ou a été déplacée. Voici quelques pages utiles :</p>
    <ul>
      <li><a href="/">Accueil</a></li>
      <li><a href="/contact/">Contact</a></li>
      <li><a href="/blog/">Blog</a></li>
    </ul>
  </main>
</BaseLayout>
```

3. Pour un site servi par **nginx** (statique) : indiquer la page d'erreur, sinon nginx affiche la sienne.

```nginx
error_page 404 /404.html;
location = /404.html { internal; }
```

Avec **Caddy** (fichiers statiques) : `handle_errors { rewrite * /404.html  file_server }` en gardant le statut 404 (dans un bloc `handle_errors`, Caddy conserve le code d'erreur).

4. Derrière un serveur Node (`@astrojs/node`), rien à ajouter : l'adaptateur sert `404.astro` pour toute route inconnue. Ne pas configurer le proxy pour remplacer les 404 par l'accueil.
5. Ne pas mettre de redirection automatique vers l'accueil sur cette page (soft 404).

## Critères d'acceptation

- [ ] `src/pages/404.astro` existe et utilise le layout du site
- [ ] Une URL inexistante renvoie le **statut 404** avec cette page
- [ ] La page propose au moins un lien vers l'accueil et vers une rubrique
- [ ] Aucune régression : build OK, la page 404 n'est pas dans le sitemap

## Vérification après correction

```bash
curl -s -o /dev/null -w '%{http_code}\n' https://SITE/page-qui-nexiste-pas
curl -s https://SITE/page-qui-nexiste-pas | grep -c 'Page introuvable'
bash scripts/http_checks.sh https://SITE/ /tmp/verif   # dernière ligne de la section 6 : 404
```

## Pièges et retour arrière

- Le filtre du sitemap doit exclure `/404` (vérifier que `/404` n'apparaît pas dans le sitemap, surtout avec un endpoint personnalisé).
- Une 404 servie avec le statut 200 par le proxy est un soft 404 : contrôler avec `curl -I`.
- Retour arrière : supprimer `src/pages/404.astro`.

## Pour aller plus loin

- https://docs.astro.build/en/basics/astro-pages/ : pages d'erreur 404 et 500.
- https://docs.astro.build/en/guides/routing/ : routage et `Astro.rewrite('/404')`.
- https://developers.google.com/search/docs/crawling-indexing/http-network-errors : statuts 4xx et exploration.
