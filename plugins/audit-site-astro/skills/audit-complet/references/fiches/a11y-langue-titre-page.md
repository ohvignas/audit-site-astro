---
id: a11y-langue-titre-page
titre: "Langue de la page et titre du document absents ou invalides"
domaine: Accessibilité
severite_type: haute
effort: S
declencheurs:
  - "lighthouse:html-has-lang|html-lang-valid|valid-lang|html-xml-lang-mismatch|document-title"
  - "lighthouse:n'a pas d'attribut `\\[lang\\]`|La valeur de l'attribut `\\[lang\\]` de l'élément `<html>` n'est pas valide|La valeur des attributs `\\[lang\\]` n'est pas valide|attribut `\\[xml:lang\\]`|ne contient pas d'élément `<title>`"
sources:
  - https://www.w3.org/WAI/WCAG22/Understanding/language-of-page.html
  - https://www.w3.org/WAI/WCAG22/Understanding/language-of-parts.html
  - https://www.w3.org/WAI/WCAG22/Understanding/page-titled.html
  - https://docs.astro.build/en/guides/internationalization/
  - https://accessibilite.numerique.gouv.fr/methode/criteres-et-tests/#8.3
---

# Langue de la page et titre du document absents ou invalides

> **En une phrase** : la page n'indique pas sa langue (ou l'indique mal) ou n'a pas de `<title>`, si bien que le lecteur d'écran prononce le français avec l'accent anglais et que l'onglet n'a pas de nom.

## Pourquoi c'est important

Sans `lang="fr"`, un lecteur d'écran choisit la langue de l'utilisateur ou de l'appareil : un texte français lu avec une voix anglaise est incompréhensible. Le navigateur utilise aussi `lang` pour la césure, les guillemets, les correcteurs et la traduction automatique. Le `<title>` est la première chose lue à l'ouverture de la page et le nom de l'onglet, de l'historique et des favoris. WCAG 3.1.1 (langue de la page, niveau A), 3.1.2 (langue d'un passage, AA), 2.4.2 (titre de page, A) ; RGAA critères 8.3, 8.4, 8.5, 8.7. La langue et le titre servent aussi au référencement (voir la fiche SEO `seo-base-html-lang-viewport` pour l'absence de `lang` mesurée par le crawl).

## Comment le constater soi-même

```bash
curl -s https://exemple.fr/ | grep -oE '<html[^>]*>' ; curl -s https://exemple.fr/ | grep -oE '<title>[^<]*</title>'
```

Attendu : `<html lang="fr">` (ou `fr-FR`) et un `<title>` non vide et propre à la page. Problème : `<html>` seul, `lang=""`, code invalide (`lang="francais"`, `lang="fr_FR"` avec un souligné), plusieurs `<title>`, absence de `<title>`.

## Correction

1. **Déclarer la langue dans la mise en page commune** (un seul endroit).

   ```astro
   ---
   // src/layouts/Base.astro
   interface Props { titre: string; description?: string }
   const { titre, description } = Astro.props;
   const langue = Astro.currentLocale ?? 'fr'; // avec la config i18n d'Astro ; sinon 'fr' en dur
   ---
   <!doctype html>
   <html lang={langue}>
     <head>
       <meta charset="utf-8" />
       <meta name="viewport" content="width=device-width, initial-scale=1" />
       <title>{titre}</title>
       {description && <meta name="description" content={description} />}
     </head>
     <body><slot /></body>
   </html>
   ```

   Astro expose `Astro.currentLocale` quand `i18n` est configuré dans `astro.config.mjs` ; sinon écrivez `lang="fr"`.
2. **Code de langue valide** : `fr`, `fr-FR`, `en`, `en-GB` (tiret, pas de souligné). Pas de nom de langue en clair.
3. **Passages dans une autre langue** (citation anglaise, nom de produit, formation en anglais) : `<span lang="en">on-page SEO</span>` ; pour un bloc, `<blockquote lang="en">`. Un code invalide sur ces attributs déclenche `valid-lang`.
4. **`xml:lang`** : inutile en HTML5 ; si présent, il doit avoir la même langue que `lang` (ou supprimez-le).
5. **Titre de page** : un `<title>` unique, dans le `<head>`, qui décrit **cette** page (« Formation SEO à Lyon | Exemple »). Le titre du site en dernier, moins de 60 caractères environ. Chaque page transmet son propre `titre` à la mise en page (pas de titre statique).
6. **Pages générées par le CMS** : vérifiez le gabarit d'article et les pages d'erreur (404), qui oublient souvent le `<title>`.
7. **Astro avec `<ClientRouter />`** : le titre est mis à jour à chaque navigation ; ne le remplacez pas côté client par du JavaScript maison.

## Critères d'acceptation

- [ ] Toutes les pages ont `<html lang="…">` avec un code valide qui correspond à la langue du contenu.
- [ ] Toutes les pages ont exactement un `<title>` non vide, distinct d'une page à l'autre.
- [ ] Les passages en langue étrangère portent un `lang` valide.
- [ ] Lighthouse : `html-has-lang`, `html-lang-valid`, `valid-lang`, `document-title` réussis.

## Vérification après correction

```bash
for u in / /contact /404-inexistante; do echo "$u"; curl -s "https://exemple.fr$u" | grep -oE '<html[^>]*>|<title>[^<]*</title>'; done
python3 scripts/crawl_site.py https://exemple.fr/ --out /tmp/verif-crawl
```

## Pièges et retour arrière

- Pages multilingues : `lang` doit changer avec la page (`/en/...` en `en`), sinon la voix lit l'anglais en français.
- `lang` sur `<html>` ne corrige pas un bloc dans une autre langue : balisez-le.
- Retour arrière : remettre l'attribut précédent ; aucun effet sur les données.

## Pour aller plus loin

- WCAG 3.1.1, 3.1.2 et 2.4.2.
- Astro, internationalisation : `Astro.currentLocale`.
- RGAA, thématique Éléments obligatoires (critères 8.3 à 8.7).
