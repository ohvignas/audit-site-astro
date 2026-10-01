---
id: a11y-zoom-viewport-refresh
titre: "Zoom bloqué (meta viewport) et redirection automatique par meta refresh"
domaine: Accessibilité
severite_type: haute
effort: S
declencheurs:
  - "crawl:zoom_bloque"
  - "lighthouse:meta-viewport|meta-refresh"
  - "lighthouse:user-scalable=\"no\"|maximum-scale|http-equiv=\"refresh\""
sources:
  - https://www.w3.org/WAI/WCAG22/Understanding/resize-text.html
  - https://www.w3.org/WAI/WCAG22/Understanding/reflow.html
  - https://www.w3.org/WAI/WCAG22/Understanding/timing-adjustable.html
  - https://dequeuniversity.com/rules/axe/4.10/meta-viewport
  - https://docs.astro.build/en/guides/routing/#configured-redirects
---

# Zoom bloqué (meta viewport) et redirection automatique par meta refresh

> **En une phrase** : la balise `viewport` empêche les visiteurs d'agrandir la page (`user-scalable=no`, `maximum-scale` faible), ou une balise `meta refresh` redirige/recharge la page sans que l'utilisateur ne le décide.

## Pourquoi c'est important

Beaucoup de personnes malvoyantes agrandissent le texte en pinçant l'écran ; bloquer le zoom leur retire l'accès au contenu. WCAG 1.4.4 (redimensionnement du texte à 200 %, AA) et 1.4.10 (reflow, AA) l'exigent ; RGAA 10.4 et 10.11. Un `meta refresh` avec délai est lu comme une redirection ou un rechargement inattendu qui interrompt la lecture (WCAG 2.2.1, 2.2.4, 3.2.5) et est mal géré par le SEO (préférez une redirection serveur 301).

## Comment le constater soi-même

```bash
curl -s https://exemple.fr/ | grep -oiE '<meta[^>]*(viewport|http-equiv="?refresh)[^>]*>'
grep -rniE "user-scalable|maximum-scale|http-equiv=.refresh" src public | head
```

Problème : `user-scalable=no`, `user-scalable=0` ou `maximum-scale=1` (Lighthouse exige `maximum-scale` d'au moins 5) ; toute balise `http-equiv="refresh"`. Corrigé : `<meta name="viewport" content="width=device-width, initial-scale=1">`, aucune balise `refresh`.

## Correction

1. **Viewport** : dans la mise en page commune (`src/layouts/Base.astro`, dans le `<head>`), utilisez uniquement :

   ```html
   <meta name="viewport" content="width=device-width, initial-scale=1" />
   ```

   Supprimez `user-scalable=no`, `user-scalable=0`, `maximum-scale=1`, `minimum-scale`. Vérifiez aussi les composants et thèmes qui injectent leur propre viewport (doublons dans le `<head>`).
2. **Conséquence sur la mise en page** : pensez le site « fluide » (unités relatives `rem`, `%`, `min()`, `clamp()`), sans largeurs fixes, pour qu'il tienne à 320 px et à 200 % de zoom sans défilement horizontal (test : fenêtre 1280 px, zoom navigateur 400 % ≈ 320 px).
3. **Bloquer le zoom au double-tap sans bloquer le pincement** (raison courante de `user-scalable=no`) : `touch-action: manipulation;` sur les boutons.

   ```css
   button, a, input { touch-action: manipulation; }
   ```
4. **`meta refresh`** : remplacez par une redirection serveur.
   - Astro (redirection fixe). Attention : en **site statique**, Astro génère pour chaque redirection une petite page HTML contenant justement un `meta refresh` ; en rendu à la demande (SSR) c'est une vraie réponse HTTP 301. Pour un site statique, faites donc plutôt la redirection au serveur web (ligne suivante) :

     ```js
     // astro.config.mjs
     import { defineConfig } from 'astro/config';
     export default defineConfig({
       redirects: {
         '/ancienne-page': { status: 301, destination: '/nouvelle-page' },
       },
     });
     ```
   - nginx : `location = /ancienne-page { return 301 /nouvelle-page; }` ; Caddy : `redir /ancienne-page /nouvelle-page permanent`.
   - Rechargement périodique (tableau de bord, compteur) : proposer un bouton « Actualiser » ou mettre à jour la zone par JavaScript, avec l'option de l'arrêter.
5. Contrôlez que le viewport n'est pas modifié par un script ou un plugin (`document.querySelector('meta[name=viewport]')`).

## Critères d'acceptation

- [ ] La balise viewport ne contient ni `user-scalable=no` ni `maximum-scale` inférieur à 5.
- [ ] Zoom à 200 % (et 400 % à 320 px) sans perte de contenu ni défilement horizontal, hors tableaux et éléments qui exigent une mise en page bidimensionnelle.
- [ ] Aucune balise `<meta http-equiv="refresh">` (redirections faites au serveur).
- [ ] Lighthouse : `meta-viewport` et `meta-refresh` réussis.

## Vérification après correction

```bash
curl -s https://exemple.fr/ | grep -oiE '<meta[^>]*(viewport|refresh)[^>]*>'
curl -sI https://exemple.fr/ancienne-page | head -3     # 301 et Location
```

## Pièges et retour arrière

- Sur iOS, un champ de saisie dont la police est inférieure à 16 px déclenche un zoom automatique à la saisie ; cela se corrige avec `font-size: 1rem` sur les champs, pas en bloquant le zoom.
- Ne mettez pas de redirection JavaScript (`location.href=`) dans le `<head>` pour remplacer un `meta refresh` : préférez le serveur.
- Retour arrière : ne pas remettre `user-scalable=no`.

## Pour aller plus loin

- WCAG 1.4.4 (redimensionnement du texte) et 1.4.10 (reflow).
- Astro, routage : redirections configurées.
- Lighthouse, audit `meta-viewport`.
