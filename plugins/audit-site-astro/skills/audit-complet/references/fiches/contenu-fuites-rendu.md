---
id: contenu-fuites-rendu
titre: "Valeurs techniques affichées : undefined, NaN, null, [object Object]"
domaine: Contenu
severite_type: haute
effort: S
declencheurs:
  - "crawl:fuite_rendu"
sources:
  - https://docs.astro.build/en/reference/api-reference/#rewrite
  - https://docs.convex.dev/database/reading-data/
  - https://developers.google.com/search/docs/fundamentals/creating-helpful-content
---

# Valeurs techniques affichées au visiteur

> **En une phrase** : une donnée manquante est publiée telle quelle (« Prix : undefined € », `alt="undefined"`), ce qui dégrade la confiance, le référencement de la page et ce que les IA en retiennent.

## Pourquoi c'est important

Un site alimenté par Convex affiche ce que renvoie la requête : un champ absent, renommé ou mal converti devient « undefined » ou « NaN » à l'écran, dans les extraits Google et dans les réponses des assistants. Aucun outil SEO du marché ne le signale (Screaming Frog ne repère que « lorem ipsum »).

## Comment le constater soi-même

```bash
python3 -c "import json;d=json.load(open('data/crawl/issues.json'));[print(e['signature'], e['exemples_pages']) for e in d.get('fuite_rendu',{}).get('examples',[])]"
curl -s https://SITE/PAGE | grep -nE '\bundefined\b|\bNaN\b|\[object Object\]'
```

## Correction

1. Trouver l'expression qui produit la valeur (souvent une interpolation `{`${doc.prix} €`}` ou `alt={doc.image}`) dans la page ou le composant.
2. Donner une valeur par défaut ou masquer le bloc quand la donnée manque :
```astro
---
const prix = typeof formation.prix === 'number' ? `${formation.prix} €` : null;
---
{prix && <p>Prix : {prix}</p>}
<img src={formation.image ?? '/images/defaut.jpg'} alt={formation.imageAlt ?? ''} />
```
3. Si le document Convex entier manque, répondre 404 plutôt qu'une page vide : `if (!formation) return Astro.rewrite('/404');`.
4. Côté Convex, rendre les champs obligatoires dans le schéma (`v.number()` plutôt que `v.optional(…)`) quand la page ne sait pas s'en passer.

## Critères d'acceptation

- [ ] `fuite_rendu` absent de `data/crawl/issues.json`
- [ ] Les pages concernées affichent la valeur réelle ou masquent proprement le bloc
- [ ] Aucune régression : build OK (`astro check` sans nouvelle erreur)

## Vérification après correction

```bash
python3 scripts/crawl_site.py https://SITE/ --out /tmp/verif/crawl --liens-externes 0
python3 -c "import json;print(json.load(open('/tmp/verif/crawl/issues.json')).get('fuite_rendu',{}).get('count',0))"   # 0
```

## Pièges et retour arrière

- Un article technique qui montre `undefined` dans un `<code>` ou qui écrit « la valeur null indique… » dans une phrase n'est pas signalé. Un mot seul dans son élément (`<span>undefined</span>`), collé à un prix ou une unité (« NaN min »), ou placé après une étiquette courte (« Prix : undefined ») l'est : vérifier l'extrait avant de corriger.
- Retour arrière : `git revert` du composant.
