---
id: a11y-noms-boutons-liens
titre: "Boutons et liens sans nom accessible (icônes, liens vides, « En savoir plus » répétés)"
domaine: Accessibilité
severite_type: haute
effort: S
declencheurs:
  - "crawl:lien_sans_nom"
  - "crawl:bouton_sans_nom"
  - "lighthouse:button-name|link-name|input-button-name|aria-command-name|label-content-name-mismatch|identical-links-same-purpose"
  - "lighthouse:Les boutons n'ont pas de nom accessible|Les liens n'ont pas de nom visible|boutons d'entrée ne contiennent pas de texte visible|`button`, `link` et `menuitem` n'ont pas|libellés de texte visibles ne sont pas associés|liens identiques n'ont pas la même fonction"
sources:
  - https://www.w3.org/WAI/WCAG22/Understanding/name-role-value.html
  - https://www.w3.org/WAI/WCAG22/Understanding/label-in-name.html
  - https://www.w3.org/WAI/WCAG22/Understanding/link-purpose-in-context.html
  - https://dequeuniversity.com/rules/axe/4.10/button-name
  - https://dequeuniversity.com/rules/axe/4.10/link-name
  - https://accessibilite.numerique.gouv.fr/methode/criteres-et-tests/#6.1
---

# Boutons et liens sans nom accessible (icônes, liens vides, « En savoir plus » répétés)

> **En une phrase** : des boutons ou liens ne contiennent aucun texte lisible par un lecteur d'écran (icône seule, image sans alt), ou plusieurs liens s'appellent tous « En savoir plus », donc personne ne sait où ils mènent.

## Pourquoi c'est important

Un lecteur d'écran annonce « bouton » ou « lien » sans rien d'autre : l'utilisateur ne peut pas deviner que l'icône en haut à droite ouvre le menu ou que le lien du logo mène à l'accueil. Les personnes qui pilotent l'ordinateur à la voix (« clique sur Menu ») sont aussi bloquées si le nom visible ne correspond pas au nom accessible (WCAG 2.5.3, « Label in Name »). Critères WCAG 4.1.2, 2.4.4 (but du lien) ; RGAA thématique 6 (Liens) et 11 (Formulaires, boutons).

## Comment le constater soi-même

```bash
# Boutons / liens vides dans le code
grep -rnE "<button[^>]*>[[:space:]]*(<svg|<img|<i )" src | head -20
grep -rnE "<a [^>]*>[[:space:]]*(<svg|<img)" src | head -20
grep -rniE ">[[:space:]]*(en savoir plus|lire la suite|cliquez ici|voir plus)[[:space:]]*<" src | head -20
```

Dans le navigateur : Inspecteur, onglet Accessibilité, champ « Name » de l'élément (vide = problème). Lighthouse donne le sélecteur de chaque élément en échec.

## Correction

1. **Bouton avec icône seule** : ajouter un nom. Trois manières, dans l'ordre de préférence.

   ```astro
   ---
   // src/components/BoutonMenu.astro
   ---
   <!-- 1. Texte masqué visuellement (fonctionne partout, traduit par le navigateur) -->
   <button type="button" class="bouton-menu" aria-expanded="false" aria-controls="menu-principal">
     <svg aria-hidden="true" focusable="false" width="24" height="24" viewBox="0 0 24 24">
       <path d="M3 6h18M3 12h18M3 18h18" stroke="currentColor" stroke-width="2" fill="none" />
     </svg>
     <span class="sr-only">Menu</span>
   </button>

   <!-- 2. aria-label (si le texte visible n'existe pas) -->
   <button type="button" aria-label="Fermer la fenêtre">
     <svg aria-hidden="true" focusable="false" width="16" height="16"><path d="M2 2l12 12M14 2L2 14" stroke="currentColor" /></svg>
   </button>
   ```

   ```css
   /* Classe de masquage visuel (Tailwind fournit déjà `sr-only`) */
   .sr-only {
     position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px;
     overflow: hidden; clip: rect(0, 0, 0, 0); white-space: nowrap; border: 0;
   }
   ```
2. **Icône décorative dans un bouton qui a déjà du texte** : `aria-hidden="true"` sur l'`<svg>` pour qu'elle ne soit pas lue.
3. **Lien contenant seulement une image** (logo) : l'`alt` de l'image devient le nom du lien.

   ```astro
   <a href="/"><img src="/logo.svg" alt="Exemple, retour à l'accueil" width="160" height="40" /></a>
   ```
4. **Lien vide** (`<a href="/x"></a>`, ancre décorative) : supprimer ou lui donner un contenu. Une carte cliquable entière : un seul lien avec un texte explicite (le titre), les autres éléments non focalisables.
5. **Liens « En savoir plus » répétés** : rendre le libellé unique, en gardant le texte visible court.

   ```astro
   <a href={`/formations/${slug}`}>
     En savoir plus<span class="sr-only"> sur la formation {titre}</span>
   </a>
   ```

   Ou `aria-label={`En savoir plus sur ${titre}`}` (le nom accessible doit **commencer par** ou contenir le texte visible, WCAG 2.5.3).
6. **Nom visible ≠ nom accessible** (`label-content-name-mismatch`) : si le bouton affiche « Rechercher », son `aria-label` ne doit pas être « Lancer la requête » ; supprimez l'`aria-label` ou faites-le contenir « Rechercher ».
7. **`<input type="submit|button" value="">`** : renseigner `value` (texte visible) ; `<input type="image">` : voir `a11y-images-alt`.
8. Les composants réutilisés (bouton d'icône, carte) : corrigez le composant, pas chaque page ; exigez une propriété `label` obligatoire dans ses `Props` TypeScript.

## Critères d'acceptation

- [ ] Lighthouse : « Les boutons ont un nom accessible » et « Les liens ont un nom visible » réussis.
- [ ] Aucun lien ou bouton sans texte ni `aria-label` (inspection de l'arbre d'accessibilité).
- [ ] Les liens qui se ressemblent ont des noms distincts ou un contexte précisé.
- [ ] Le nom accessible contient le texte visible (essai à la voix sur Mac/iOS ou Windows).
- [ ] Rendu visuel inchangé.

## Vérification après correction

```bash
npx lighthouse https://exemple.fr/ --only-categories=accessibility --quiet --output=json --output-path=/tmp/a11y.json --locale=fr
python3 -c "import json; a=json.load(open('/tmp/a11y.json'))['audits']; [print(k, a[k]['score']) for k in ('button-name','link-name','input-button-name','aria-command-name') if k in a]"
```

## Pièges et retour arrière

- `aria-label` sur un élément qui a du texte visible **remplace** ce texte pour le lecteur d'écran : ne l'utilisez pas pour « améliorer » un libellé qui existe.
- `title=""` seul n'est pas un nom fiable (non lu partout, invisible au clavier).
- L'`aria-label` n'est pas traduit par la traduction automatique du navigateur : préférez le texte masqué visuellement si le site est multilingue.
- Retour arrière : retirer l'attribut ajouté ; aucun effet visuel.

## Pour aller plus loin

- WCAG 4.1.2 (nom, rôle, valeur) et 2.5.3 (étiquette dans le nom).
- Lighthouse, audits `button-name` et `link-name`.
- RGAA, thématique Liens.
