---
id: a11y-contraste-couleurs
titre: "Contrastes de couleurs insuffisants (texte et éléments d'interface)"
domaine: Accessibilité
severite_type: haute
effort: M
declencheurs:
  - "lighthouse:color-contrast|suffisamment contrastées"
sources:
  - https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html
  - https://www.w3.org/WAI/WCAG22/Understanding/non-text-contrast.html
  - https://dequeuniversity.com/rules/axe/4.10/color-contrast
  - https://accessibilite.numerique.gouv.fr/methode/criteres-et-tests/#3.2
---

# Contrastes de couleurs insuffisants (texte et éléments d'interface)

> **En une phrase** : des textes sont trop pâles sur leur fond (gris clair, texte sur image, couleur de marque), ce qui les rend illisibles pour les personnes malvoyantes et pour tout le monde en plein soleil.

## Pourquoi c'est important

Environ un homme sur douze et une femme sur deux cents ont une déficience de perception des couleurs, et la baisse de la vue avec l'âge touche une grande partie des visiteurs. WCAG 1.4.3 (niveau AA, repris par le RGAA, critère 3.2) exige un rapport de contraste d'au moins **4,5:1** pour le texte courant et **3:1** pour le grand texte (à partir de 24 px, ou 18,66 px en gras). WCAG 1.4.11 exige **3:1** pour les éléments d'interface (bordure d'un champ, icône seule, état d'un bouton). Ce défaut est aussi le plus fréquent sur les sites : un seul jeton de couleur mal choisi (le gris des textes secondaires) provoque des dizaines d'occurrences.

## Comment le constater soi-même

```bash
# Lighthouse : liste des éléments en échec avec leur rapport de contraste
npx lighthouse https://exemple.fr/ --only-categories=accessibility --output=json --locale=fr --quiet \
  | python3 -c "import json,sys; a=json.load(sys.stdin)['audits']['color-contrast']; print(a['score'], a['displayValue'] if 'displayValue' in a else ''); [print(i['node']['snippet'][:100], '|', i['node'].get('explanation','')[:160]) for i in a['details']['items'][:15]]"
```

Dans le navigateur : outils de développement, inspecteur, clic sur la pastille de couleur (le rapport et la couleur suggérée s'affichent) ; ou l'extension axe DevTools. Mesure manuelle : WebAIM Contrast Checker avec les deux codes couleur.

Vérifier en calculant (Python, sans dépendance) :

```python
def lum(h):
    r, g, b = (int(h[i:i+2], 16) / 255 for i in (1, 3, 5))
    f = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)

def contraste(a, b):
    la, lb = sorted((lum(a), lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)

print(round(contraste('#767676', '#ffffff'), 2))   # 4.54 : limite basse acceptable (texte courant)
print(round(contraste('#9ca3af', '#ffffff'), 2))   # 2.54 : insuffisant
```

## Correction

1. **Trouver la couleur d'origine, pas l'élément** : le rapport de Lighthouse cite des sélecteurs ; remontez à la variable de design (variable CSS, thème Tailwind) utilisée. Corriger la variable règle toutes les pages d'un coup.
2. **Assombrir le texte (ou éclaircir le fond)** jusqu'à 4,5:1 minimum pour le texte courant. Règles pratiques sur fond blanc : texte courant `#595959` (7:1) ou au plus clair `#767676` (4,54:1) ; texte secondaire jamais plus clair que `#6b7280` (4,83:1). Le gris `#9ca3af` (2,54:1) est à proscrire pour du texte.

   ```css
   /* src/styles/global.css : jetons de couleur vérifiés sur fond blanc */
   :root {
     --couleur-texte: #1f2937;         /* 14,7:1 */
     --couleur-texte-secondaire: #595959; /* 7:1 */
     --couleur-lien: #1d4ed8;          /* 6,7:1 */
     --couleur-bordure-champ: #6b7280; /* 4,8:1 : bordures d'inputs (3:1 requis) */
   }
   ```
3. **Couleur de marque** (bouton, lien) trop claire : créez une variante foncée pour le texte et gardez la couleur d'origine pour les aplats décoratifs. Sur un bouton plein, calculez le contraste texte/fond du bouton (texte blanc sur fond orange clair échoue souvent).
4. **Texte sur image** (hero) : ajoutez un voile ou un dégradé derrière le texte, ou déplacez le texte sur un aplat.

   ```css
   .hero__texte { background: rgb(0 0 0 / 0.55); color: #fff; padding: 1rem; }
   ```
5. **États** : placeholder (texte indicatif d'un champ) doit avoir 4,5:1 lui aussi ; lien survolé/focalisé ; texte désactivé (exempté par WCAG mais évitez l'illisible) ; mode sombre (`prefers-color-scheme: dark`) à recalculer séparément.
6. **Éléments d'interface** : bordures de champs, icônes porteuses de sens, indicateurs (pastille active) ≥ 3:1 contre le fond adjacent.
7. Évitez de « baisser l'opacité » (`opacity: .6`, `text-gray-400`, `text-white/60`) pour faire du texte secondaire : le contraste chute sans que le code couleur le montre.

## Critères d'acceptation

- [ ] L'audit Lighthouse « Les couleurs d'arrière-plan et de premier plan sont suffisamment contrastées » est réussi sur les gabarits testés (accueil, article, catalogue, contact).
- [ ] Texte courant ≥ 4,5:1, grand texte ≥ 3:1, éléments d'interface ≥ 3:1, en clair et en sombre.
- [ ] La charte graphique reste cohérente (validation visuelle de la couleur modifiée).
- [ ] Aucune régression de mise en page.

## Vérification après correction

```bash
npx lighthouse https://exemple.fr/ --only-categories=accessibility --quiet --output=json --output-path=/tmp/a11y.json --locale=fr
python3 -c "import json; a=json.load(open('/tmp/a11y.json'))['audits']['color-contrast']; print('score', a['score'])"
```

Relancer aussi l'outil : `bash scripts/lighthouse_run.sh /tmp/verif-perf --file urls.txt` et lire `echecs_autres_categories.accessibility`.

## Pièges et retour arrière

- Lighthouse ne voit pas les textes sur image ni les états `:hover` / `:focus` : vérifiez-les à l'œil et avec un contrôleur de contraste.
- Un fond en dégradé ou une image a plusieurs valeurs : testez le pire point derrière le texte.
- Retour arrière : revenir à l'ancienne valeur de la variable (Git) ; ne pas refuser la correction pour des raisons d'esthétique sans proposer une alternative conforme.

## Pour aller plus loin

- WCAG 2.2, contraste minimum (1.4.3) : seuils et exceptions.
- WCAG 2.2, contraste des éléments non textuels (1.4.11).
- Lighthouse, audit `color-contrast` : fonctionnement.
- RGAA, thématique Couleurs (critères 3.1 à 3.3).
