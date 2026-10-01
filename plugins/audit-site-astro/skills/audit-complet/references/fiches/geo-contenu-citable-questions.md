---
id: geo-contenu-citable-questions
titre: Peu de titres en questions et de réponses directes (contenu peu « citable »)
domaine: GEO / IA
severite_type: moyenne
effort: M
declencheurs:
  - "geo:Peu de titres formulés en questions"
sources:
  - https://developers.google.com/search/docs/fundamentals/creating-helpful-content
  - https://developers.google.com/search/docs/appearance/ai-features
  - https://developers.google.com/search/docs/appearance/structured-data/faqpage
  - https://docs.astro.build/en/basics/astro-components/
---

# Peu de titres en questions et de réponses directes

> **En une phrase** : les pages analysées contiennent en moyenne moins d'un titre H2/H3 formulé en question ; leur contenu répond peu explicitement aux questions que les utilisateurs posent aux assistants IA, ce qui le rend moins facile à extraire et à citer.

## Pourquoi c'est important

Un assistant IA répond à une question en prélevant des passages qui la traitent directement. Un titre qui reprend la question, suivi d'une réponse courte et autonome, puis du détail, est facile à repérer et à citer. C'est un **format**, pas une astuce : sans contenu utile et précis dessous, le titre ne sert à rien. Ce point est un indice, pas une garantie : aucune étude publique n'établit de gain de citation chiffré, et Google indique qu'il n'y a pas d'optimisation spéciale pour ses fonctions IA au-delà d'un contenu utile, indexable et éligible aux extraits. L'outil compte les titres H2/H3 qui se terminent par « ? » ou commencent par un mot interrogatif (comment, pourquoi, quel, combien, est-ce…) sur les pages échantillonnées et signale quand le total est inférieur au nombre de pages. À appliquer **là où c'est naturel** (services, tarifs, méthodes, guides), pas sur toutes les pages (mentions légales, contact).

## Comment le constater soi-même

```bash
# Titres H2/H3 d'une page et repérage des questions
curl -s https://SITE/PAGE | python3 -c "
import sys,re
h=sys.stdin.read()
for lvl,t in re.findall(r'<h([23])[^>]*>(.*?)</h\1>',h,re.S|re.I):
    t=re.sub(r'<[^>]+>','',t).strip()
    print('H'+lvl, '?' if t.endswith('?') else ' ', t[:90])
"
# Le texte est-il dans le HTML initial (sans JavaScript) ?
curl -s https://SITE/PAGE | sed -e 's/<script.*<\/script>//g' -e 's/<[^>]*>//g' | wc -w
```

Colonne « Q° » de `geo-summary.md` : `questions / titres` par page. Problème présent : `0/8`, `1/12` sur la plupart des pages clés. Le nombre de mots sans JS très faible sur une page pourtant riche indique un contenu rendu côté navigateur (îlot `client:only`), invisible pour beaucoup de robots.

## Correction

1. Créer une branche Git. Choisir les 5 à 10 pages qui doivent être citées (accueil, offres, tarifs, pages métier, guides).
2. Pour chacune, lister 3 à 6 **vraies questions** de vos clients (mails, appels, Search Console, « Autres questions posées »), avec leur formulation réelle.
3. Réécrire les titres concernés en questions et placer juste dessous une **réponse directe de 40 à 60 mots environ** (pratique éditoriale courante, sans valeur normative), puis le détail, des listes et des tableaux (durées, prix, prérequis, comparatifs).

```md
## Combien coûte un site vitrine de 5 pages ?

Un site vitrine de 5 pages coûte entre 2 500 € et 5 000 € HT chez Exemple SAS, selon le nombre de
contenus fournis et les intégrations. Ce tarif comprend la conception, l'intégration, l'hébergement
la première année et 2 rounds de retouches. Les options sont détaillées ci-dessous (dernière mise à jour : septembre 2026).

### Ce qui fait varier le prix
- Nombre de pages et de gabarits
- Rédaction des textes fournie ou non
```

   Chiffres réels, sourcés et datés uniquement (une IA cite volontiers des données précises qu'elle ne trouve pas ailleurs).
4. Ajouter un bloc **FAQ visible** sur les pages business. Composant Astro alimenté par une liste de données, qui produit aussi le JSON-LD `FAQPage` à partir de la **même** source (pas de divergence texte/balisage) :

```astro
---
// src/components/Faq.astro
import JsonLd from './JsonLd.astro'; // voir geo-entite-organization-jsonld
interface Props { items: { question: string; reponse: string }[] }
const { items } = Astro.props;
const schema = {
  '@context': 'https://schema.org',
  '@type': 'FAQPage',
  mainEntity: items.map((i) => ({
    '@type': 'Question',
    name: i.question,
    acceptedAnswer: { '@type': 'Answer', text: i.reponse },
  })),
};
---
<section>
  <h2>Questions fréquentes</h2>
  {items.map((i) => (
    <details>
      <summary><h3>{i.question}</h3></summary>
      <p>{i.reponse}</p>
    </details>
  ))}
</section>
<JsonLd data={schema} />
```

   Le texte des réponses reste dans le HTML servi (ne pas le charger en JS). Le JSON-LD FAQPage n'apporte plus de résultat enrichi dans Google pour la plupart des sites : il aide seulement à structurer l'information. Ne pas le vendre comme un gain de visibilité.
5. Vérifier que le contenu principal est dans le HTML initial : si une section est dans un composant React/Vue/Svelte, éviter `client:only` pour le texte et rendre le composant au build (`client:load`/`client:visible` ou sans directive).
6. Ne pas transformer artificiellement tous les titres en questions : garder des titres informatifs quand la question serait forcée.

## Critères d'acceptation

- [ ] Les pages stratégiques comptent chacune au moins 2 à 3 titres H2/H3 formulés en questions naturelles
- [ ] Chaque question est suivie d'une réponse directe de quelques phrases, avant le détail
- [ ] Le texte est présent dans le HTML servi (`curl` montre les réponses)
- [ ] Les chiffres cités sont exacts, datés, et existent sur le site
- [ ] Aucune régression : hiérarchie H1 > H2 > H3 respectée, build OK

## Vérification après correction

```bash
curl -s https://SITE/PAGE | grep -ciE '<h[23][^>]*>[^<]*\?'
python3 scripts/geo_check.py https://SITE/ --out /tmp/verif/geo --sample 12
grep -iE 'titres formulés' /tmp/verif/geo/geo-summary.md
```

Puis un test manuel (voir la fiche `geo-mesure-visibilite-ia`) : les questions ciblées mènent-elles à une citation du site ?

## Pièges et retour arrière

- Un `<h3>` dans un `<summary>` est valide en HTML5 mais peut être mal rendu par certains styles ; adapter le CSS ou utiliser un simple `<h3>` suivi d'un `<p>`.
- Ne pas dupliquer la même FAQ sur toutes les pages (contenu répétitif).
- Retour arrière : Git ; supprimer le composant `<Faq>` des pages concernées.

## Pour aller plus loin

- https://developers.google.com/search/docs/fundamentals/creating-helpful-content : contenu utile, écrit pour les personnes.
- https://developers.google.com/search/docs/appearance/ai-features : conditions pour apparaître dans les fonctions IA de Google.
- https://developers.google.com/search/docs/appearance/structured-data/faqpage : statut du résultat enrichi FAQ.
- https://docs.astro.build/en/basics/astro-components/ : composants Astro.
