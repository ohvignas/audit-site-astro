# Barème de notation

But : une note lisible, **reproductible** d'un audit à l'autre et facile à expliquer. Ce n'est pas un score magique : c'est 100 moins les problèmes confirmés.

## Note d'un domaine (sur 100)

```
note = max(0, 100 − 20 × nb_critiques − 10 × nb_hautes − 4 × nb_moyennes − 1 × nb_basses)
```

- Seuls les **constats confirmés** comptent (pas les « Écartés », pas les « Info »).
- Un constat = une cause. 38 URL touchées par la même cause comptent pour 1 constat : l'ampleur se reflète dans la sévérité choisie, pas dans le nombre de lignes.

| Note | Lettre | Lecture |
|---|---|---|
| 90–100 | A | Excellent, finitions seulement |
| 75–89 | B | Bon, quelques gains nets |
| 60–74 | C | Correct, plusieurs chantiers utiles |
| 40–59 | D | Faible, perte de trafic ou de sécurité probable |
| 0–39 | E | Urgent |

## Note globale

Moyenne pondérée des domaines :

| Domaine | Poids |
|---|---|
| Performance | 20 |
| SEO technique | 20 |
| Contenu | 15 |
| GEO / IA | 15 |
| Sécurité | 12 |
| Code Astro / Convex | 10 |
| Accessibilité | 8 |

Si un domaine n'a pas pu être audité (pas d'accès au code, par exemple), l'exclure et renormaliser les poids. Le préciser sous la note.

**Plafond de sécurité** : un constat Critique non corrigé en sécurité ou en SEO technique plafonne la note globale à 49/100. Un site qui expose un secret ou qui est désindexé n'est pas « bon », quelle que soit sa vitesse.

## Scores Lighthouse

Toujours affichés **à part** (tableau par page et par mode), avec la médiane si `RUNS≥3`. Ils varient de ±5 à 10 points d'un passage à l'autre : ne jamais annoncer une amélioration inférieure à 10 points sur un seul passage.

## Priorisation des actions

```
priorité = impact (1-5) × confiance (0,5 / 0,8 / 1) ÷ effort (S=1, M=2, L=4)
```

- **Impact** : 5 = critique ou gain majeur mesuré (secondes de LCP, pages désindexées), 1 = finition.
- **Confiance** : 1 si c'est mesuré sur le site, 0,8 si c'est très probable, 0,5 si c'est une hypothèse à valider.
- Les **P0** (critiques) passent avant tout, quel que soit le calcul.
