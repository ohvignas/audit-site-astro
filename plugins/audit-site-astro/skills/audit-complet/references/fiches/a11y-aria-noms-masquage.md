---
id: a11y-aria-noms-masquage
titre: "Composants ARIA sans nom accessible et contenus masqués mais focalisables (aria-hidden)"
domaine: Accessibilité
severite_type: haute
effort: M
declencheurs:
  - "lighthouse:aria-hidden-body|aria-hidden-focus|aria-text|aria-dialog-name|aria-input-field-name|aria-meter-name|aria-progressbar-name|aria-toggle-field-name|aria-tooltip-name|aria-treeitem-name"
  - "lighthouse:aria-hidden=\"true\"|descendants sélectionnables|role=text|role=\"dialog\"|champs de saisie ARIA n'ont pas|éléments ARIA `(meter|progressbar|tooltip|treeitem)`|champs d'activation/de désactivation ARIA"
sources:
  - https://www.w3.org/WAI/WCAG22/Understanding/name-role-value.html
  - https://www.w3.org/WAI/ARIA/apg/patterns/dialog-modal/
  - https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Global_attributes/inert
  - https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Elements/dialog
  - https://dequeuniversity.com/rules/axe/4.10/aria-hidden-focus
---

# Composants ARIA sans nom accessible et contenus masqués mais focalisables (aria-hidden)

> **En une phrase** : des boîtes de dialogue, jauges ou interrupteurs n'ont pas de nom, ou un contenu marqué « caché » pour les lecteurs d'écran reste atteignable au clavier, ce qui crée des « fantômes » impossibles à comprendre.

## Pourquoi c'est important

Deux familles d'erreurs, fréquentes avec les menus mobiles, modales, sliders et chats : (1) un composant avec un rôle (`dialog`, `progressbar`, `switch`, `tooltip`...) sans nom, que le lecteur d'écran annonce sans contexte ; (2) `aria-hidden="true"` sur un bloc qui contient des liens ou boutons focalisables : le clavier y accède mais le lecteur d'écran ne dit rien, l'utilisateur « tabule dans le vide ». `aria-hidden="true"` sur `<body>` rend toute la page invisible aux lecteurs d'écran. WCAG 4.1.2, 1.3.1, 2.4.3 ; RGAA thématique 7.

## Comment le constater soi-même

```bash
grep -rn 'aria-hidden="true"' src | head -30
grep -rnE 'role="(dialog|alertdialog|progressbar|meter|switch|tooltip|treeitem)"' src | head -20
```

Navigateur : tabulez sur la page ; si le focus « disparaît » (rien de visible qui change) sur un élément d'un menu fermé ou d'un carrousel, un contenu masqué est encore focalisable. Inspecteur, Accessibilité : vérifiez que le composant a un « Name ».

## Correction

1. **Donner un nom** à chaque composant à rôle : `aria-labelledby` (vers un titre visible, à privilégier) ou `aria-label`.

   ```astro
   <div role="dialog" aria-modal="true" aria-labelledby="titre-modale">
     <h2 id="titre-modale">Prendre rendez-vous</h2>
     ...
   </div>
   <div role="progressbar" aria-label="Avancement de l'envoi" aria-valuemin="0" aria-valuemax="100" aria-valuenow="40"></div>
   <button type="button" role="switch" aria-checked="false" aria-label="Recevoir la newsletter"></button>
   ```
2. **Préférer les éléments natifs** : `<dialog>` avec `showModal()` (nom via `aria-labelledby`, focus géré), `<progress value="40" max="100">` avec label, `<input type="checkbox" role="switch">`, `<meter>`.
3. **Contenu masqué mais focalisable** : un contenu qui doit disparaître pour tout le monde (menu fermé, panneau d'accordéon replié, diapositive non visible) doit être retiré du focus. Utilisez `hidden`, `display: none`, ou l'attribut `inert`, **au lieu de** `aria-hidden` seul.

   ```html
   <div id="menu-mobile" hidden>...</div>
   <div class="fond-page" inert>...</div>   <!-- pendant qu'une modale est ouverte -->
   ```

   Si `aria-hidden="true"` est justifié (icône décorative), l'élément ne doit contenir aucun lien, bouton ou champ focalisable ; sinon ajoutez `tabindex="-1"` ou `inert` à ces enfants.
4. **`aria-hidden="true"` sur `<body>`** : le retirer. Ce défaut vient souvent d'une bibliothèque de modales qui masque le reste de la page ; appliquez `aria-hidden` (ou mieux `inert`) sur les frères de la modale, pas sur le `<body>`.
5. **`role="text"`** (`aria-text`) : ne pas l'utiliser avec des enfants focalisables ; supprimer ce rôle non standard.
6. **Infobulles** (`role="tooltip"`) : nom = texte de l'infobulle, reliée à son déclencheur par `aria-describedby` ; elle doit apparaître aussi au focus clavier, pas seulement au survol, et rester affichée jusqu'à fermeture (WCAG 1.4.13).
7. Îlots React / Svelte / Vue : préférez les composants d'une bibliothèque accessible (Radix, Headless UI, Ark UI) pour modales, onglets, tooltips.

## Critères d'acceptation

- [ ] Chaque composant à rôle a un nom (Lighthouse : audits `aria-*-name` réussis).
- [ ] `aria-hidden="true"` ne recouvre aucun élément focalisable et n'est pas posé sur `<body>`.
- [ ] Menus, modales, carrousels fermés : le focus clavier ne peut plus y entrer.
- [ ] La page fonctionne comme avant pour un utilisateur voyant.

## Vérification après correction

```bash
npx lighthouse https://exemple.fr/ --only-categories=accessibility --quiet --output=json --output-path=/tmp/a11y.json --locale=fr
python3 -c "
import json; a=json.load(open('/tmp/a11y.json'))['audits']
ids=['aria-hidden-body','aria-hidden-focus','aria-dialog-name','aria-input-field-name','aria-progressbar-name','aria-toggle-field-name','aria-tooltip-name','aria-treeitem-name','aria-meter-name','aria-text']
print({k:a[k]['score'] for k in ids if k in a and a[k]['score'] not in (None,1)})"
```

## Pièges et retour arrière

- `inert` n'est pas géré par de très vieux navigateurs : le combiner avec `hidden` pour les panneaux fermés.
- Une modale mal fermée laisse `inert` ou `aria-hidden` sur la page : nettoyez à la fermeture (y compris avec Échap).
- Retour arrière : restaurer l'attribut d'origine ; testez au clavier.

## Pour aller plus loin

- W3C APG, modèle de dialogue modal : nom, focus, fermeture.
- MDN, attribut `inert` et élément `<dialog>`.
- Lighthouse, audit `aria-hidden-focus`.
- RGAA, thématique Scripts.
