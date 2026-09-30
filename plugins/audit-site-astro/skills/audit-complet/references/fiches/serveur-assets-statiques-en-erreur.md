---
id: serveur-assets-statiques-en-erreur
titre: Fichiers CSS, JS, images ou polices référencés par la page mais introuvables (404/5xx)
domaine: Serveur / HTTP
severite_type: haute
effort: S
declencheurs:
  - "http:❌ HTTP \\d{3}"
sources:
  - https://docs.astro.build/en/guides/integrations-guide/node/
  - https://docs.astro.build/en/reference/configuration-reference/
  - https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Cache-Control
---

# Fichiers CSS, JS, images ou polices référencés par la page mais introuvables (404/5xx)

> **En une phrase** : le HTML pointe vers des fichiers que le serveur ne trouve plus ; la page s'affiche sans style, sans interactivité ou sans images.

## Pourquoi c'est important

Un `/_astro/xxx.css` en 404 donne une page « brute » sans mise en forme ; un `/_astro/xxx.js` en 404 casse les îlots interactifs (menu, formulaires). Google voit aussi une page dégradée (rendu cassé, CLS, LCP mauvais). La cause la plus fréquente est une **incohérence de déploiement** : le HTML (ancien, mis en cache) référence des fichiers hashés d'un ancien build qui ont été supprimés, ou l'inverse. Sur un site en SSR, un déploiement qui remplace `dist/` pendant que le process Node tourne encore produit le même effet.

L'outil ne signale ici que les 12 premières ressources de la page d'accueil : la ligne en `❌ HTTP 404` (ou 403, 500…) est un échantillon d'un problème potentiellement plus large.

## Comment le constater soi-même

```bash
# Statut de chaque ressource /_astro/ référencée par l'accueil
curl -s https://SITE/ | grep -oE '(src|href)="[^"]*/_astro/[^"]+"' | sed -E 's/^(src|href)="//; s/"$//' | sort -u | while read -r u; do
  printf '%s %s\n' "$(curl -s -o /dev/null -w '%{http_code}' "https://SITE$u")" "$u"
done
# Le fichier existe-t-il sur le disque du serveur ? (adapter Node : dossier dist/client/_astro)
ls dist/client/_astro | head
```

Problème présent : des codes 404, 403 ou 5xx. Corrigé : que des 200.

## Correction

1. **Identifier la cause** en comparant le HTML servi et les fichiers disponibles :
   - HTML à jour mais fichiers absents du disque → déploiement incomplet (build non copié, mauvais dossier `root` du proxy).
   - HTML ancien (cache CDN/proxy/navigateur) mais fichiers nouveaux → le HTML est resté en cache alors que l'ancien build a été supprimé.
   - 403 → droits de fichiers (utilisateur du service sans lecture sur `dist/`) ou règle de blocage du proxy trop large (par exemple une règle qui bloque les chemins contenant un point ou un underscore).
   - 5xx → le serveur Node est arrêté ou redémarre au moment de la requête.

2. **Purger le HTML en cache** (CDN, `proxy_cache`) après chaque déploiement, ou lui donner une durée courte (voir la fiche du cache HTML). Cloudflare : « Purge Everything » ou par préfixe ; nginx : supprimer le contenu de `proxy_cache_path` puis recharger.

3. **Déployer de façon atomique** (SSR Node) : construire dans un nouveau dossier, puis basculer un lien symbolique et redémarrer le process, plutôt que de réécrire `dist/` en place.

```bash
# Exemple de déploiement atomique, sur le serveur (adapter les chemins)
set -e
REL=/srv/exemple/releases/$(date +%Y%m%d%H%M%S)
mkdir -p "$REL" && cp -r dist "$REL/dist" && cp package.json package-lock.json "$REL/"
(cd "$REL" && npm ci --omit=dev)
ln -sfn "$REL" /srv/exemple/current
systemctl restart exemple-astro
```

4. **Garder l'ancien build** disponible quelques heures (ne pas supprimer les anciens fichiers `/_astro/` immédiatement) si un CDN ou des navigateurs peuvent encore servir l'ancien HTML.

5. **Si le proxy sert lui-même les fichiers** (nginx avec `root`), vérifier le chemin réel du dossier client :

```nginx
location /_astro/ {
    root /srv/exemple/current/dist/client;
    access_log off;
    add_header Cache-Control "public, max-age=31536000, immutable" always;
    try_files $uri =404;
}
```

6. **Astro `base` ou `build.assetsPrefix`** : si l'un des deux est défini dans `astro.config.mjs`, les URL des fichiers changent (`/base/_astro/…` ou CDN) : le proxy doit servir le même préfixe.

## Critères d'acceptation

- [ ] Toutes les ressources listées par le HTML de l'accueil répondent 200
- [ ] Après un déploiement test, aucun 404 sur `/_astro/` pendant et après la bascule
- [ ] Le HTML mis en cache est purgé ou de courte durée
- [ ] Aucune régression : rendu identique, JS des îlots actif

## Vérification après correction

```bash
bash scripts/http_checks.sh https://SITE/ /tmp/verif   # §4 : plus aucune ligne « ❌ HTTP »
python3 scripts/crawl_site.py https://SITE/ --out /tmp/verif/crawl   # broken_images vide
```

## Pièges et retour arrière

- Ne pas « réparer » en créant des fichiers vides : le navigateur mettrait le résultat en cache pour un an (`immutable`).
- Un 404 sur un fichier `/_astro/` mis en cache par un CDN reste servi tant qu'il n'est pas purgé.
- Retour arrière : rebasculer le lien symbolique `current` vers la version précédente et redémarrer le service.

## Pour aller plus loin

- https://docs.astro.build/en/guides/integrations-guide/node/ : dossier `dist/client/_astro` et cache des fichiers hashés.
- https://docs.astro.build/en/reference/configuration-reference/ : options `base` et `build.assetsPrefix`.
- https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Cache-Control : effet de `immutable` et du cache long.
