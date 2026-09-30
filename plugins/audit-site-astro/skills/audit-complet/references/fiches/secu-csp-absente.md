---
id: secu-csp-absente
titre: "Aucune Content-Security-Policy (CSP)"
domaine: Sécurité
severite_type: moyenne
effort: M
declencheurs:
  - "http:\\| content-security-policy \\| — \\| ❌ absent"
  - "code:Aucune Content-Security-Policy"
versions_astro: ">=6.0"
sources:
  - https://docs.astro.build/en/reference/configuration-reference/#securitycsp
  - https://docs.astro.build/en/reference/api-reference/#csp
  - https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CSP
  - https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Content-Security-Policy-Report-Only
  - https://csp-evaluator.withgoogle.com/
---

# Aucune Content-Security-Policy (CSP)

> **En une phrase** : le navigateur n'a aucune consigne sur les scripts, styles et connexions autorisés ; si une faille XSS existe, l'attaquant n'est arrêté par rien.

## Pourquoi c'est important

La CSP est la deuxième ligne de défense contre l'injection de scripts (XSS) : même si un contenu malveillant passe dans une page, le navigateur refuse d'exécuter un script non autorisé ou d'envoyer des données vers un domaine inconnu. Elle limite aussi les effets d'un script tiers compromis (chat, analytics). C'est un durcissement, pas un correctif de faille : sévérité moyenne à basse pour un site vitrine, plus haute avec comptes utilisateurs ou contenu saisi par des visiteurs. Une CSP mal réglée casse le site : on la déploie d'abord en mode observation.

## Comment le constater soi-même

```bash
curl -sI https://exemple.fr/ | grep -i content-security-policy          # en-tête HTTP
curl -s https://exemple.fr/ | grep -io '<meta[^>]*content-security-policy[^>]*>'   # balise meta (Astro >= 6)
```

Absent : aucune sortie sur les deux commandes. Corrigé : l'un des deux renvoie une politique.

## Correction

Deux voies selon la version d'Astro (`npm ls astro`).

### Voie A : Astro 6.0 ou plus (recommandée), option `security.csp`

Astro calcule les empreintes (hashes) de ses scripts et styles au build et insère une balise `<meta http-equiv="content-security-policy">` dans chaque page.

1. Activer dans `astro.config.mjs` :

   ```js
   // astro.config.mjs
   import { defineConfig } from 'astro/config';

   export default defineConfig({
     security: {
       csp: {
         algorithm: 'SHA-256',
         directives: [
           "default-src 'self'",
           "img-src 'self' data: https://cdn.exemple.fr",
           "font-src 'self'",
           "connect-src 'self' https://nom-du-deploiement.convex.cloud wss://nom-du-deploiement.convex.cloud",
           "object-src 'none'",
           "base-uri 'self'",
           "form-action 'self'",
         ],
       },
     },
   });
   ```

   `script-src` et `style-src` sont produits par Astro (hashes). Pour autoriser un script externe précis, ajoutez `scriptDirective: { resources: ["'self'", "https://cdn.exemple.fr"] }` (attention : `resources` remplace la valeur par défaut, gardez `'self'`) ou, pour un script tiers avec empreinte connue, `scriptDirective: { hashes: ['sha384-...'] }`.
2. Contraintes documentées par Astro : pas de prise en charge du mode `dev` (testez avec `npm run build && npm run preview`), le routeur `<ClientRouter />` (View Transitions Astro) n'est pas supporté, Shiki n'est pas supporté, et les scripts/styles externes demandent leurs propres empreintes.
3. Les directives `frame-ancestors`, `report-uri` et `sandbox` sont **ignorées** dans une balise meta : posez-les en en-tête HTTP (`secu-anti-clickjacking`).
4. API d'exécution pour une page précise : `Astro.csp?.insertDirective(...)`, `insertScriptResource(...)`, `insertStyleResource(...)`.

### Voie B : CSP par en-tête HTTP au proxy (toutes versions)

Commencez en **observation** (`Content-Security-Policy-Report-Only`) : le navigateur signale les violations dans la console mais ne bloque rien.

nginx :

```nginx
add_header Content-Security-Policy-Report-Only "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; font-src 'self'; connect-src 'self' https://nom-du-deploiement.convex.cloud wss://nom-du-deploiement.convex.cloud; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'self'" always;
```

Caddy :

```caddy
header Content-Security-Policy-Report-Only "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; font-src 'self'; connect-src 'self' https://nom-du-deploiement.convex.cloud wss://nom-du-deploiement.convex.cloud; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'self'"
```

Cette politique de départ est volontairement large (`'unsafe-inline'`) pour ne rien casser. Elle apporte déjà `object-src 'none'`, `base-uri`, `form-action`, `frame-ancestors`. Pour la resserrer ensuite, voir `secu-csp-faible`.

### Déploiement par étapes (les deux voies)

1. Déployer en `Report-Only` (voie B) ou tester en préproduction (voie A).
2. Parcourir les pages clés avec la console ouverte : chaque « Refused to ... » signale une source à autoriser (police, image externe, iframe YouTube dans `frame-src`, analytics dans `script-src` et `connect-src`).
3. Corriger la liste, retester, puis renommer l'en-tête en `Content-Security-Policy` (voie B).
4. Vérifier une seule CSP effective par cause ; si les deux voies coexistent, le navigateur applique les deux (cumul).

## Critères d'acceptation

- [ ] Une CSP (en-tête ou meta) est présente sur toutes les pages, sans violation dans la console sur les pages clés.
- [ ] Elle contient au minimum `object-src 'none'`, `base-uri 'self'` et une restriction de `script-src`.
- [ ] Analytics, chat, cartes, vidéos et formulaires fonctionnent.
- [ ] Le rapport du CSP Evaluator ne signale aucun problème critique.

## Vérification après correction

```bash
curl -sI https://exemple.fr/ | grep -i content-security-policy
bash scripts/http_checks.sh https://exemple.fr/ /tmp/verif-http && grep -i 'content-security' /tmp/verif-http/http-checks.md
```

## Pièges et retour arrière

- Une CSP stricte sans phase de test casse silencieusement des fonctions (formulaire tiers, paiement, chat). Toujours observer d'abord.
- Les scripts injectés par des extensions du navigateur provoquent des violations parasites : ne pas les prendre en compte.
- Convex utilise WebSocket : `connect-src` doit contenir `wss://` en plus de `https://` pour le domaine de déploiement.
- Retour arrière : retirer la directive `security.csp` (redéployer) ou supprimer la ligne d'en-tête du proxy.

## Pour aller plus loin

- Astro, `security.csp` : options `algorithm`, `directives`, `scriptDirective`, `styleDirective`.
- Astro, API `csp` : ajout de sources par page.
- MDN, guide CSP : concepts et déploiement.
- MDN, `Content-Security-Policy-Report-Only` : mode observation.
- CSP Evaluator : analyse d'une politique.
