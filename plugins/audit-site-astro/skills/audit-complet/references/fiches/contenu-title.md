---
id: contenu-title
titre: Balise <title> absente, trop courte ou trop longue
domaine: Contenu
severite_type: haute
effort: S
declencheurs:
  - "crawl:title_missing"
  - "crawl:title_short"
  - "crawl:title_long"
  - "code:Layout .* : balises absentes du <head> : .*\\btitle\\b"
  - "lighthouse:document-title|n'a pas d'élément .?<title>"
sources:
  - https://developers.google.com/search/docs/appearance/title-link
  - https://docs.astro.build/en/basics/layouts/
  - https://docs.astro.build/en/guides/content-collections/
---

# Balise <title> absente, trop courte ou trop longue

> **En une phrase** : le titre de la page est vide, générique (« Accueil ») ou tronqué, donc Google le réécrit ou l'affiche mal et le clic est perdu.

## Pourquoi c'est important

Le `<title>` est le texte cliquable du résultat Google et le nom de l'onglet, du favori et du partage. Sans `<title>`, ou avec un titre vide ou trop court (« Accueil », « Formation »), Google invente un titre à partir du H1 ou des liens entrants, rarement celui que vous voulez. Google ne fixe aucune limite de caractères : il tronque « pour tenir dans la largeur de l'appareil », soit environ 55 à 65 caractères. Les seuils de l'outil (moins de 25 caractères = trop court, plus de 65 = trop long, marque comprise) sont des repères pratiques, pas des règles Google. Un `<title>` manquant sur une page indexable est le défaut de contenu le plus coûteux à corriger et le plus rapide à rentabiliser.

## Comment le constater soi-même

```bash
# titre d'une page
curl -s https://SITE/formations/excel/ | grep -o '<title>[^<]*</title>'
# longueur en caractères
curl -s https://SITE/formations/excel/ | grep -o '<title>[^<]*</title>' | sed 's/<[^>]*>//g' | awk '{ print length($0) " : " $0 }'
# dans le code source
grep -rn "<title" src/layouts src/components src/pages | head
```

Problème présent : aucune ligne, `<title></title>`, ou une longueur < 25 ou > 65. Corrigé : un titre unique de 30 à 60 caractères par page.

## Correction

1. **Trouver d'où vient le titre.** Dans un projet Astro, il est presque toujours écrit dans le layout (`src/layouts/BaseLayout.astro` ou équivalent, celui qui contient `<head>`), alimenté par une prop `title` que chaque page transmet. La source du texte est ensuite : (a) la page `.astro` qui appelle le layout, (b) le frontmatter d'un fichier de collection (`src/content/<collection>/*.md`), (c) un document Convex (champ `seoTitle` ou `titre`). Ne jamais corriger 40 pages à la main si le défaut est dans le layout.
2. **Rendre la prop obligatoire dans le layout** pour qu'une page sans titre casse le build au lieu de sortir sans titre :

```astro
---
// src/layouts/BaseLayout.astro
interface Props {
  title: string;        // obligatoire : TypeScript et `astro check` signalent l'oubli
  description: string;
  isHome?: boolean;
}
const { title, description, isHome = false } = Astro.props;
const SITE_NAME = "Exemple";
// Accueil : titre libre. Autres pages : « sujet | marque ». Éviter de répéter la marque.
const fullTitle = isHome || title.includes(SITE_NAME) ? title : `${title} | ${SITE_NAME}`;
---
<html lang="fr">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>{fullTitle}</title>
    <meta name="description" content={description} />
  </head>
  <body><slot /></body>
</html>
```

3. **Écrire le titre.** Règles : 30 à 60 caractères, marque comprise ; le sujet précis (formation, service, ville) en premier, la marque à la fin ; une seule promesse ; jamais de mots-clés empilés ni de MAJUSCULES. Ne jamais inventer un fait (durée, prix, certification, financement) : le reprendre du contenu de la page ou demander au propriétaire du site.

