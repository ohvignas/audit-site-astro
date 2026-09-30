---
id: contenu-cannibalisation
titre: Pages aux titres quasi identiques (cannibalisation possible)
domaine: Contenu
severite_type: moyenne
effort: M
declencheurs:
  - "crawl:near_dup_titles"
sources:
  - https://developers.google.com/search/docs/crawling-indexing/consolidate-duplicate-urls
  - https://developers.google.com/search/docs/appearance/title-link
  - https://docs.astro.build/en/reference/configuration-reference/#redirects
---

# Pages aux titres quasi identiques (cannibalisation possible)

> **En une phrase** : deux pages ou plus visent la même recherche, elles se concurrencent et aucune n'atteint le haut des résultats.

## Pourquoi c'est important

Quand deux pages d'un même site répondent à la même requête, Google en choisit une (pas toujours la bonne), alterne entre elles, ou les classe toutes deux plus bas. La popularité (liens, clics) est répartie au lieu d'être concentrée. Le cas typique : un article « Devenir développeur web » et la page métier « Développeur web » qui visent la même intention ; ou une page formation et sa page « ville » dont le texte est presque le même. L'outil repère seulement des titres et H1 qui partagent au moins 70 % de leurs mots (hors mots de marque) : c'est un indice à confirmer par la lecture des pages et, idéalement, par Search Console (deux URL du site qui reçoivent des impressions pour la même requête).

## Comment le constater soi-même

```bash
# paires suspectes détectées par l'outil
python3 -c "import json;d=json.load(open('data/crawl/issues.json'));[print(e['a'],'<->',e['b'],e['mots_communs']) for e in d['near_dup_titles']['examples']]"
# recherche Google du site pour une requête visée
#   site:SITE devenir développeur web      -> plusieurs pages proches en tête ?
# Search Console : Performances > Requêtes > cliquer la requête > onglet Pages : plusieurs URL du site ?
```

Confirmé si deux URL répondent à la même intention de recherche. Faux positif si les titres partagent des mots mais visent des intentions différentes (« Formation Excel débutant » et « Formation Excel avancé »).

## Correction

1. **Pour chaque paire, lire les deux pages et décider de l'intention** de chacune : informer (article), comparer, acheter ou s'inscrire (page business), se localiser.
2. **Choisir l'une des 4 solutions** :
   - **Fusionner** (mêmes intention et contenu) : garder la page la plus forte (trafic, liens, ancienneté), y reprendre le meilleur de l'autre, puis rediriger l'autre en 301 (étape 3) et corriger les liens internes.
   - **Différencier** (intentions réellement différentes) : réécrire titre, H1 et introduction de chaque page pour que chacune vise une requête distincte. Exemple : `Devenir développeur web : parcours et formations | Exemple` (article, intention informer) et `Formation développeur web à Lyon, éligible CPF | Exemple` (page business, intention s'inscrire).
   - **Désigner une page principale** : l'article renvoie vers la page business par un lien contextuel clair (ancre descriptive, voir `contenu-maillage-ancres`), et n'essaie plus de se positionner sur la requête commerciale.
   - **Canonical** (contenus quasi identiques à conserver, ex. variantes d'une même fiche) : `<link rel="canonical" href="https://exemple.fr/page-principale/" />` sur la page secondaire. Ne pas utiliser si les contenus diffèrent réellement.
3. **Redirection 301 en Astro** (site statique ou SSR) dans `astro.config.mjs` :

```js
// astro.config.mjs (extrait)
export default {
  site: 'https://exemple.fr',
  redirects: {
    '/blog/formation-excel-avance-2': { status: 301, destination: '/formations/excel-avance/' },
  },
};
```

   Selon l'hébergeur, préférer une règle serveur (nginx `return 301`, Caddy `redir`) ; en site statique pur, Astro génère une page HTML de redirection (meta refresh), qui n'est pas un vrai 301 HTTP. Retirer l'URL supprimée du sitemap (elle disparaît seule si le sitemap est généré au build) et supprimer la page ou l'entrée de collection.
4. **Réécrire les titres et H1** de la page conservée avec la méthode de `contenu-title` et `contenu-h1`. Source du texte : layout ou page `.astro`, frontmatter de la collection (`seoTitle`), ou document Convex (`seoTitle`, `titre`).
5. **Convex** : si les deux pages sont deux documents d'une même table, fusionner le contenu dans le document conservé, puis supprimer l'autre avec une `internalMutation` (`ctx.db.delete(id)`), lancée par `npx convex run`, après sauvegarde (`npx convex export --path sauvegarde.zip`). La redirection 301 doit exister avant la suppression.
6. **Mettre à jour le maillage** : tout lien interne qui pointait vers l'URL supprimée doit viser l'URL conservée (`grep -rn "ancienne-url" src`).

## Critères d'acceptation

- [ ] Chaque requête visée a une page principale identifiée ; les autres pages ciblent une intention différente ou ont été fusionnées.
- [ ] Les pages supprimées redirigent en 301 vers leur remplaçante ; aucun lien interne ne pointe encore vers elles.
- [ ] Les titres et H1 de deux pages conservées ne se recouvrent plus à 70 % ou plus.
- [ ] Build OK, sitemap sans URL supprimée.

## Vérification après correction

```bash
curl -sI https://SITE/blog/formation-excel-avance-2 | grep -iE '^(HTTP|location)'     # 301 + Location
python3 scripts/crawl_site.py https://SITE/ --out /tmp/verif/crawl
python3 -c "import json;d=json.load(open('/tmp/verif/crawl/issues.json'));print(d.get('near_dup_titles',{}).get('count',0))"
```

Après 4 à 8 semaines, contrôler dans Search Console que la requête est servie par une seule URL.

## Pièges et retour arrière

- Ne pas fusionner deux pages qui ont des intentions différentes juste parce que les titres se ressemblent.
- Une redirection vers une page sans rapport est traitée comme une soft 404 : rediriger vers la page équivalente.
- Ne pas supprimer sans redirection : les liens externes et le trafic seraient perdus.
- Retour arrière : `git revert` et restauration de l'export Convex ; retirer la règle de redirection.

## Pour aller plus loin

- https://developers.google.com/search/docs/crawling-indexing/consolidate-duplicate-urls : canonical et redirections pour regrouper des pages.
- https://developers.google.com/search/docs/appearance/title-link : titres distincts et descriptifs.
- https://docs.astro.build/en/reference/configuration-reference/#redirects : option `redirects` d'Astro.
