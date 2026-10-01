# Cobayes d'audit : jumeaux `casse` et `propre`

Deux sites Astro jumeaux servent à valider l'outil d'audit.

- `casse/` : site volontairement défectueux. Chaque défaut porte un ID en commentaire (ex. `H07`, `X01`, `G02`), dans le code Astro comme dans `nginx/conf.d/casse.conf`.
- `propre/` : jumeau sain, censé ne déclencher aucun de ces défauts (`nginx/conf.d/propre.conf` applique les bonnes pratiques).
- `nginx/` : proxy HTTPS (certificat auto-signé généré dans `nginx/certs/`, ignoré par git) et faux fichiers sensibles (`leurres/`, sans aucune valeur réelle).
- `nginx/images/` + `nginx/conf.d/images.conf` : hôte d'images « tiers » interne au réseau (`http://images.cobaye.test/cobaye.png`). `auditer.sh` le passe dans `AUDIT_IMAGE_DISTANTE` : la sonde X06 (proxy `/_image` ouvert) ne dépend ainsi d'aucun site Internet. Les liens vers cet hôte (adresse Docker privée) ne sont vérifiés par le crawl que grâce à `AUDIT_LIENS_PRIVES=1` (option `--liens-prives`), que `auditer.sh` passe : sinon ils sont « non vérifiés (adresse privée) », comme sur un vrai site.

## Commandes

```bash
bash tests/cobaye/lancer.sh            # certificat + docker compose up (réseau Docker "cobaye")
bash tests/cobaye/auditer.sh casse     # collecte -> audits-cobaye/casse/
bash tests/cobaye/auditer.sh propre    # collecte -> audits-cobaye/propre/
python3 tests/cobaye/score.py --casse audits-cobaye/casse --propre audits-cobaye/propre --phase 1 \
    [--sortie audits-cobaye] [--resume "$GITHUB_STEP_SUMMARY"]   # verdict rappel / faux positifs
```

`auditer.sh` utilise l'image `audit-site-astro:test` (variable `IMAGE_AUDIT` pour changer). Seul un code de collecte 0 passe : le code 1 (une étape ❌ = sortie absente ou inexploitable) ne doit arriver sur aucun des deux jumeaux, car un propre en panne passerait pour un propre sans faux positif ; le code 2 (site injoignable ou accueil en 5xx) et les codes docker sont remontés tels quels. Le verdict vient de `score.py`.

## Score

`score.py` compare les sorties (`audits-cobaye/casse`, `audits-cobaye/propre`) à `verite-terrain.json` :

- **rappel** : défauts requis (phase <= `--phase`) détectés sur le cassé ;
- **faux positifs** : matchers qui se déclenchent sur le propre. Les filtres d'emplacement propres au cassé (`contient`, `ou_contient`, `exemple_contient`) sont retirés : la seule présence de la clé du crawl ou de la regex compte. Un défaut peut fournir un `matcher_propre` explicite, ou porter `"propre": "ignorer"` avec une `raison_ignorer` quand son signal apparaît légitimement sur tout bon site ;
- **inattendus** : constats Critique/Haute du propre.

Avant de scorer, `score.py` refuse un dossier d'audit invalide (`data/COLLECTE.md` absent ou avec une étape ❌, ou l'un de `crawl/issues.json`, `geo/geo.json`, `code/code-scan.json`, `perf/pagespeed.json` manquant).

Codes de sortie : **0** seuils respectés ; **1** seuil violé (`seuils.json`) ; **2** audit invalide (mesure impossible).

Le leurre `/.git/HEAD` est stocké dans `nginx/leurres/git-HEAD` (git ne peut pas suivre un dossier `.git` imbriqué) et servi par un `alias` nginx.

## Avertissement RAM

`lancer.sh` construit deux sites Astro et lance nginx : compter environ 3 Go de RAM. À réserver à la CI (GitHub Actions), pas au poste local. Hors CI, le script laisse 5 s pour annuler.

## Règle

Un défaut = un ID en commentaire, jamais supprimé pour faire passer un build. Si le build casse, on corrige la cause en conservant le défaut.
