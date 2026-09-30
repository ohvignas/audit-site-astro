---
id: a11y-bandeau-consentement
titre: "Bandeau de consentement aux cookies inaccessible au clavier ou aux lecteurs d'écran"
domaine: Accessibilité
severite_type: haute
effort: M
declencheurs:
  - "manuel:bandeau-consentement"
sources:
  - https://www.w3.org/WAI/WCAG22/Understanding/keyboard.html
  - https://www.w3.org/WAI/WCAG22/Understanding/focus-not-obscured-minimum.html
  - https://www.w3.org/WAI/WCAG22/Understanding/reflow.html
  - https://www.cnil.fr/fr/cookies-et-autres-traceurs/regles/cookies/que-dit-la-loi
  - https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Elements/dialog
---

# Bandeau de consentement aux cookies inaccessible au clavier ou aux lecteurs d'écran

> **En une phrase** : le bandeau de cookies recouvre le contenu, ne se manie pas au clavier, piège le focus ou rend « Refuser » plus difficile que « Accepter », ce qui bloque l'accès au site et pose aussi un problème de conformité au consentement.

## Pourquoi c'est important

Le bandeau est la première chose que voit chaque visiteur. S'il n'est pas utilisable au clavier ou lu par le lecteur d'écran, une partie des utilisateurs ne peut ni le fermer ni accéder au site (recouvrement du contenu, focus enfermé, boutons non atteignables). WCAG 2.1.1, 2.1.2, 2.4.11 (focus non masqué), 1.4.10 (reflow), 4.1.2. Côté consentement, la CNIL demande que refuser soit aussi simple qu'accepter (boutons au même niveau, même visibilité) : un bandeau dont le bouton « Refuser » est caché est un défaut d'accessibilité **et** de conformité. Les outils automatiques ne testent pas ce comportement : **contrôle manuel**.

## Comment le constater soi-même

1. Ouvrez le site en navigation privée (le bandeau s'affiche). Sans souris : Tab. Le focus atteint-il le bandeau dans un ordre logique ? Peut-on choisir « Tout refuser », « Tout accepter » et « Personnaliser » avec Entrée/Espace ?
2. Le bandeau se ferme-t-il après le choix, et le focus revient-il sur la page ? Reste-t-il un moyen de rouvrir les choix (lien « Gérer mes cookies » en pied de page) ?
3. Zoom 200 % et fenêtre de 320 px : le bandeau ne recouvre-t-il pas tout le contenu, et laisse-t-il un défilement possible ?
4. Lecteur d'écran (VoiceOver, NVDA) : le titre et les boutons sont-ils annoncés ?

```bash
grep -rniE "cookie|consent|tarteaucitron|axeptio|didomi|cookiebot|klaro" src public astro.config.* | head
```

## Correction

1. **Deux boutons de même niveau et de même importance visuelle** : « Tout refuser » et « Tout accepter » (plus un lien ou bouton « Personnaliser »). Pas de bouton de refus caché dans un texte gris ou un lien minuscule.
2. **Structure sémantique** : une région nommée avec un titre, non modale (le visiteur peut continuer à naviguer). Ne bloquez le reste de la page (`<dialog>` modal, `inert`) que si le design l'impose.

   ```astro
   <section id="consentement" class="consentement" aria-labelledby="consent-titre" hidden>
     <h2 id="consent-titre">Vos choix sur les cookies</h2>
     <p>Nous utilisons des cookies de mesure d'audience uniquement avec votre accord. <a href="/confidentialite">En savoir plus</a></p>
     <div class="consentement__actions">
       <button type="button" data-choix="refuser">Tout refuser</button>
       <button type="button" data-choix="accepter">Tout accepter</button>
       <button type="button" data-choix="personnaliser">Personnaliser</button>
     </div>
   </section>
   ```
3. **Emplacement dans l'ordre du clavier** : placez le bandeau juste après le lien d'évitement (voir `a11y-lien-evitement-tabindex`), pour qu'il soit atteint par la première tabulation ; sans piège de focus (sauf s'il est réellement modal, avec Échap ou un bouton pour sortir).
4. **Ne pas recouvrir le contenu ni le focus** : bandeau en bas d'écran, hauteur limitée, défilable sur petit écran ; ajoutez du remplissage sous la page (`padding-bottom` égal à la hauteur) tant qu'il est affiché, et `scroll-padding-bottom` pour que le focus reste visible (WCAG 2.4.11).

   ```css
   .consentement { position: fixed; inset: auto 0 0 0; max-block-size: 60vh; overflow: auto; background: #fff; color: #111; border-top: 3px solid #111; padding: 1rem; }
   ```
5. **Après le choix** : enregistrer (cookie ou `localStorage`), masquer le bandeau (`hidden`), et remettre le focus sur un élément logique (le contenu principal, `<main tabindex="-1">`). Ne pas charger les scripts tiers avant consentement (voir `perf-js-tiers`).

   ```ts
   // extrait de <script> dans le composant
   const bandeau = document.querySelector<HTMLElement>('#consentement');
   const choix = localStorage.getItem('consentement');
   if (bandeau && !choix) bandeau.hidden = false;
   bandeau?.addEventListener('click', (e) => {
     const bouton = (e.target as HTMLElement).closest<HTMLButtonElement>('button[data-choix]');
     if (!bouton) return;
     localStorage.setItem('consentement', bouton.dataset.choix ?? 'refuser');
     bandeau.hidden = true;
     document.querySelector<HTMLElement>('main')?.focus();
   });
   ```
6. **Rouvrir les choix** : lien ou bouton « Gérer mes cookies » dans le pied de page, atteignable au clavier.
7. **Solution tierce (CMP)** : choisissez-en une documentée accessible, testez-la au clavier avec les étapes 1 à 4 ; sinon remplacez-la ou surchargez son style (contraste, focus, `aria-*`).
8. Contraste (`a11y-contraste-couleurs`), zone tactile (`a11y-zones-tactiles`) et focus visible (`a11y-focus-visible`) s'appliquent au bandeau comme au reste.

## Critères d'acceptation

- [ ] Le bandeau se manie entièrement au clavier et avec un lecteur d'écran (titre et boutons annoncés).
- [ ] « Tout refuser » et « Tout accepter » sont au même niveau, aussi visibles l'un que l'autre.
- [ ] Le bandeau ne recouvre pas définitivement le contenu ni le focus, à 200 % de zoom et à 320 px.
- [ ] Aucun piège de focus ; le choix est mémorisé ; un lien permet de rouvrir les choix.
- [ ] Aucun script tiers de mesure ou de publicité ne se charge avant un accord.

## Vérification après correction

Refaire les quatre tests ci-dessus, puis vérifier dans l'onglet Réseau des outils de développement qu'aucune requête vers les domaines tiers (analytics, publicités) n'est envoyée avant le choix.

## Pièges et retour arrière

- Certains modules de bandeau réinsèrent leur propre balisage à chaque navigation (avec `<ClientRouter />`) : testez après un changement de page.
- Un bandeau modal sans possibilité de sortie par Échap enferme les utilisateurs du clavier.
- Cette fiche traite l'accessibilité ; la conformité juridique du consentement relève de la CNIL et d'un juriste.
- Retour arrière : restaurer le composant précédent (Git).

## Pour aller plus loin

- WCAG 2.1.2 (pas de piège clavier), 2.4.11 (focus non masqué), 1.4.10 (reflow).
- CNIL, règles sur les cookies et autres traceurs.
- MDN, élément `<dialog>`.