| Type de page | Mauvais | Bon (longueur) |
|---|---|---|
| Formation | `Formation` / `Accueil` | `Excel avancé : formation de 3 jours, éligible CPF \| Exemple` (59) |
| Formation par ville | `Formation développeur` | `Formation développeur web à Lyon, éligible CPF \| Exemple` (56) |
| Service | `Services` | `Création de site vitrine sur mesure à Nantes \| Exemple` (54) |
| Article | `Blog - article 3` | `Devenir développeur web : parcours et formations \| Exemple` (58) |
| À propos | `Qui sommes-nous` | `Qui sommes-nous ? Équipe et méthode \| Exemple` (45) |

4. **Appliquer selon la source.**
   - Page `.astro` : `<BaseLayout title="Excel avancé : formation de 3 jours, éligible CPF" description="Excel avancé en 3 jours : tableaux croisés, macros et Power Query. Sessions à Lyon ou à distance.">`.
   - Collection Markdown/MDX : ajouter au schéma `seoTitle: z.string().min(25).max(60).optional()` dans `src/content.config.ts` (`import { z } from 'astro/zod'` à partir d'Astro 6 ; `import { z } from 'astro:content'` en Astro 5), remplir le frontmatter, puis dans la page : `title={entry.data.seoTitle ?? entry.data.title}`. En Astro 5 et plus, l'identifiant d'une entrée est `entry.id` (l'ancien `entry.slug` a disparu en v6).
   - Convex : champ `seoTitle: v.optional(v.string())` dans `convex/schema.ts` (l'ajout d'un champ optionnel ne casse pas les documents existants), lu par la requête de la page ; voir la fiche `contenu-meta-description` pour le code Convex complet et la mutation d'édition.
5. **Titres vides venant de données** : si le titre est construit avec une variable (`{page.titre}`), prévoir un repli : `const title = data?.seoTitle || data?.titre || "Exemple : organisme de formation à Lyon"`. Un `undefined` produit `<title></title>` ou « undefined | Exemple ».

## Critères d'acceptation

- [ ] Chaque page indexable a exactement un `<title>` non vide dans le HTML servi (pas ajouté par JavaScript).
- [ ] Longueur entre 25 et 65 caractères (idéal 30 à 60), marque comprise.
- [ ] Aucun titre générique (« Accueil », « Sans titre », « undefined »).
- [ ] `title` est une prop obligatoire du layout ; `npx astro check` passe.
- [ ] Aucune régression : build OK, pages clés en 200, rendu identique.

## Vérification après correction

```bash
npx astro check && npx astro build
find dist -name '*.html' | xargs grep -L '<title>'      # ne doit rien lister
python3 scripts/crawl_site.py https://SITE/ --out /tmp/verif/crawl
python3 -c "import json;d=json.load(open('/tmp/verif/crawl/issues.json'));print({k:v['count'] for k,v in d.items() if k.startswith('title_')})"
```

Le dernier affichage doit être vide (`{}`) ou ne plus contenir `title_missing`, `title_short`, `title_long`.

## Pièges et retour arrière

- Un titre plus court que l'ancien peut faire perdre un mot-clé utile : ne raccourcir que ce qui dépasse 65 caractères ou n'apporte rien.
- Google peut quand même réécrire le titre (titre jugé inexact, marque répétée, plusieurs titres équivalents) : c'est normal, corriger d'abord l'écart entre titre, H1 et contenu.
- Ne pas changer 200 titres d'un coup sur un site qui se positionne bien sans suivi : faire d'abord les pages sans titre ou génériques, puis mesurer dans Search Console.
- Retour arrière : `git revert` du commit ; les titres sont uniquement du texte.

## Pour aller plus loin

- https://developers.google.com/search/docs/appearance/title-link : ce que Google fait du titre, quand il le réécrit, absence de limite officielle.
- https://docs.astro.build/en/basics/layouts/ : layouts et props dans Astro.
- https://docs.astro.build/en/guides/content-collections/ : schéma de collection et frontmatter.
