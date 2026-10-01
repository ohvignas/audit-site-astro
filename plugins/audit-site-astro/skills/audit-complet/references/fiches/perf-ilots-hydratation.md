---
id: perf-ilots-hydratation
titre: Îlots hydratés trop tôt (client:load) ou inutilement (composants sans interaction)
domaine: Performance
severite_type: moyenne
effort: M
declencheurs:
  - "code:îlot\\(s\\) en client:load"
sources:
  - https://docs.astro.build/en/reference/directives-reference/#client-directives
  - https://docs.astro.build/en/concepts/islands/
  - https://web.dev/articles/inp
---

# Îlots hydratés trop tôt (client:load) ou inutilement (composants sans interaction)

> **En une phrase** : des composants React/Vue/Svelte sont chargés et exécutés dès l'ouverture de la page, alors qu'ils ne sont pas utilisés tout de suite, ce qui retarde l'interactivité et gonfle le JavaScript.

## Pourquoi c'est important

Astro n'envoie du JavaScript que pour les composants marqués d'une directive `client:*`. Avec `client:load`, le navigateur télécharge le code du composant (et celui de son framework) et l'exécute immédiatement, en haute priorité. Sur un téléphone d'entrée de gamme, plusieurs îlots `client:load` occupent le thread principal pendant des centaines de ms : le TBT (Total Blocking Time, indicateur de l'INP en labo) monte, et l'INP terrain (seuil Google : 200 ms) souffre. Un composant qui n'a aucune interaction n'a en outre aucune raison d'être un îlot.

## Comment le constater soi-même

```bash
# Où sont les îlots et de quel type
grep -rnE "client:(load|idle|visible|media|only)" src | head -40
# JavaScript envoyé : îlots dans le HTML servi et scripts chargés
curl -s https://SITE/ | grep -oE '<astro-island[^>]*(component-url|client)="[^"]*"' | head
curl -s https://SITE/ | grep -oE '<script[^>]*src="[^"]+"' | head
```

Problème présent : de nombreux `<astro-island client="load">` ou des scripts volumineux au chargement. Corrigé : peu d'îlots au chargement, les autres `idle`/`visible`, et aucun îlot pour du contenu purement statique.

## Correction

1. **Lister les îlots** avec la commande ci-dessus, puis classer chacun :
   - **Aucune interaction** (carte, bandeau, liste, texte) : convertir en composant `.astro` (aucun JavaScript). C'est le meilleur gain.
   - **Interaction immédiate et visible** en haut de page (menu mobile, recherche de l'en-tête) : garder `client:load`, mais alléger.
   - **Interaction secondaire** (widget de chat, formulaire de bas de page, carrousel, avis) : `client:idle` ou `client:visible`.
   - **Mobile uniquement** : `client:media="(max-width: 768px)"`.
2. **Remplacer les directives** :

```astro
---
import MenuMobile from '../components/MenuMobile.tsx';
import Chat from '../components/Chat.tsx';
import Avis from '../components/Avis.tsx';
import Recherche from '../components/Recherche.tsx';
---
<!-- Interaction immédiate en haut de page -->
<MenuMobile client:media="(max-width: 768px)" />
<!-- Hydraté quand le navigateur est libre (timeout facultatif en ms) -->
<Chat client:idle={{ timeout: 2000 }} />
<!-- Hydraté quand le composant approche de l'écran -->
<Avis client:visible={{ rootMargin: '200px' }} />
<Recherche client:load />
```

3. **Charger le code lourd à la demande** dans le composant lui-même, par `import()` dynamique :

```tsx
import { useState, type ComponentType } from 'react';

export default function Chat() {
  const [Widget, setWidget] = useState<ComponentType | null>(null);
  const ouvrir = async () => {
    const mod = await import('./ChatWidget');
    setWidget(() => mod.default);
  };
  return Widget ? <Widget /> : <button onClick={ouvrir}>Discuter avec nous</button>;
}
```

4. **Éviter `client:only`** quand un rendu serveur est possible : il n'affiche rien avant l'exécution du JavaScript (impact SEO traité dans la fiche SEO correspondante) et retarde le contenu.
5. **Un seul framework** : mélanger React, Vue et Svelte charge chaque runtime. Garder celui déjà utilisé le plus souvent.
6. Relire le résultat : `npm run build` puis comparer la taille du dossier `dist/client/_astro` avant et après.

## Critères d'acceptation

- [ ] Chaque `client:load` restant est justifié par une interaction visible et utile immédiatement
- [ ] Les composants sans interaction sont des `.astro` (0 Ko de JavaScript)
- [ ] TBT mobile en baisse mesurable (cible : < 200 ms) ; pas de régression fonctionnelle (menus, formulaires, recherche)
- [ ] Aucun contenu principal supprimé du HTML servi (vérifier avec `curl`)

## Vérification après correction

```bash
grep -rc "client:load" src | grep -v ":0"
python3 scripts/astro_scan.py /chemin/projet --out /tmp/verif
bash scripts/lighthouse_run.sh /tmp/verif https://SITE/
```

## Pièges et retour arrière

- Un `client:visible` sur un composant que l'utilisateur veut utiliser tout de suite donne un retard visible : tester au doigt sur mobile.
- Un composant hydraté tard peut changer de hauteur et provoquer un décalage de mise en page : réserver sa place (`min-height`).
- Retour arrière : remettre `client:load` sur le composant concerné.

## Pour aller plus loin

- https://docs.astro.build/en/reference/directives-reference/#client-directives : `client:load`, `idle`, `visible`, `media`, `only`.
- https://docs.astro.build/en/concepts/islands/ : architecture en îlots.
- https://web.dev/articles/inp : ce que mesure l'INP et pourquoi le JavaScript l'affecte.
