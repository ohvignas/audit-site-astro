# Cobayes d'audit : jumeaux `casse` et `propre`

Deux sites Astro jumeaux servent à valider l'outil d'audit.

- `casse/` : site volontairement défectueux. Chaque défaut porte un ID en commentaire (ex. `H07`, `X01`, `G02`), dans le code Astro comme dans `nginx/conf.d/casse.conf`.
- `propre/` : jumeau sain, censé ne déclencher aucun de ces défauts (`nginx/conf.d/propre.conf` applique les bonnes pratiques).
- `nginx/` : proxy HTTPS (certificat auto-signé généré dans `nginx/certs/`, ignoré par git) et faux fichiers sensibles (`leurres/`, sans aucune valeur réelle).

## Commandes

```bash
bash tests/cobaye/lancer.sh            # certificat + docker compose up (réseau Docker "cobaye")
bash tests/cobaye/auditer.sh casse     # collecte -> audits-cobaye/casse/
bash tests/cobaye/auditer.sh propre    # collecte -> audits-cobaye/propre/
python3 tests/cobaye/score.py …        # verdict (arrive dans une tâche ultérieure)
```

`auditer.sh` utilise l'image `audit-site-astro:test` (variable `IMAGE_AUDIT` pour changer) et sort toujours en code 0 : le verdict vient de `score.py`.

## Avertissement RAM

`lancer.sh` construit deux sites Astro et lance nginx : compter environ 3 Go de RAM. À réserver à la CI (GitHub Actions), pas au poste local. Hors CI, le script laisse 5 s pour annuler.

## Règle

Un défaut = un ID en commentaire, jamais supprimé pour faire passer un build. Si le build casse, on corrige la cause en conservant le défaut.
