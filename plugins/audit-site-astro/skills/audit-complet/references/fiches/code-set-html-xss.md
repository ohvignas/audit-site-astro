---
id: code-set-html-xss
titre: set:html / dangerouslySetInnerHTML sur du contenu non assaini (risque XSS)
domaine: Code
severite_type: moyenne
effort: S
declencheurs:
  - "code:usage\\(s\\) de set:html / dangerouslySetInnerHTML"
sources:
  - https://docs.astro.build/en/reference/directives-reference/
  - https://github.com/apostrophecms/sanitize-html
  - https://cheatsheetseries.owasp.org/cheatsheets/XSS_Prevention_Cheat_Sheet.html
---

# set:html / dangerouslySetInnerHTML sur du contenu non assaini (risque XSS)

> **En une phrase** : `set:html` injecte du HTML sans l'échapper ; si ce HTML vient d'un utilisateur, de Convex ou d'un CMS, un script malveillant peut s'exécuter chez les visiteurs (faille XSS).

## Pourquoi c'est important

La doc Astro le dit en toutes lettres : la valeur passée à `set:html` n'est pas échappée ; oublier de l'assainir ouvre la porte aux attaques XSS. Un script injecté peut voler une session, rediriger vers un site frauduleux ou modifier la page. Le risque dépend de l'origine du HTML :

- **Sûr** : HTML écrit par vous dans le dépôt, JSON-LD produit par `JSON.stringify` (voir plus bas), Markdown rendu par Astro (collections de contenu).
- **À assainir** : texte saisi par des utilisateurs (avis, commentaires, profils), champs riches stockés dans Convex ou un CMS, HTML récupéré d'une API externe.

## Comment le constater soi-même

```bash
grep -rnE "set:html|dangerouslySetInnerHTML" src
```

Pour chaque ligne, remonter à l'origine de la valeur : est-elle une chaîne fixe ou un `JSON.stringify(...)` (sûr), ou vient-elle de `Astro.props`, d'une requête Convex, d'un `fetch` (à assainir) ? Test de contrôle sur un environnement de préproduction : enregistrer `<img src=x onerror=alert(1)>` dans le champ concerné ; si une alerte apparaît, la faille est réelle.

## Correction

1. Classer chaque usage : sûr (ne rien changer) ou à assainir.
2. Pour du HTML riche venant de l'extérieur, assainir **côté serveur** avec une liste blanche stricte :
   ```bash
   npm install sanitize-html
   npm install --save-dev @types/sanitize-html
   ```
   ```astro
   ---
   // src/components/AvisRiche.astro
   import sanitizeHtml from 'sanitize-html';

   const { html } = Astro.props;
   const propre = sanitizeHtml(html, {
     allowedTags: ['p', 'br', 'strong', 'em', 'ul', 'ol', 'li', 'a', 'blockquote'],
     allowedAttributes: { a: ['href', 'title'] },
     allowedSchemes: ['http', 'https', 'mailto'],
   });
   ---
   <div set:html={propre} />
   ```
   Le composant assainit : la page ne fait jamais confiance à la donnée brute.
3. Si le contenu n'a pas besoin de mise en forme, ne pas utiliser `set:html` : `<p>{texte}</p>` échappe automatiquement (ou `set:text`).
4. Pour du contenu éditorial, préférer le Markdown rendu par Astro (collections de contenu) au HTML stocké.
5. **JSON-LD** : `JSON.stringify` dans un `<script type="application/ld+json">` est correct, mais échapper `<` évite qu'une valeur contenant `</script>` ferme la balise :
   ```astro
   ---
   const schema = { '@context': 'https://schema.org', '@type': 'Organization', name: 'Exemple', url: 'https://exemple.fr' };
   const json = JSON.stringify(schema).replace(/</g, '\\u003c');
   ---
   <script type="application/ld+json" set:html={json} />
   ```
6. En React (`dangerouslySetInnerHTML`), assainir de la même façon avant le rendu, ou passer par un composant `.astro` qui fournit le HTML déjà assaini.
7. Défense en profondeur : ajouter une Content-Security-Policy (fiche sécurité sur la CSP ; `security.csp` dans Astro 6+).

## Critères d'acceptation

- [ ] Chaque `set:html` restant est soit une chaîne maîtrisée, soit un JSON-LD `JSON.stringify` échappé, soit passé par `sanitizeHtml`
- [ ] Le test `<img src=x onerror=alert(1)>` en préproduction n'exécute rien
- [ ] Aucune régression : mise en forme autorisée (gras, listes, liens) toujours affichée

## Vérification après correction

```bash
grep -rnE "set:html|dangerouslySetInnerHTML" src
npx astro build
python3 scripts/astro_scan.py . --out /tmp/verif   # les usages sûrs restent listés : les justifier en revue
```

## Pièges et retour arrière

- Assainir **à l'affichage** (ou à l'enregistrement **et** à l'affichage) : ne jamais supposer que la base ne contient que du HTML propre.
- Une liste blanche trop large (`script`, `iframe`, attributs `on*`, `style`) annule l'effet ; la garder minimale. Les liens `javascript:` sont bloqués par `allowedSchemes`.
- Les regex maison (`replace(/<script>/g, '')`) sont contournables : utiliser une bibliothèque.
- Retour arrière : retirer l'appel à `sanitizeHtml` ne casse rien mais rétablit la faille ; préférer ajuster la liste blanche.

## Pour aller plus loin

- https://docs.astro.build/en/reference/directives-reference/ : `set:html` (non échappé) et `set:text`.
- https://github.com/apostrophecms/sanitize-html : options `allowedTags`, `allowedAttributes`, `allowedSchemes`.
- https://cheatsheetseries.owasp.org/cheatsheets/XSS_Prevention_Cheat_Sheet.html : bonnes pratiques contre le XSS.
