---
id: contenu-fuites-rendu
titre: "Valeurs techniques affichées : undefined, NaN, null, [object Object], Invalid Date"
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

- [ ] `fuite_rendu` absent de `data/crawl/issues.json`
- [ ] Les pages concernées affichent la valeur réelle ou masquent proprement le bloc
- [ ] Aucune régression : build OK (`astro check` sans nouvelle erreur)

## Vérification après correction

```bash
python3 scripts/crawl_site.py https://SITE/ --out /tmp/verif/crawl --liens-externes 0
python3 -c "import json;print(json.load(open('/tmp/verif/crawl/issues.json')).get('fuite_rendu',{}).get('count',0))"   # 0
```

## Ce que l'outil lit, et ce qu'il laisse passer

- Lu : le texte visible, `alt` / `title` / `aria-label` / `placeholder` / `value`, les liens (`/formations/undefined`, `?id=undefined`, `tel:undefined`, `mailto:undefined`), le `<title>` et les meta description / `og:` / `twitter:` (coupés sur `|`, `-`, `—`, `·` : un segment réduit au jeton est une fuite).
- Signalé partout : `[object Object]`, `Invalid Date`, `{{ variable }}`.
- Signalé quand le mot se comporte comme une valeur : seul dans son élément (`<span>undefined</span>`), collé à un prix, une unité ou un nombre (« NaN min », « NaN inscrits », « NaN/NaN/NaN »), après une étiquette courte (« Prix : undefined ») ou une formule (« Bonjour undefined », « Écrit par undefined »).
- Laissé passer : `<code>`, `<pre>`, `<kbd>`, `<samp>`, scripts, JSON-LD ; la prose (« la valeur null indique… », « NaN means Not-a-Number ») ; les liens vers un autre site (MDN) ; « nul », « nulle ». Sur une page qui contient `<code>` ou `<pre>` (tutoriel), les jetons nus d'un tableau ou d'une liste ne sont pas signalés ; trois jetons nus distincts sur une même page sont traités comme une liste de documentation.

## Pièges et retour arrière

- Un article technique écrit sans `<code>` ni `<pre>` (tableau « Valeur / Signification », cellules `undefined`, `null`, `NaN` en texte brut) peut être signalé à tort : lire l'extrait de la signature, qui reproduit le texte de la page, et ignorer le constat s'il s'agit de documentation.
- Un lien vers une page de ce même site dont le chemin finit par `/null` ou `/undefined` est signalé : si c'est une vraie page (`/docs/js/null`), l'ignorer.
- Retour arrière : `git revert` du composant.
