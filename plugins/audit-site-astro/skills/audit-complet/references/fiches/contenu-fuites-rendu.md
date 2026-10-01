---
id: contenu-fuites-rendu
titre: "Valeurs techniques affichées : undefined, NaN, null, [object Object], Invalid Date"
domaine: Contenu
severite_type: haute
effort: S
declencheurs:
  - "crawl:fuite_rendu"
  - "crawl:fuite_rendu_isolee"
sources:
  - https://docs.astro.build/en/reference/api-reference/#rewrite
  - https://docs.convex.dev/database/reading-data/
  - https://developers.google.com/search/docs/fundamentals/creating-helpful-content
---

# Valeurs techniques affichées au visiteur

> **En une phrase** : une donnée manquante est publiée telle quelle (« Prix : undefined € », `alt="undefined"`, « Mis à jour le Invalid Date », `<title>undefined | Site</title>`), ce qui dégrade la confiance, le référencement de la page et ce que les IA en retiennent.

## Pourquoi c'est important

Un site alimenté par Convex affiche ce que renvoie la requête : un champ absent, renommé ou mal converti devient « undefined », « NaN » ou « Invalid Date » à l'écran, dans le `<title>` et la meta description (donc dans les extraits Google et les réponses des assistants). Aucun outil SEO du marché ne le signale (Screaming Frog ne repère que « lorem ipsum »).

## Comment le constater soi-même

```bash
python3 -c "import json;d=json.load(open('data/crawl/issues.json'));[print(e['signature'], e['exemples_pages']) for e in d.get('fuite_rendu',{}).get('examples',[])]"
curl -s https://SITE/PAGE | grep -nE '\bundefined\b|\bNaN\b|\[object Object\]|Invalid Date'
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

- [ ] `fuite_rendu` et `fuite_rendu_isolee` absents de `data/crawl/issues.json`
- [ ] Les pages concernées affichent la valeur réelle ou masquent proprement le bloc
- [ ] Aucune régression : build OK (`astro check` sans nouvelle erreur)

## Vérification après correction

```bash
python3 scripts/crawl_site.py https://SITE/ --out /tmp/verif/crawl --liens-externes 0
python3 -c "import json;print(json.load(open('/tmp/verif/crawl/issues.json')).get('fuite_rendu',{}).get('count',0))"   # 0
```

## Ce que l'outil lit, et ce qu'il laisse passer

Deux clés dans `issues.json` :

- `fuite_rendu` (**haute**) : le mot se comporte comme une valeur affichée.
  - Collé à un prix, une unité ou un nombre (« NaN min », « NaN inscrits », « NaN/NaN/NaN »), après une étiquette courte (« Prix : undefined »), une formule (« Bonjour undefined », « Écrit par undefined ») ou une date (« Ajouté le undefined », « Du undefined au undefined »).
  - `[object Object]`, `Invalid Date`, `{{ variable }}`, partout dans le texte visible.
  - `alt` / `title` / `aria-label` / `placeholder` / `value` réduit au mot.
  - Un lien du site vers `/formations/undefined`, `?id=undefined`, `tel:undefined`, `mailto:undefined`.
  - Le `<title>`, la meta description et `og:` / `twitter:` (coupés sur `|`, `-`, `—`, `·` : un segment réduit au mot, ou fini par le mot, est une fuite). Toujours lus, même sur une page de tutoriel.
- `fuite_rendu_isolee` (**basse**) : le mot remplit tout un élément (`<td>null</td>`, `<li>undefined</li>`, `<h3>undefined</h3>`, `<span>NaN</span>`), ou finit un `alt` ou un libellé de bouton. C'est une vraie fuite sur une fiche produit à champs vides (prix, note, stock) et de la documentation dans un tutoriel sans `<code>` : ces constats ne sont jamais supprimés, mais classés bas pour être vérifiés d'un coup d'œil sur l'extrait.

Laissé passer : `<code>`, `<pre>`, `<kbd>`, `<samp>`, scripts, JSON-LD ; la prose (« la valeur null indique… », « NaN means Not-a-Number ») ; les liens vers un autre site (MDN) ; « nul », « nulle ». Limite connue : un lien externe dont le dernier segment est le mot (`https://wa.me/undefined`) n'est pas signalé, car il se confond avec les liens vers la documentation d'un autre site ; seul `?id=undefined` l'est sur tout hôte.

## Pièges et retour arrière

- Un article technique écrit sans `<code>` ni `<pre>` (tableau « Valeur / Signification », cellules `undefined`, `null`, `NaN` en texte brut) produit des constats `fuite_rendu_isolee` : lire l'extrait de la signature, qui reproduit le texte de la page, et ignorer le constat s'il s'agit de documentation.
- Un lien vers une page de ce même site dont le chemin finit par `/null` ou `/undefined` est signalé : si c'est une vraie page (`/docs/js/null`), l'ignorer.
- Retour arrière : `git revert` du composant.
