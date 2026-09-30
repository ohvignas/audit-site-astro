---
id: contenu-fraicheur
titre: Contenus non datés ou périmés (années dans les titres, chiffres obsolètes)
domaine: Contenu
severite_type: moyenne
effort: M
declencheurs:
  - "geo:Articles sans date de mise à jour"
sources:
  - https://developers.google.com/search/docs/appearance/publication-dates
  - https://developers.google.com/search/docs/fundamentals/creating-helpful-content
  - https://docs.astro.build/en/guides/content-collections/
---

# Contenus non datés ou périmés (années dans les titres, chiffres obsolètes)

> **En une phrase** : les pages ne montrent pas quand elles ont été revues et contiennent des années, prix ou règles périmés, ce qui fait perdre la confiance des lecteurs et des moteurs.

## Pourquoi c'est important

Pour les sujets qui évoluent (prix, réglementation, financement CPF, outils, salaires), un contenu daté de 2023 est écarté par les lecteurs et par les IA qui privilégient les sources récentes. Google recommande d'afficher une date visible sur la page et de la déclarer de façon cohérente (données structurées `datePublished` et `dateModified`) ; il précise ne pas vouloir de date modifiée artificiellement : la date de mise à jour n'a de valeur que si le contenu a réellement été revu. La partie balisage (meta `article:modified_time`, JSON-LD) est traitée dans `geo-articles-auteur-date-maj` ; cette fiche traite l'éditorial : repérer le périmé, le réviser et instaurer un rythme de revue.

## Comment le constater soi-même

```bash
# années passées dans les textes et les titres
grep -rnE "(20(1[0-9]|2[0-5]))" src/content src/pages | grep -v "©" | head -40
# année dans les titres publiés
curl -s https://SITE/sitemap-0.xml | grep -o '<loc>[^<]*</loc>' | sed 's/<[^>]*>//g' | head -50 | while read u; do
  curl -s "$u" | grep -o '<title>[^<]*</title>' | grep -E '20[0-9]{2}' | sed "s|^|$u  |"; done
# date visible sur un article
curl -s https://SITE/blog/EXEMPLE/ | grep -oE '<time[^>]*>[^<]*</time>'
```

Adapter l'expression au millésime courant (les années antérieures à l'année en cours sont suspectes). Problème présent : titres ou textes portant des années passées, aucune balise `<time>` sur les articles.

## Correction

1. **Inventaire** : lister les contenus qui vieillissent (prix, tarifs, réglementation, financement, dates de session, statistiques, captures d'écran d'outils, « en 2024 »). Priorité aux pages qui reçoivent du trafic ou qui vendent.
2. **Champs de date dans le contenu** : ajouter au schéma de collection `pubDate` et `updatedDate` (voir l'extrait de `geo-articles-auteur-date-maj`), ou en Convex `publieLe: v.number()` et `misAJourLe: v.optional(v.number())` (timestamps en millisecondes). Ne jamais mettre la date du jour automatiquement à chaque build.
3. **Afficher la date** au début de l'article, avec la balise sémantique :

```astro
---
const { pubDate, updatedDate } = Astro.props;
const fr = (d: Date) => d.toLocaleDateString("fr-FR", { day: "numeric", month: "long", year: "numeric" });
---
<p class="meta">
  Publié le <time datetime={pubDate.toISOString()}>{fr(pubDate)}</time>
  {updatedDate && <> · Mis à jour le <time datetime={updatedDate.toISOString()}>{fr(updatedDate)}</time></>}
</p>
```

4. **Titres avec année** : deux stratégies. (a) Retirer l'année si le contenu est durable (« Meilleures formations Excel » plutôt que « en 2024 »). (b) La garder (« Guide 2026 ») mais alors réviser la page chaque année en mettant à jour le contenu, le `title`, le H1 et `updatedDate` ; ne pas changer seulement l'année dans le titre sans revoir le fond.
5. **Réviser le fond** : mettre à jour chaque chiffre avec sa source et sa date, remplacer les captures obsolètes, supprimer les sessions passées (ou les basculer en « sessions précédentes »), corriger les liens sortants cassés. Puis seulement, renseigner `updatedDate` (frontmatter Markdown : `updatedDate: 2026-09-30`).
6. **Rythme de revue** : proposer un calendrier (trimestriel pour les prix et financements, annuel pour les guides) et l'écrire dans un fichier du dépôt (`CONTENU-REVUE.md` : page, dernière revue, prochaine revue), à valider avec le propriétaire.
7. **Contenu sans valeur durable** (actualité ancienne, événement passé) : le laisser daté et lié à sa suite (« voir la version 2026 »), le rediriger en 301 vers la version à jour, ou le passer en `noindex` s'il n'apporte rien.

## Critères d'acceptation

- [ ] Chaque article et guide affiche une date de publication et, si révisé, une date de mise à jour visibles dans des balises `<time datetime>`.
- [ ] Aucun titre ne contient une année passée sans que la page ait été révisée pour cette année.
- [ ] Les pages prioritaires (business, plus visitées) ont été relues, chiffres et prix vérifiés auprès du propriétaire.
- [ ] `updatedDate` correspond à une vraie révision ; un calendrier de revue existe.
- [ ] Build OK.

## Vérification après correction

```bash
npx astro build
grep -rlE "<time " dist/blog | wc -l                    # autant que d'articles
python3 scripts/geo_check.py https://SITE/ --out /tmp/verif/geo --crawl /tmp/verif/crawl/pages.json
grep -iE 'sans date' /tmp/verif/geo/geo-summary.md      # ne doit rien renvoyer
```

## Pièges et retour arrière

- Modifier la date sans changer le contenu est une pratique contraire aux consignes de Google : à proscrire.
- Ne pas afficher deux dates contradictoires (une visible, une dans le JSON-LD) : elles doivent être identiques.
- Fuseaux horaires : `toISOString()` sort en UTC, l'affichage `toLocaleDateString("fr-FR")` utilise le fuseau du serveur ; pour une date pure, stocker à midi ou préciser `timeZone: "Europe/Paris"`.
- Retour arrière : `git revert` ; retirer un champ de date optionnel ne casse rien.

## Pour aller plus loin

- https://developers.google.com/search/docs/appearance/publication-dates : afficher et déclarer les dates de publication.
- https://developers.google.com/search/docs/fundamentals/creating-helpful-content : contenu utile et fiable.
- https://docs.astro.build/en/guides/content-collections/ : champs de date dans le schéma.
