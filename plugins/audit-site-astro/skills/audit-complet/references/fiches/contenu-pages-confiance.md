---
id: contenu-pages-confiance
titre: Pages de confiance manquantes (à propos, contact, mentions légales, confidentialité)
domaine: Contenu
severite_type: haute
effort: M
declencheurs:
  - "geo:Page « (a propos|contact|mentions legales|confidentialite) » introuvable"
sources:
  - https://developers.google.com/search/docs/fundamentals/creating-helpful-content
  - https://entreprendre.service-public.gouv.fr/vosdroits/F31228
  - https://www.cnil.fr/fr/cookies-et-autres-traceurs
  - https://schema.org/AboutPage
---

# Pages de confiance manquantes (à propos, contact, mentions légales, confidentialité)

> **En une phrase** : le site ne dit pas clairement qui il est, comment le joindre et quelles règles il respecte, ce qui est une obligation légale en France et un signal de fiabilité pour Google et les visiteurs.

## Pourquoi c'est important

En France, tout site professionnel doit afficher ses mentions légales (loi pour la confiance dans l'économie numérique, LCEN). Service-public.fr indique que leur absence est punie jusqu'à un an d'emprisonnement et 75 000 euros d'amende (personne physique). La politique de confidentialité est exigée par le RGPD dès que le site collecte des données personnelles (formulaire de contact, inscription, newsletter, mesure d'audience, comptes). Côté référencement, Google évalue la fiabilité (le « T » de E-E-A-T) : savoir qui publie, pouvoir le contacter, voir des preuves. Pour un organisme de formation ou un prestataire de services, une page « à propos » réelle et une page équipe nommée pèsent dans la décision de s'inscrire ou d'appeler. L'outil cherche dans les URL du crawl un slug de type `a-propos`, `qui-sommes-nous`, `contact`, `mentions-legales`, `confidentialite` ou `privacy` ; s'il n'en trouve pas, la page peut exister sous un autre nom : vérifier avant de créer (faux positif possible).

## Comment le constater soi-même

```bash
for p in a-propos qui-sommes-nous contact mentions-legales politique-de-confidentialite confidentialite; do
  printf '%s : ' "$p"; curl -s -o /dev/null -w '%{http_code}\n' "https://SITE/$p/"
done
curl -s https://SITE/ | grep -oiE 'href="[^"]*(mentions|confidential|privacy|contact|propos)[^"]*"' | sort -u
ls src/pages | grep -iE "propos|contact|mentions|confidential"
```

Présent : 404 partout et aucun lien dans le pied de page. Corrigé : chaque page répond 200 et est liée depuis le pied de page de toutes les pages.

## Correction

1. **Ne rien inventer.** Toutes les données légales viennent du propriétaire (raison sociale, SIRET, capital, adresse, directeur de la publication, hébergeur). Si une information manque, la lister dans le rapport et laisser la page en brouillon, jamais de valeur fictive publiée.
2. **Mentions légales** (`src/pages/mentions-legales.astro`) : contenu attendu.
   - Éditeur : dénomination sociale (ou nom et prénom pour un entrepreneur individuel), forme juridique, capital social, adresse du siège, RCS et numéro, numéro de TVA intracommunautaire, téléphone, adresse e-mail.
   - Directeur de la publication (et responsable de la rédaction si différent).
   - Hébergeur : nom, adresse, téléphone.
   - Selon l'activité : autorité de tutelle, numéro de déclaration d'activité et certification (organisme de formation), médiateur de la consommation si vente aux particuliers, propriété intellectuelle.
3. **Politique de confidentialité** (`src/pages/politique-de-confidentialite.astro`) : responsable du traitement et contact, chaque finalité (formulaire, newsletter, mesure d'audience, comptes) avec sa base légale, données collectées, destinataires et sous-traitants (hébergeur, outil d'e-mail, outil d'analyse ; pour un site Astro avec Convex, citer Convex comme sous-traitant et vérifier la région de son déploiement), durée de conservation, droits (accès, rectification, effacement, opposition, limitation, portabilité), droit de réclamation auprès de la CNIL, gestion des cookies et traceurs (consentement pour les traceurs non essentiels). La page doit refléter ce que le site fait réellement : lister les scripts et formulaires trouvés dans le code.
4. **Page à propos** (`src/pages/a-propos.astro`) : qui, depuis quand, pour qui, méthode, chiffres vérifiables (nombre de stagiaires formés, années d'activité), certifications et labels avec numéros, équipe nommée avec photo et parcours, adresse et carte, liens vers les profils LinkedIn. C'est ici que se jouent l'expertise et l'expérience affichées.
5. **Contact** (`src/pages/contact.astro`) : adresse postale complète, téléphone cliquable (`<a href="tel:+33400000000">`), e-mail, horaires, formulaire. Nom, adresse et téléphone (NAP) identiques partout (pied de page, contact, données structurées).
6. **Si le site vend** : CGV (conditions générales de vente) liées depuis le pied de page et le tunnel de commande. **Si organisme de formation** : règlement intérieur, indicateurs de résultats et informations sur l'accessibilité aux personnes handicapées, comme la réglementation l'exige : à faire valider par le propriétaire.
7. **Relier depuis le pied de page** (layout commun) :

```astro
---
// src/components/Footer.astro
const liens = [
  { href: "/a-propos/", texte: "À propos" },
  { href: "/contact/", texte: "Contact" },
  { href: "/mentions-legales/", texte: "Mentions légales" },
  { href: "/politique-de-confidentialite/", texte: "Politique de confidentialité" },
];
---
<footer>
  <nav aria-label="Informations légales et contact">
    <ul>
      {liens.map((l) => <li><a href={l.href}>{l.texte}</a></li>)}
    </ul>
  </nav>
</footer>
```

8. **Sources des textes** : pages `.astro` statiques, ou entrées d'une collection `pages` (`src/content/pages/*.md`) affichées par une route commune, ou documents Convex (table `pages`, champs `slug`, `titre`, `contenu`). Dans tous les cas, `noindex` est inutile ici : ces pages doivent rester indexables, y compris les mentions légales.
9. **Données structurées** (facultatif) : `AboutPage` et `ContactPage` (schema.org) sur les pages correspondantes, en cohérence avec l'entité `Organization` du site (voir la fiche GEO sur l'entité Organization).

## Critères d'acceptation

- [ ] Les quatre pages (à propos, contact, mentions légales, confidentialité) répondent 200, sont indexables et sont liées depuis le pied de page de chaque page.
- [ ] Les mentions légales contiennent éditeur, directeur de la publication et hébergeur, avec des données réelles validées par le propriétaire.
- [ ] La politique de confidentialité correspond aux traitements réels du site (formulaires, analytics, Convex, e-mailing).
- [ ] NAP identique sur toutes les pages.
- [ ] Aucune donnée inventée ; build OK.

## Vérification après correction

```bash
for p in a-propos contact mentions-legales politique-de-confidentialite; do curl -s -o /dev/null -w "$p %{http_code}\n" "https://SITE/$p/"; done
python3 scripts/geo_check.py https://SITE/ --out /tmp/verif/geo --crawl /tmp/verif/crawl/pages.json
grep -i "introuvable" /tmp/verif/geo/geo-summary.md      # ne doit rien renvoyer
```

## Pièges et retour arrière

- Ce contenu engage juridiquement : c'est un texte à faire relire par le propriétaire (ou un juriste).
- Un slug non standard (`/qui-sommes-nous-2/`) échappe à la détection de l'outil ; préférer des URL usuelles.
- Ne pas copier les mentions légales d'un autre site.
- Retour arrière : `git revert` ; les pages légales existantes ne doivent pas être supprimées.

## Pour aller plus loin

- https://entreprendre.service-public.gouv.fr/vosdroits/F31228 : mentions obligatoires d'un site professionnel.
- https://www.cnil.fr/fr/cookies-et-autres-traceurs : règles de la CNIL sur les cookies et traceurs (consentement).
- https://developers.google.com/search/docs/fundamentals/creating-helpful-content : qui, comment, pourquoi ; fiabilité.
- https://schema.org/AboutPage : type de page à propos.
