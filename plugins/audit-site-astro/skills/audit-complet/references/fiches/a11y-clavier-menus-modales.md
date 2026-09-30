---
id: a11y-clavier-menus-modales
titre: "Navigation au clavier : menus, modales, accordéons et widgets inutilisables sans souris"
domaine: Accessibilité
severite_type: haute
effort: M
declencheurs:
  - "manuel:clavier-menus-modales"
sources:
  - https://www.w3.org/WAI/WCAG22/Understanding/keyboard.html
  - https://www.w3.org/WAI/WCAG22/Understanding/no-keyboard-trap.html
  - https://www.w3.org/WAI/ARIA/apg/patterns/dialog-modal/
  - https://www.w3.org/WAI/ARIA/apg/patterns/disclosure/examples/disclosure-navigation/
  - https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Elements/dialog
  - https://accessibilite.numerique.gouv.fr/methode/criteres-et-tests/#12.8
---

# Navigation au clavier : menus, modales, accordéons et widgets inutilisables sans souris

> **En une phrase** : le menu mobile, la fenêtre modale, le carrousel ou le chat ne se manipulent qu'à la souris, ou piègent le focus, ce qui bloque les personnes qui naviguent au clavier ou avec un lecteur d'écran.

## Pourquoi c'est important

Tout ce qui se fait à la souris doit se faire au clavier (WCAG 2.1.1, niveau A) sans piéger l'utilisateur (2.1.2) et dans un ordre logique (2.4.3). Un menu qui ne s'ouvre qu'au survol, une modale qui laisse le focus filer derrière elle ou qui ne se ferme pas avec Échap, un formulaire de chat atteint seulement après 80 tabulations : autant de portes fermées, y compris pour les personnes avec un handicap moteur temporaire. RGAA thématique 7 (Scripts) et 12 (Navigation). Lighthouse ne teste pas ces comportements : **contrôle manuel**.

## Comment le constater soi-même

Sans toucher la souris, sur chaque gabarit :

| Test | Attendu |
|---|---|
| Tab / Maj+Tab sur toute la page | Tout ce qui est cliquable est atteignable, dans l'ordre visuel |
| Menu mobile : Entrée/Espace sur le bouton | S'ouvre ; le focus reste logique ; Échap le referme et rend le focus au bouton |
| Modale : ouverture | Le focus entre dans la modale ; Tab reste dedans ; Échap ferme ; le focus revient au déclencheur |
| Menu déroulant au survol | Aussi ouvrable au clavier (focus ou touche) |
| Accordéon, onglets | Entrée/Espace/flèches ; l'état est annoncé (`aria-expanded`) |
| Carrousel, chat, vidéo | Boutons atteignables, pause possible |
| Aucun piège | On peut toujours sortir d'un widget avec le clavier |

```bash
grep -rnE "onclick=|@click|mouseenter|mouseover|:hover" src | head -30    # comportements potentiellement réservés à la souris
grep -rnE '<div[^>]*(onclick|role="button")' src | head                    # faux boutons
```

## Correction

1. **Utiliser les éléments natifs** : `<button>`, `<a href>`, `<details>`, `<dialog>`, `<select>`. Ils gèrent clavier et lecteurs d'écran sans code.
2. **Menu de navigation mobile** : modèle « bouton de révélation » (disclosure), pas de `role="menu"`.

   ```astro
   <nav aria-label="Navigation principale">
     <button type="button" id="bouton-menu" aria-expanded="false" aria-controls="liste-menu">Menu</button>
     <ul id="liste-menu" hidden>
       <li><a href="/">Accueil</a></li>
       <li><a href="/contact">Contact</a></li>
     </ul>
   </nav>

   <script>
     const bouton = document.querySelector<HTMLButtonElement>('#bouton-menu');
     const liste = document.querySelector<HTMLElement>('#liste-menu');
     if (bouton && liste) {
       const basculer = (ouvrir: boolean) => {
         bouton.setAttribute('aria-expanded', String(ouvrir));
         liste.hidden = !ouvrir;
       };
       bouton.addEventListener('click', () => basculer(liste.hidden));
       document.addEventListener('keydown', (e) => {
         if (e.key === 'Escape' && !liste.hidden) { basculer(false); bouton.focus(); }
       });
     }
   </script>
   ```
