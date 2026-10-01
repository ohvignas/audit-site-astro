---
id: a11y-liens-couleur-seule
titre: "Liens dans les textes reconnaissables par leur seule couleur"
domaine: Accessibilité
severite_type: moyenne
effort: S
declencheurs:
  - "lighthouse:link-in-text-block|identifiables grâce à leur couleur"
sources:
  - https://www.w3.org/WAI/WCAG22/Understanding/use-of-color.html
  - https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html
  - https://dequeuniversity.com/rules/axe/4.10/link-in-text-block
  - https://accessibilite.numerique.gouv.fr/methode/criteres-et-tests/#10.6
---

# Liens dans les textes reconnaissables par leur seule couleur

> **En une phrase** : dans les paragraphes, les liens ne se distinguent du texte que par leur couleur (pas de soulignement), donc une personne daltonienne ou malvoyante ne les repère pas.

## Pourquoi c'est important

Environ 8 % des hommes ont un daltonisme et beaucoup d'utilisateurs ont un écran mal réglé ou en plein soleil. Si le lien bleu et le texte gris ont des teintes proches, le lien devient invisible : pas de clic, pas de conversion, ni de navigation vers vos pages clés. WCAG 1.4.1 (Utilisation de la couleur, niveau A) impose qu'une information ne repose pas sur la seule couleur. RGAA critère 10.6 (lien identifiable). Le soulignement est la solution universelle et la plus économique.

## Comment le constater soi-même

```bash
grep -rnE "text-decoration:[[:space:]]*none|no-underline|\[&_a\]:no-underline" src | head -20     # soulignements retirés
npx lighthouse https://exemple.fr/ --only-categories=accessibility --quiet --output=json --output-path=/tmp/a11y.json --locale=fr \
 && python3 -c "import json; a=json.load(open('/tmp/a11y.json'))['audits']['link-in-text-block']; [print(i['node']['snippet'][:90]) for i in a.get('details',{}).get('items',[])[:10]]"
```

Test à l'œil : passez la page en niveaux de gris (outils de développement, Rendu, « Emuler une déficience visuelle » : achromatopsie). Les liens du texte doivent rester repérables.

## Correction

1. **Souligner les liens à l'intérieur du texte** (paragraphes, listes, articles, mentions). C'est la correction la plus sûre.

   ```css
   /* src/styles/global.css */
   .contenu a,
   p a, li a, td a {
     text-decoration: underline;
     text-decoration-thickness: 0.08em;
     text-underline-offset: 0.18em;
   }
   .contenu a:hover { text-decoration-thickness: 0.14em; }
   ```

   Avec Tailwind : `underline underline-offset-2` sur les liens du texte, ou le plugin Typography (`prose`) qui les souligne par défaut. Vérifiez qu'aucune classe `no-underline` ne s'applique.
2. **Si le design refuse le soulignement**, satisfaites les deux conditions de WCAG : (a) la couleur du lien a un contraste d'au moins **3:1** avec le texte environnant, et (b) un indice non coloré (soulignement, gras, bordure) apparaît au survol **et** au focus.

   ```css
   .contenu a { color: #1d4ed8; }          /* texte environnant : #1f2937 */
   .contenu a:hover, .contenu a:focus-visible { text-decoration: underline; }
   ```

   Vérifiez les deux rapports (lien/texte 3:1 ; lien/fond 4,5:1), voir `a11y-contraste-couleurs`.
3. **Navigation et boutons** (menus, cartes) sont hors sujet : le critère vise les liens noyés dans du texte. Un menu se repère par sa position et sa forme.
4. **Liens dans les composants de contenu** (rich text venant du CMS ou de Markdown) : appliquez la règle CSS au conteneur du contenu, pas lien par lien.

## Critères d'acceptation

- [ ] Lighthouse : « Les liens sont identifiables sans se baser sur la couleur » réussi.
- [ ] Chaque lien inclus dans un texte est souligné (ou respecte les conditions 3:1 + indice au survol/focus).
- [ ] Rendu toujours cohérent avec la charte (validation visuelle).

## Vérification après correction

```bash
python3 -c "import json; print(json.load(open('/tmp/a11y.json'))['audits']['link-in-text-block']['score'])"
```

Relancer Lighthouse (commande ci-dessus) avant de lire le score.

## Pièges et retour arrière

- `text-decoration: none` posé globalement sur `a` puis réactivé au cas par cas est source d'oublis : faites l'inverse (soulignement par défaut dans le contenu, retrait sur les composants de navigation).
- Ne retirez pas le soulignement au `:hover` seulement : il doit exister au repos.
- Retour arrière : supprimer les règles ajoutées.

## Pour aller plus loin

- WCAG 1.4.1, utilisation de la couleur.
- Lighthouse, audit `link-in-text-block`.
- RGAA critère 10.6.
