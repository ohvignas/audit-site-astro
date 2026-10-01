---
id: contenu-demo-residuel
titre: "Contenu de démonstration resté en ligne (lorem ipsum, « à remplacer », gabarit de démarrage)"
domaine: Contenu
severite_type: moyenne
effort: S
declencheurs:
  - "crawl:contenu_demo"
sources:
  - https://developers.google.com/search/docs/fundamentals/creating-helpful-content
  - https://developers.google.com/search/docs/appearance/snippet
---

# Contenu de démonstration resté en ligne

> **En une phrase** : un texte d'exemple du thème (lorem ipsum, « à remplacer par la vôtre ») est publié, souvent dans la meta description reprise par Google et les assistants IA.

## Pourquoi c'est important

Google affiche la meta description dans ses résultats et les IA la citent : un texte de démonstration y donne une image d'abandon et fait perdre des clics. Google classe le texte de remplissage parmi les contenus sans valeur. Sur beta.illith.com, la page `/contact` annonçait « Page de démonstration livrée avec AstroTan — à remplacer par la vôtre ».

## Comment le constater soi-même

```bash
python3 -c "import json;d=json.load(open('data/crawl/issues.json'));[print(e['signature'], e['exemples_pages']) for e in d.get('contenu_demo',{}).get('examples',[])]"
grep -rniE "lorem ipsum|à remplacer par|page de démonstration|Welcome to Astro" src/
```

## Correction

1. Chercher la phrase signalée dans le code (`grep -rn` ci-dessus) : souvent une valeur par défaut d'une prop `description` dans `src/layouts/*.astro` ou un fichier de données du thème.
2. Remplacer le texte par le vrai contenu ; pour une description par défaut, préférer une description propre à chaque page :
```astro
---
const { title, description } = Astro.props; // plus de valeur par défaut « à remplacer »
---
<meta name="description" content={description} />
```
3. Supprimer les pages d'exemple du thème qui ne servent pas (`src/pages/demo*.astro`, articles d'exemple des collections).

## Critères d'acceptation

- [ ] `contenu_demo` absent de `data/crawl/issues.json`
- [ ] Chaque page indexable a une meta description propre (aucun `desc_missing` ni `desc_dup` nouveau)
- [ ] Aucune régression : build OK, pages clés en 200

## Vérification après correction

```bash
python3 scripts/crawl_site.py https://SITE/ --out /tmp/verif/crawl
python3 -c "import json;print(json.load(open('/tmp/verif/crawl/issues.json')).get('contenu_demo',{}).get('count',0))"   # 0
```

## Pièges et retour arrière

- Un article qui parle de « lorem ipsum » est un faux positif : vérifier l'extrait cité avant de corriger.
- Une page qui présente un thème (« la page de démonstration du thème X »), un article sur le « contenu factice » ou le « texte de remplissage », ou un extrait de code rendu sans `<pre>` ni `<code>` peuvent être signalés à tort : seule une phrase comme « à remplacer par la vôtre » est certaine.
- Retirer une valeur par défaut peut laisser des pages sans description : relancer le crawl et traiter `desc_missing`.
- Retour arrière : `git revert` du commit de contenu.
