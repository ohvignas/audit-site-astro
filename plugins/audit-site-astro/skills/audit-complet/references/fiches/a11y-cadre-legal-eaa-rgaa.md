---
id: a11y-cadre-legal-eaa-rgaa
titre: "Cadre légal de l'accessibilité (EAA, RGAA) et déclaration d'accessibilité"
domaine: Accessibilité
severite_type: basse
effort: L
declencheurs:
  - "manuel:cadre-legal-accessibilite"
sources:
  - https://eur-lex.europa.eu/eli/dir/2019/882/oj
  - https://accessibilite.numerique.gouv.fr/
  - https://accessibilite.numerique.gouv.fr/obligations/
  - https://accessibilite.numerique.gouv.fr/ressources/modele-de-declaration/
  - https://www.w3.org/TR/WCAG22/
---

# Cadre légal de l'accessibilité (EAA, RGAA) et déclaration d'accessibilité

> **En une phrase** : selon la nature de l'organisation et du service, le site peut devoir respecter un référentiel d'accessibilité (RGAA) et publier une déclaration d'accessibilité ; cette fiche décrit le contexte et le travail à prévoir, elle ne dit pas si votre structure est concernée.

## Pourquoi c'est important

L'accessibilité n'est pas seulement un choix éthique : c'est une obligation légale pour une partie des sites, avec un risque de sanction ou de contentieux, et un critère de sélection pour certains clients publics. Ce qui est sûr : **la directive européenne 2019/882 (European Accessibility Act, EAA) s'applique depuis le 28 juin 2025** à certains produits et services (notamment des services de commerce en ligne, de banque de détail, de transport de voyageurs, de communications électroniques, de livres numériques), transposée en droit français. Le secteur public et certaines grandes entreprises étaient déjà soumis à l'article 47 de la loi du 11 février 2005 et au RGAA. Les micro-entreprises qui fournissent des services sont exemptées par la directive. **Que votre structure soit soumise ou non dépend de sa taille, de son secteur et de la nature de ses services : faites-le confirmer par un juriste ou par le référent de votre organisation.** Ne jamais affirmer une obligation dans un rapport sans cette validation.

## Comment le constater soi-même

Points à vérifier (sans avoir à trancher juridiquement) :

```bash
curl -s https://exemple.fr/ | grep -oiE 'accessibilit[ée][^<]{0,60}' | head          # mention dans la page ?
for p in /accessibilite /declaration-accessibilite /mentions-legales; do printf '%s -> ' $p; curl -s -o /dev/null -w '%{http_code}\n' https://exemple.fr$p; done
```

- Existe-t-il une page « Accessibilité » liée depuis toutes les pages (pied de page) ?
- Indique-t-elle l'état de conformité (non conforme, partiellement conforme, totalement conforme), la date, la méthode d'évaluation, les contenus non accessibles, un moyen de contact et les voies de recours ?

## Correction

1. **Qualifier la situation** (à faire par la personne responsable, avec un juriste) : public/privé, taille de l'entreprise, nature du service (vente en ligne, réservation…), date de mise en service. Consigner la décision.
2. **Choisir le référentiel** : en France, le RGAA (Référentiel général d'amélioration de l'accessibilité) est la méthode d'évaluation de référence. La version 4.1.2 compte 106 critères regroupés en 13 thématiques et s'appuie sur WCAG 2.1 niveau AA ; la norme européenne EN 301 549 est le pivot de l'EAA. Les exigences de WCAG 2.2 AA (taille de cible, focus non masqué…) sont une bonne pratique à viser dès maintenant ; vérifiez sur le site officiel la version du RGAA en vigueur.
3. **Auditer** un échantillon de pages représentatif (accueil, contact, une page de contenu, un formulaire, le parcours de conversion, mentions légales, page d'accessibilité) : outils automatiques (Lighthouse, axe, pa11y) puis contrôles manuels. Les outils automatiques trouvent environ 30 à 40 % des problèmes ; le clavier et le lecteur d'écran sont indispensables.
4. **Publier une déclaration d'accessibilité** si elle est requise (ou par transparence) : page dédiée liée depuis chaque page (pied de page, libellé « Accessibilité : non conforme / partiellement conforme / totalement conforme »). Contenu type :
   - état de conformité et référentiel utilisé ;
   - résultats des tests (taux de critères respectés, échantillon, date) ;
   - contenus non accessibles et raisons (dérogations éventuelles) ;
   - établissement de la déclaration (date, agent d'évaluation, technologies utilisées) ;
   - retour d'information et contact (adresse ou formulaire accessible) ;
   - voies de recours (saisine du Défenseur des droits).

   Le service public fournit un générateur de déclaration : accessibilite.numerique.gouv.fr/ressources/modele-de-declaration.
5. **Planifier les corrections** : commencer par les fiches à fort impact (`a11y-noms-boutons-liens`, `a11y-images-alt`, `a11y-formulaires-labels`, `a11y-contraste-couleurs`, `a11y-focus-visible`, `a11y-clavier-menus-modales`), puis corriger dans les composants (un correctif répare toutes les pages).
6. **Prévenir la régression** : ajouter un test automatique (pa11y ou axe en intégration continue) et la revue « Tab + zoom 200 % » avant chaque mise en production.
7. **Mettre à jour** la déclaration au moins une fois par an et après tout changement important.

## Critères d'acceptation

- [ ] La qualification juridique (concerné ou non) est documentée et validée par une personne compétente.
- [ ] Un audit sur échantillon a été réalisé avec une méthode et une date.
- [ ] Une déclaration d'accessibilité est publiée et liée depuis toutes les pages si elle est requise.
- [ ] Un plan de correction daté existe, avec un responsable.
- [ ] Un contrôle automatique et une revue manuelle sont intégrés au processus de mise en production.

## Vérification après correction

```bash
curl -s -o /dev/null -w '%{http_code}\n' https://exemple.fr/accessibilite      # 200
curl -s https://exemple.fr/ | grep -oiE 'accessibilit[ée][^<]{0,60}'            # mention dans le pied de page
```

## Pièges et retour arrière

- Ne déclarez pas « totalement conforme » sans audit complet et méthodique : une déclaration inexacte est un risque en soi.
- Un score Lighthouse de 100 n'est pas une preuve de conformité (contrôle automatique partiel).
- Les textes, seuils et sanctions évoluent : consultez les sources officielles (site du service public dédié, Légifrance, EUR-Lex) avant toute affirmation.
- Retour arrière : sans objet (documentation) ; ne supprimez pas une déclaration publiée sans la remplacer.

## Pour aller plus loin

- EUR-Lex, directive (UE) 2019/882 : produits et services concernés, exemptions.
- Site officiel de l'accessibilité numérique (RGAA, obligations, générateur de déclaration).
- WCAG 2.2 : recommandation du W3C.
