---
id: secu-hsts-absent
titre: "En-tête HSTS (Strict-Transport-Security) absent"
domaine: Sécurité
severite_type: moyenne
effort: S
declencheurs:
  - "http:\\| strict-transport-security \\| — \\| ❌ absent"
sources:
  - https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Strict-Transport-Security
  - https://hstspreload.org/
  - https://nginx.org/en/docs/http/ngx_http_headers_module.html#add_header
  - https://caddyserver.com/docs/caddyfile/directives/header
---

# En-tête HSTS (Strict-Transport-Security) absent

> **En une phrase** : rien n'oblige le navigateur à toujours utiliser https pour votre site, ce qui laisse une porte ouverte aux attaques de « rétrogradation » sur les réseaux non fiables (Wi-Fi public).

## Pourquoi c'est important

Sans HSTS, un visiteur qui tape `exemple.fr` ou clique sur un vieux lien `http://` fait sa première requête en clair : un intermédiaire (Wi-Fi public, réseau piégé) peut l'intercepter et l'empêcher d'arriver en https. Avec HSTS, le navigateur, après une première visite, refuse toute connexion non chiffrée vers votre domaine pendant la durée indiquée (`max-age`). C'est une protection standard, attendue par les audits de sécurité, et sans coût de performance (elle évite même la redirection http vers https aux visites suivantes).

## Comment le constater soi-même

```bash
curl -sI https://exemple.fr/ | grep -i strict-transport-security
```

Absent : aucune ligne. Corrigé : `strict-transport-security: max-age=31536000; includeSubDomains`.

## Correction

**Préalable indispensable** : le site et tous les sous-domaines concernés répondent bien en https avec un certificat valide, et `http://` redirige en un saut vers `https://` (301/308). HSTS étant mémorisé par les navigateurs, une erreur est difficile à annuler : déployez par paliers.

1. **Palier 1 (test)** : `max-age=300` (5 minutes). Vérifiez que tout fonctionne.
2. **Palier 2** : `max-age=604800` (1 semaine) pendant quelques jours.
3. **Palier final** : `max-age=31536000` (1 an). Ajoutez `includeSubDomains` **seulement si tous** vos sous-domaines (mail, intranet, préproduction…) sont en https.
4. `preload` : ne l'ajoutez qu'en connaissance de cause. Il inscrit le domaine dans les navigateurs (liste hstspreload.org), exige `max-age` d'au moins un an, `includeSubDomains` et la redirection https, et le retrait prend des mois.

nginx (bloc `server` qui écoute en 443 ; `always` pour l'envoyer aussi sur les erreurs) :

```nginx
add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
```

Attention : dans nginx, si un bloc `location` contient ses propres `add_header`, il **n'hérite plus** de ceux du `server`. Répétez la ligne dans ces blocs (ou regroupez les en-têtes dans un fichier `include`).

Caddy (Caddy active https et la redirection seuls, mais n'envoie pas HSTS par défaut) :

```caddy
exemple.fr {
    header Strict-Transport-Security "max-age=31536000; includeSubDomains"
    reverse_proxy 127.0.0.1:4321
}
```

Autres hébergements : voir la fiche `secu-en-tetes-securite-manquants` (fichier `_headers` Netlify / Cloudflare Pages, `vercel.json`, middleware Astro).

Redirection http vers https en un saut (si absente) :

```nginx
server {
    listen 80;
    server_name exemple.fr www.exemple.fr;
    return 301 https://exemple.fr$request_uri;
}
```

## Critères d'acceptation

- [ ] `curl -sI https://exemple.fr/` affiche `strict-transport-security` avec `max-age` d'au moins 31536000 (palier final).
- [ ] `http://exemple.fr/` redirige en un saut 301 vers `https://exemple.fr/`.
- [ ] Aucun sous-domaine en http si `includeSubDomains` est utilisé.
- [ ] Aucune régression : pages et assets en 200.

## Vérification après correction

```bash
curl -sI https://exemple.fr/ | grep -i strict-transport-security
bash scripts/http_checks.sh https://exemple.fr/ /tmp/verif-http && grep strict-transport /tmp/verif-http/http-checks.md
```

## Pièges et retour arrière

- HSTS est ignoré sur une réponse en http : il doit être envoyé sur https.
- `includeSubDomains` bloque un sous-domaine qui n'a pas de certificat valide (intranet, ancien outil) : listez-les d'abord (`dig`, tableau de bord DNS).
- Retour arrière : envoyer `max-age=0` pendant la durée de l'ancien `max-age` pour effacer la règle des navigateurs. Une entrée « preload » est beaucoup plus longue à retirer.
- Sauvegardez la configuration avant modification et testez avec `nginx -t` / `caddy validate`.

## Pour aller plus loin

- MDN, `Strict-Transport-Security` : directives et exemples.
- hstspreload.org : critères et vérificateur de liste de préchargement.
- nginx `add_header` : règles d'héritage entre blocs.
- Caddy `header` : poser ou supprimer un en-tête.
