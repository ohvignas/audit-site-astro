---
id: seo-maillage-orphelines-profondeur
titre: Pages orphelines, pages trop profondes et liens non explorables
domaine: SEO technique
severite_type: moyenne
effort: M
declencheurs:
  - "crawl:orphan"
  - "crawl:deep_page"
  - "crawl:nofollow_internal"
  - "lighthouse:crawlable-anchors|liens ne peuvent pas être explorés"
  - "lighthouse:link-text|texte descriptif"
sources:
  - https://developers.google.com/search/docs/crawling-indexing/links-crawlable
  - https://developers.google.com/search/docs/crawling-indexing/qualify-outbound-links
  - https://developer.chrome.com/docs/lighthouse/seo/link-text
---

# Pages orphelines, pages trop profondes et liens non explorables

> **En une phrase** : des pages n'ont aucun lien interne qui y mène, ou sont à plus de 3 clics de l'accueil, ou sont liées par des liens que Google ne peut pas suivre.

## Pourquoi c'est important

Google découvre et hiérarchise les pages en suivant les liens. Une page **orpheline** (présente dans le sitemap mais liée depuis nulle part) reçoit très peu de poids et est explorée rarement. Une page **profonde** (plus de 3 clics depuis l'accueil) est jugée moins importante. Les liens internes sont aussi le principal levier pour positionner les pages business (formations, services, catégories). Google ne suit que les liens `<a href="...">` avec une vraie adresse : un `<a>` sans `href`, un `onclick` ou un `href="javascript:..."` n'est pas exploré. Un `rel="nofollow"` sur un lien interne coupe la transmission de poids sans raison.

## Comment le constater soi-même

```bash
# Pages orphelines et profondes (issues.json du crawl)
python3 - <<'EOF'
import json
d = json.load(open('data/crawl/issues.json'))
for k in ('orphan', 'deep_page', 'nofollow_internal'):
    print(k, d.get(k, {}).get('count'))
    for e in d.get(k, {}).get('examples', [])[:10]:
        print('  ', e)
EOF
# Liens non explorables dans le code
grep -rn '<a ' src/ | grep -v 'href' | head
grep -rnE 'href="(javascript:|#)"|onclick="?window\.location' src/ | head
grep -rn 'rel="nofollow"' src/ | head
```

`summary.md` du crawl liste aussi « Pages indexables les moins liées ».

## Correction

1. **Orphelines** : ajouter au moins 2 liens contextuels vers chaque page depuis des pages proches (article du blog qui cite une formation, page catégorie, page « voir aussi »), avec une ancre qui décrit la page (« formation Excel niveau 2 » et non « cliquez ici »).
2. **Créer des hubs** : pages de catégories ou de listes (`/blog/`, `/formations/`) qui listent toutes les pages d'une famille, elles-mêmes liées depuis le menu ou le pied de page. Une liste générée depuis la donnée évite d'en oublier :

```astro
---
// src/pages/formations/index.astro : hub qui lie toutes les formations
import { getCollection } from 'astro:content';
import BaseLayout from '../../layouts/BaseLayout.astro';
const formations = (await getCollection('formations')).filter((f) => !f.data.brouillon);
---
<BaseLayout title="Toutes nos formations" description="Catalogue complet des formations.">
  <h1>Formations</h1>
  <ul>
    {formations.map((f) => (
      {/* f.id : identifiant de l'entrée (Astro >= 5) ; avec l'ancienne API de collections, utiliser f.slug */}
      <li><a href={`/formations/${f.id}/`}>{f.data.titre}</a></li>
    ))}
  </ul>
</BaseLayout>
```

3. **Profondeur** : remonter à moins de 4 clics les pages importantes : lien depuis l'accueil, le menu, un bloc « populaires » ou un fil d'Ariane. Pagination : proposer aussi un accès direct (archives par catégorie) plutôt qu'une seule liste paginée.
4. **Liens explorables** : remplacer les faux liens par de vrais `<a href>` (les boutons qui déclenchent une action restent des `<button>`).

```astro
<!-- Non explorable -->
<a onclick="window.location='/contact/'">Contact</a>
<!-- Explorable -->
<a href="/contact/">Contact</a>
```

5. **nofollow interne** : retirer `rel="nofollow"` des liens internes sauf cas précis (liens générés par les utilisateurs).
6. Ajouter les pages profondes au sitemap (fiche `seo-sitemap-coherence`) : c'est un complément, pas un remplacement du maillage.
7. Ne pas se limiter au menu et au pied de page : ces liens sont identiques partout et pèsent peu. Privilégier les liens dans le contenu.

## Critères d'acceptation

- [ ] Chaque page indexable reçoit au moins 2 liens internes depuis des pages différentes (`orphan` = 0)
- [ ] Les pages stratégiques sont à 3 clics ou moins de l'accueil (`deep_page` sans page stratégique)
- [ ] Tous les liens de navigation sont des `<a href>` avec adresse réelle ; Lighthouse `crawlable-anchors` réussi
- [ ] Ancres descriptives (Lighthouse `link-text` réussi) ; aucun `nofollow` interne injustifié
- [ ] Aucune régression : pas de liens cassés introduits

## Vérification après correction

```bash
python3 scripts/crawl_site.py https://SITE/ --out /tmp/verif   # orphan, deep_page, nofollow_internal
sed -n '/moins liées/,$p' /tmp/verif/summary.md                 # pages les moins liées
bash scripts/lighthouse_run.sh /tmp/verif-lh https://SITE/     # crawlable-anchors, link-text
```

## Pièges et retour arrière

- Le crawler ne suit que les liens présents dans le HTML : une page dont les liens sont injectés par JavaScript (`client:only`) paraît orpheline (fiche `seo-contenu-rendu-client`).
- Trop de liens (des centaines par page) dilue leur poids : viser la pertinence.
- Si le crawl atteint sa limite de pages (`--max-pages`), des pages profondes peuvent paraître orphelines par simple absence d'exploration.
- Retour arrière : retirer les blocs de liens ajoutés (Git).

## Pour aller plus loin

- https://developers.google.com/search/docs/crawling-indexing/links-crawlable : liens explorables, ancres, `href` valide.
- https://developers.google.com/search/docs/crawling-indexing/qualify-outbound-links : `nofollow`, `sponsored`, `ugc`.
- https://developer.chrome.com/docs/lighthouse/seo/link-text : audit Lighthouse sur le texte des liens (l'audit « liens explorables » s'appuie sur les mêmes règles de `href` que la doc Google ci-dessus).
