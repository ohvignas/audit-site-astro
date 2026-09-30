---
id: code-server-islands
titre: Parties personnalisées qui empêchent de prérendre ou de mettre en cache la page
domaine: Code
severite_type: basse
effort: M
declencheurs:
  - "code:isoler en server islands"
  - "code:Des composants lisent cookies/session"
versions_astro: ">=5.0"
sources:
  - https://docs.astro.build/en/guides/server-islands/
  - https://docs.astro.build/en/reference/directives-reference/
---

# Parties personnalisées qui empêchent de prérendre ou de mettre en cache la page

> **En une phrase** : un composant qui lit les cookies ou la session (menu « Mon compte », panier) oblige à rendre toute la page à chaque requête ; en l'isolant en server island, le reste de la page peut être prérendu ou mis en cache.

## Pourquoi c'est important

Dès qu'un seul composant lit `Astro.cookies` ou `Astro.locals`, la page entière devient dépendante de la requête : impossible de la prérendre ou de la servir depuis un cache partagé, donc TTFB plus élevé et charge serveur inutile. Avec `server:defer` (Astro 5.0), la page est servie immédiatement avec un contenu de remplacement, puis le fragment personnalisé est rendu à la demande.

## Comment le constater soi-même

```bash
grep -rnE "Astro\.(cookies|locals)" src/components src/layouts       # composants qui personnalisent
grep -rn "server:defer" src                                           # déjà des îlots serveur ?
curl -sI https://SITE/ | grep -iE 'cache-control|set-cookie|vary'     # la page publique porte-t-elle des cookies / Vary: Cookie ?
```

## Correction

1. Repérer le composant personnalisé (menu utilisateur, panier, bandeau « bonjour Prénom »). Il ne doit contenir que la partie dépendante de l'utilisateur.
2. Vérifier qu'un **adapter** est installé (les server islands en ont besoin) : `npx astro add node`.
3. Lui ajouter `server:defer` et un contenu de remplacement dans le slot `fallback` :
   ```astro
   ---
   // src/layouts/Base.astro
   import MenuUtilisateur from '../components/MenuUtilisateur.astro';
   ---
   <header>
     <a href="/">Accueil</a>
     <MenuUtilisateur server:defer>
       <a slot="fallback" href="/connexion">Se connecter</a>
     </MenuUtilisateur>
   </header>
   ```
   ```astro
   ---
   // src/components/MenuUtilisateur.astro
   const session = Astro.cookies.get('session')?.value;
   ---
   {session ? <a href="/mon-compte">Mon compte</a> : <a href="/connexion">Se connecter</a>}
   ```
4. Rendre ensuite le reste de la page prérendu (`export const prerender = true;`, voir `code-prerender-ssr-opportunites`) ou mise en cache.
5. Contraintes des props : elles doivent être sérialisables (objets simples, nombres, chaînes, tableaux, `Date`, `Map`, `Set`… mais pas de fonctions ni de références circulaires). Éviter les props volumineuses : au-delà de 2048 octets d'URL, Astro passe en requête POST, non mise en cache par les navigateurs.
6. Derrière un déploiement en plusieurs instances ou en mise à jour progressive, définir la même clé de chiffrement partout : variable d'environnement `ASTRO_KEY` (générée par `npx astro create-key`).

## Critères d'acceptation

- [ ] Le composant personnalisé est chargé via `server:defer` avec un `fallback` lisible
- [ ] La page publique ne lit plus de cookies au rendu principal (elle peut être prérendue ou mise en cache)
- [ ] `curl -sI` de la page publique ne montre plus de `Set-Cookie` ni `Vary: Cookie` inutiles
- [ ] Aucune régression : utilisateur connecté toujours reconnu, pas de saut de mise en page à l'arrivée du fragment (réserver la place du fallback en CSS)

## Vérification après correction

```bash
npx astro build && curl -sI https://SITE/ | grep -i cache-control
python3 scripts/astro_scan.py . --out /tmp/verif   # le constat « isoler en server islands » doit disparaître
```

## Pièges et retour arrière

- Dans un server island, `Astro.url` renvoie `/_server-islands/NomDuComposant` et non l'URL de la page : lire la page d'origine dans l'en-tête `Referer`.
- Le fragment ajoute une requête réseau après le chargement : ne pas l'utiliser pour du contenu essentiel au référencement (le fallback est ce que voient les robots sans JS).
- Retour arrière : retirer `server:defer` et le slot `fallback` ; le composant redevient rendu avec la page.

## Pour aller plus loin

- https://docs.astro.build/en/guides/server-islands/ : syntaxe, props, cache, `ASTRO_KEY`.
- https://docs.astro.build/en/reference/directives-reference/ : directive `server:defer`.