3. **Fenêtre modale** : `<dialog>` natif avec `showModal()` (piège de focus, Échap, arrière-plan rendu inerte, retour du focus au déclencheur gérés par le navigateur).

   ```astro
   <button type="button" id="ouvrir">Prendre rendez-vous</button>
   <dialog id="rdv" aria-labelledby="rdv-titre">
     <h2 id="rdv-titre">Prendre rendez-vous</h2>
     <form method="dialog"><button>Fermer</button></form>
   </dialog>
   <script>
     const dlg = document.querySelector<HTMLDialogElement>('#rdv');
     document.querySelector('#ouvrir')?.addEventListener('click', () => dlg?.showModal());
   </script>
   ```
4. **Menu au survol** : ajoutez l'ouverture au focus (`:focus-within`) et au clic ; ne réservez rien à `:hover`. WCAG 1.4.13 : le contenu qui apparaît au survol doit rester affiché (ne pas disparaître si on le survole) et pouvoir être fermé (Échap).
5. **Accordéon** : `<details><summary>`. Pour les onglets (`role="tablist"`), suivez le modèle APG (flèches, `aria-selected`) ou évitez-les : une simple suite de sections suffit souvent.
6. **Carrousel** : boutons précédent/suivant (vrais `<button>`), pause obligatoire pour tout défilement automatique de plus de 5 secondes (WCAG 2.2.2), pas de contenu accessible uniquement par glissement.
7. **Chat ou widget flottant** : bouton d'ouverture focalisable avec nom (« Ouvrir le chat »), zone de messages avec `aria-live="polite"`, focus géré à l'ouverture et à la fermeture, ne recouvre pas le contenu ni le focus (`a11y-focus-visible`).
8. **Ordre** : l'ordre du DOM = l'ordre visuel ; évitez `order:` en CSS et les `tabindex` positifs (voir `a11y-lien-evitement-tabindex`).
9. **Îlots** React/Svelte/Vue : privilégier une bibliothèque accessible (Radix UI, Headless UI, Ark UI) pour modales, menus, onglets.

## Critères d'acceptation

- [ ] Le site entier se parcourt et s'utilise au clavier, sur ordinateur et avec un lecteur d'écran (NVDA/VoiceOver) pour les composants principaux.
- [ ] Menu, modale, chat : ouverture, fermeture par Échap, retour du focus au déclencheur.
- [ ] Aucun piège de focus, aucun contenu réservé au survol.
- [ ] États annoncés (`aria-expanded`, `aria-selected`) et mis à jour.

## Vérification après correction

Refaire le tableau ci-dessus au clavier, puis avec VoiceOver (macOS : Cmd+F5) sur la modale et le menu. Lancer aussi `npx lighthouse ... --only-categories=accessibility` pour contrôler les erreurs ARIA induites (`a11y-aria-roles-attributs`).

## Pièges et retour arrière

- `role="menu"` impose une gestion de touches complexe : pour une navigation de site, utilisez plutôt le modèle de révélation ci-dessus.
- Une modale ouverte sans `showModal()` (simple `open`) ne piège ni ne masque l'arrière-plan.
- Retour arrière : restaurer le composant (Git) ; ne supprimez pas la gestion clavier pour « simplifier ».

## Pour aller plus loin

- WCAG 2.1.1 clavier, 2.1.2 pas de piège au clavier.
- W3C APG : modèles de dialogue modal et de navigation par révélation.
- MDN, élément `<dialog>`.
- RGAA, thématiques Scripts et Navigation.
