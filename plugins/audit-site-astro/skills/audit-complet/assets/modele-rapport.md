# Audit du site — {{domaine}}

_{{date}} · Périmètre : {{nb_pages}} pages crawlées, {{nb_pages_lighthouse}} pages mesurées (mobile + desktop), code {{accès_code: oui/non}} · Dossier : `{{chemin_audit}}`_

## En bref

{{3 à 5 phrases : état général, les 2-3 problèmes qui coûtent le plus, le gain attendu si on applique la semaine 1.}}

| Domaine | Note | | Constats (C/H/M/B) |
|---|---|---|---|
| Performance | {{n}}/100 | {{A-E}} | {{0/2/3/1}} |
| SEO technique | | | |
| Contenu | | | |
| GEO / IA | | | |
| Sécurité | | | |
| Code Astro / Convex | | | |
| Accessibilité | | | |
| **Global** | **{{n}}/100** | **{{A-E}}** | |

### Lighthouse (médiane)

| Page | Mobile perf | Desktop perf | LCP mobile | CLS | TBT | A11y | SEO |
|---|---|---|---|---|---|---|---|
| {{/}} | | | | | | | |

{{Données terrain CrUX si disponibles, sinon : « pas assez de trafic Chrome pour des données terrain ».}}

## Top 10 des actions

| # | Action | Domaine | Gain attendu | Effort | ID |
|---|---|---|---|---|---|
| 1 | {{verbe + objet, concret}} | | {{mesuré ou estimé}} | S | PERF-001 |

## Feuille de route

### Cette semaine — urgences + quick wins
- [ ] {{ID}} — {{action}} ({{effort}})

### Ce mois-ci
- [ ] …

### Ce trimestre
- [ ] …

## Constats détaillés

### Performance
{{blocs au format commun, triés par sévérité}}

### SEO technique
### Contenu
### GEO / IA
### Sécurité
### Code Astro / Convex
### Accessibilité

## Écartés (faux positifs des scripts)
- {{signal}} — {{pourquoi ce n'en est pas un}}

## Limites de cet audit
- {{ce qui n'a pas pu être testé et pourquoi : pas d'accès aux logs, pas de données CrUX, pages derrière connexion, etc.}}

## Annexes
- Données brutes : `data/` (voir `data/COLLECTE.md`)
- Rapports par domaine : `rapports/`
- Commande pour refaire la collecte : `bash collect_all.sh {{url}} {{projet}}`
