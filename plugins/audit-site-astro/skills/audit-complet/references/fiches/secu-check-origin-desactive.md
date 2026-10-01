---
id: secu-check-origin-desactive
titre: "Protection CSRF d'Astro désactivée (security.checkOrigin: false)"
domaine: Sécurité
severite_type: moyenne
effort: S
declencheurs:
  - "code:security\\.checkOrigin désactivé"
versions_astro: ">=4.9"
sources:
  - https://docs.astro.build/en/reference/configuration-reference/#securitycheckorigin
  - https://docs.astro.build/en/reference/configuration-reference/#securityalloweddomains
  - https://developer.mozilla.org/en-US/docs/Web/Security/Attacks/CSRF
---

# Protection CSRF d'Astro désactivée (security.checkOrigin: false)

> **En une phrase** : Astro ne vérifie plus que les formulaires envoyés à vos pages viennent bien de votre site, ce qui permet à un site tiers de faire soumettre des formulaires à vos visiteurs connectés.

## Pourquoi c'est important

Une attaque CSRF pousse le navigateur d'un visiteur (connecté chez vous) à envoyer, depuis un autre site, un formulaire vers le vôtre : changement d'adresse e-mail, suppression, achat. Astro protège par défaut (`checkOrigin: true`) en comparant l'en-tête `Origin` à l'URL de la requête et répond 403 sinon. La vérification s'applique aux pages rendues à la demande, pour les méthodes `POST`, `PATCH`, `DELETE` et `PUT` avec les types `application/x-www-form-urlencoded`, `multipart/form-data` ou `text/plain`. La désactiver retire cette barrière. Sur un site vitrine sans session, le risque est faible ; avec espace client ou administration, il est réel.

## Comment le constater soi-même

```bash
grep -n -B2 -A3 "checkOrigin" astro.config.*
# Test : un POST de formulaire avec une origine étrangère doit être refusé (403)
curl -s -o /dev/null -w '%{http_code}\n' -X POST -H 'Origin: https://evil.example' \
  -H 'Content-Type: application/x-www-form-urlencoded' -d 'test=1' https://exemple.fr/formulaire-ssr
```

Problème présent : `checkOrigin: false` dans la config et réponse ≠ 403 au test (sur une route rendue à la demande qui accepte les POST). Corrigé : option absente (ou `true`) et 403.

## Correction

1. **Chercher pourquoi elle a été désactivée** : le plus souvent parce que les formulaires légitimes renvoyaient « Cross-site POST form submissions are forbidden » derrière un reverse proxy. Dans ce cas l'URL vue par Astro (souvent `http://localhost:4321`) ne correspond pas à l'`Origin` du navigateur (`https://exemple.fr`). La bonne correction est de configurer le proxy et `security.allowedDomains` (voir `secu-allowed-domains-host-header`), pas de désactiver la protection.
2. **Réactiver** dans `astro.config.mjs` (supprimez simplement la ligne `checkOrigin: false`, la valeur par défaut est `true`) :

   ```js
   // astro.config.mjs
   import { defineConfig } from 'astro/config';

   export default defineConfig({
     output: 'server', // ou 'static' + pages rendues à la demande avec un adaptateur
     security: {
       checkOrigin: true,
       allowedDomains: [{ hostname: 'exemple.fr', protocol: 'https' }],
     },
   });
   ```
3. **Proxy** : transmettre l'hôte et le protocole d'origine.

   ```nginx
   location / {
       proxy_pass http://127.0.0.1:4321;
       proxy_set_header Host $host;
       proxy_set_header X-Forwarded-Proto $scheme;
       proxy_set_header X-Forwarded-Host $host;
   }
   ```

   Caddy `reverse_proxy` pose déjà `X-Forwarded-Proto` et `X-Forwarded-Host`.
4. **Webhook tiers qui envoie un POST en formulaire** (paiement, e-mailing) : ne désactivez pas la protection pour tout le site. Faites recevoir le webhook par un endpoint qui accepte un corps JSON (`application/json` n'est pas concerné par la vérification d'origine) et **vérifiez la signature** du fournisseur.
5. **Endpoints JSON** (`src/pages/api/*`, Actions) : la vérification d'origine ne les couvre pas. Exigez une authentification par en-tête (jeton) ou des cookies `SameSite=Lax`/`Strict`, `Secure`, `HttpOnly`, et contrôlez vous-même `Origin` pour les actions sensibles.

   ```ts
   const origine = request.headers.get('Origin');
   if (origine !== new URL(request.url).origin) return new Response('Forbidden', { status: 403 });
   ```
6. Retestez les formulaires en production après redéploiement.

## Critères d'acceptation

- [ ] `checkOrigin` n'est plus à `false` dans la configuration.
- [ ] Un POST de formulaire avec `Origin: https://evil.example` reçoit 403.
- [ ] Les formulaires du site (contact, inscription) fonctionnent depuis le domaine réel.
- [ ] Les webhooks légitimes fonctionnent (endpoint JSON avec signature).

## Vérification après correction

```bash
curl -s -o /dev/null -w '%{http_code}\n' -X POST -H 'Origin: https://evil.example' -H 'Content-Type: application/x-www-form-urlencoded' -d 'test=1' https://exemple.fr/formulaire-ssr   # 403
python3 scripts/astro_scan.py . --out /tmp/verif-code && grep -i checkOrigin /tmp/verif-code/code-scan.md || echo "constat levé"
```

## Pièges et retour arrière

- Un formulaire qui s'affichait avant et renvoie 403 après réactivation révèle un problème de proxy à corriger (pas de protection à couper).
- Les pages entièrement statiques n'ont pas de vérification d'origine côté serveur : la protection ne concerne que le rendu à la demande.
- Retour arrière : remettre `checkOrigin: false` de façon temporaire seulement, avec un ticket pour corriger la cause.

## Pour aller plus loin

- Astro, `security.checkOrigin` : méthodes et types de contenu concernés.
- Astro, `security.allowedDomains` : domaines de confiance derrière un proxy.
- MDN, CSRF : principe de l'attaque et parades.
