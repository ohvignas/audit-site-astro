---
id: a11y-formulaires-labels
titre: "Champs de formulaire sans étiquette, avec plusieurs étiquettes ou autocomplete invalide"
domaine: Accessibilité
severite_type: haute
effort: M
declencheurs:
  - "lighthouse:label(?!-content)|select-name|form-field-multiple-labels|autocomplete-valid"
  - "lighthouse:éléments de formulaire ne sont pas associés à des libellés|Certains éléments ne sont associés à aucun élément de libellé|champs de formulaire comprennent plusieurs libellés|attributs `autocomplete` ne sont pas utilisés correctement"
sources:
  - https://www.w3.org/WAI/WCAG22/Understanding/labels-or-instructions.html
  - https://www.w3.org/WAI/WCAG22/Understanding/identify-input-purpose.html
  - https://www.w3.org/WAI/WCAG22/Understanding/error-identification.html
  - https://www.w3.org/WAI/tutorials/forms/labels/
  - https://developer.mozilla.org/en-US/docs/Web/HTML/Attributes/autocomplete
  - https://accessibilite.numerique.gouv.fr/methode/criteres-et-tests/#11.1
---

# Champs de formulaire sans étiquette, avec plusieurs étiquettes ou autocomplete invalide

> **En une phrase** : des champs (e-mail, message, liste déroulante) ne sont pas reliés à un libellé, si bien qu'un lecteur d'écran annonce « champ de saisie » sans dire ce qu'il faut écrire, et que le formulaire de contact peut devenir inutilisable.

## Pourquoi c'est important

Le formulaire est l'endroit où le site gagne de l'argent (contact, devis, inscription). Sans `<label>` relié au champ, une personne aveugle ne sait pas quoi saisir, une personne qui utilise la commande vocale ne peut pas « cliquer sur Email », et le clic sur le libellé n'active pas le champ (petite cible pour tous). WCAG 1.3.1, 3.3.2, 4.1.2 ; `autocomplete` adapté : WCAG 1.3.5 (AA) ; messages d'erreur : 3.3.1 et 3.3.3. RGAA thématique 11 (Formulaires). Un formulaire accessible convertit aussi mieux sur mobile.

## Comment le constater soi-même

```bash
# Champs sans label associé (heuristique : input/select/textarea sans id ni aria-label)
grep -rnE "<(input|select|textarea)\b" src | grep -vE 'type="(hidden|submit|button|image)"' | grep -vE 'aria-label|aria-labelledby' | head -30
grep -rn "placeholder=" src | head -20     # un placeholder n'est PAS un label
```

Navigateur : cliquez sur le libellé : le champ doit prendre le focus. Inspecteur, Accessibilité : le champ a un nom (« Adresse e-mail »).

## Correction

1. **Un `<label>` visible pour chaque champ**, relié par `for`/`id` (ou par imbrication).

   ```astro
   ---
   // src/components/ChampTexte.astro
   interface Props {
     id: string; nom: string; libelle: string; type?: string;
     autocomplete?: string; requis?: boolean; aide?: string; erreur?: string;
   }
   const { id, nom, libelle, type = 'text', autocomplete, requis = false, aide, erreur } = Astro.props;
   const decrit = [aide && `${id}-aide`, erreur && `${id}-erreur`].filter(Boolean).join(' ') || undefined;
   ---
   <div class="champ">
     <label for={id}>{libelle}{requis && <span aria-hidden="true"> *</span>}</label>
     {aide && <p id={`${id}-aide`} class="champ__aide">{aide}</p>}
     <input
       id={id} name={nom} type={type} autocomplete={autocomplete}
       required={requis} aria-invalid={erreur ? 'true' : undefined} aria-describedby={decrit}
     />
     {erreur && <p id={`${id}-erreur`} class="champ__erreur">{erreur}</p>}
   </div>
   ```
2. **Ne remplacez jamais le label par un `placeholder`** : il disparaît à la saisie et son contraste est souvent faible. Le `placeholder` peut donner un exemple (« nom@exemple.fr »), pas l'intitulé.
3. **Label masqué visuellement** si le design l'impose (champ de recherche avec bouton « Rechercher » à côté) : gardez le `<label class="sr-only">` (voir `a11y-noms-boutons-liens`) plutôt que de le supprimer. À défaut, `aria-label="Rechercher sur le site"`.
4. **`select`, `textarea`, cases à cocher, boutons radio** : même règle. Pour un groupe (civilité, choix multiples) : `<fieldset><legend>...</legend>`.
5. **Plusieurs labels sur un même champ** (`form-field-multiple-labels`) : supprimez le doublon (souvent un label caché ajouté par une bibliothèque ou un label visuel plus un `aria-label`).
6. **`autocomplete`** avec des valeurs standard, pour les champs sur soi-même :

   | Champ | `autocomplete` |
   |---|---|
   | Prénom / Nom | `given-name` / `family-name` |
   | E-mail | `email` |
   | Téléphone | `tel` |
   | Adresse, code postal, ville | `street-address`, `postal-code`, `address-level2` |
   | Organisation | `organization` |

   Une valeur inventée (`autocomplete="nope"`, `"off-xyz"`) déclenche l'échec de Lighthouse. Désactiver réellement : `autocomplete="off"`.
7. **Erreurs** : indiquer l'erreur dans le texte (pas seulement en rouge), la relier au champ (`aria-describedby`, `aria-invalid="true"`) et l'annoncer.

   ```html
   <div role="alert" id="resume-erreurs">2 champs sont à corriger : Adresse e-mail, Message.</div>
   ```

   Déplacez le focus sur le premier champ en erreur après envoi.
8. **Champ piège anti-spam (honeypot)** : masquez-le aux lecteurs d'écran et au clavier : `aria-hidden="true"`, `tabindex="-1"`, `autocomplete="off"`, et pas de libellé qui incite à le remplir.
9. Boutons d'envoi : texte explicite (« Envoyer ma demande »), voir `a11y-noms-boutons-liens`.

## Critères d'acceptation

- [ ] Chaque champ visible a un nom accessible (label relié) ; un clic sur le label active le champ.
- [ ] Lighthouse : « Les éléments de formulaire sont associés à des libellés » et « Les attributs `autocomplete` sont utilisés correctement » réussis.
- [ ] Les erreurs sont écrites, reliées au champ et annoncées ; le focus va au premier champ en erreur.
- [ ] Le formulaire s'utilise entièrement au clavier ; l'envoi fonctionne toujours.

## Vérification après correction

```bash
npx lighthouse https://exemple.fr/contact --only-categories=accessibility --quiet --output=json --output-path=/tmp/a11y.json --locale=fr
python3 -c "import json; a=json.load(open('/tmp/a11y.json'))['audits']; [print(k, a[k]['score']) for k in ('label','select-name','form-field-multiple-labels','autocomplete-valid') if k in a]"
```

## Pièges et retour arrière

- `id` dupliqués (un même composant utilisé deux fois sur la page) cassent le lien label/champ : générez des `id` uniques.
- `aria-label` sur un champ qui a déjà un `<label>` : le label visible est ignoré ; évitez le doublon.
- Retour arrière : retirer l'attribut ajouté ; sans effet sur la logique d'envoi.

## Pour aller plus loin

- W3C WAI, tutoriel « Étiquettes de formulaire ».
- WCAG 1.3.5 (identifier la finalité d'un champ) et 3.3.1 (identification des erreurs).
- MDN, attribut `autocomplete` : valeurs autorisées.
- RGAA, thématique Formulaires.
