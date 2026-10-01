---
id: secu-csp-faible
titre: "CSP trop permissive (unsafe-inline sans nonce/hash, unsafe-eval)"
domaine: Sécurité
severite_type: basse
effort: M
declencheurs:
  - "http:\\| CSP \\| script-src 'unsafe-inline' sans nonce/hash"
  - "http:\\| CSP \\| contient 'unsafe-eval'"
versions_astro: ">=6.0"
sources:
  - https://docs.astro.build/en/reference/configuration-reference/#securitycspscriptdirective
  - https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CSP#the_strict-dynamic_keyword
  - https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CSP#unsafe_inline_script
  - https://csp-evaluator.withgoogle.com/
---

# CSP trop permissive (unsafe-inline sans nonce/hash, unsafe-eval)

> **En une phrase** : une CSP existe mais elle autorise n'importe quel script inline (`'unsafe-inline'`) ou l'évaluation de texte en code (`'unsafe-eval'`), ce qui annule l'essentiel de sa protection contre le XSS.

## Pourquoi c'est important

Un XSS consiste presque toujours à injecter un `<script>` inline ou un gestionnaire `onclick=`. Avec `script-src 'unsafe-inline'` sans nonce ni empreinte, le navigateur exécute ce script : la CSP ne bloque rien d'essentiel. `'unsafe-eval'` autorise `eval()` et `new Function()`, deuxième voie classique d'exécution de code injecté. Cette CSP donne surtout une fausse impression de sécurité. Les autres directives (`object-src`, `base-uri`, `frame-ancestors`, `connect-src`) gardent leur valeur.

## Comment le constater soi-même

```bash
curl -sI https://exemple.fr/ | grep -i content-security-policy | tr ';' '\n' | grep -E "script-src|unsafe"
```

Présent : `script-src ... 'unsafe-inline'` sans `'nonce-...'` ni `'sha256-...'`, ou `'unsafe-eval'`. Corrigé : `script-src 'self' 'sha256-...'` (ou nonce) et `'strict-dynamic'` éventuel, aucun `unsafe-*`. Attention : si un nonce ou un hash est présent dans la directive, les navigateurs modernes ignorent `'unsafe-inline'`, qui ne sert plus alors que de repli pour très anciens navigateurs.

## Correction

1. **Astro 6.0 ou plus : laisser Astro produire des empreintes** au lieu de `'unsafe-inline'` (voir `secu-csp-absente`, voie A).

   ```js
   // astro.config.mjs
   import { defineConfig } from 'astro/config';

   export default defineConfig({
     security: {
       csp: {
         scriptDirective: {
           resources: ["'self'"],   // ne pas ajouter 'unsafe-inline' : Astro supprimerait alors ses empreintes
           strictDynamic: true,     // les scripts chargés par un script autorisé le sont aussi
         },
         styleDirective: {
           resources: ["'self'"],
         },
       },
     },
   });
   ```

   Documentation Astro : quand `'unsafe-inline'` est présent dans une directive, Astro n'émet plus d'empreintes pour elle, ce qui ramène la directive au niveau `'unsafe-inline'`. Retirez donc ce mot-clé de toute ressource `resources` pour retrouver la protection.
2. **Retirer la CSP maintenue à la main au proxy** (ou la mettre à jour) pour qu'elle ne réintroduise pas `'unsafe-inline'` : les deux politiques se cumulent, la plus stricte gagne mais un `unsafe-inline` restant crée de la confusion.
3. **Scripts tiers inline** (Google Tag Manager, pixels) : chargez-les depuis un fichier externe autorisé (`resources`) ou fournissez leur empreinte (`scriptDirective.hashes: ['sha384-...']`). Un script inline dont le contenu change à chaque requête ne peut pas être couvert par une empreinte : utilisez un nonce ou chargez-le en fichier.
4. **Styles inline** : `style-src 'unsafe-inline'` est nettement moins dangereux que pour les scripts et parfois inévitable (bibliothèques de composants). Traitez d'abord `script-src`.
5. **`'unsafe-eval'`** : identifiez la bibliothèque qui en a besoin (console : « Refused to evaluate a string as JavaScript »). Mettez-la à jour ou remplacez-la (certains anciens graphiques, moteurs de templates). Une fois retirée, supprimez `'unsafe-eval'` de la politique. Ne l'ajoutez jamais « pour que ça marche ».
6. **Autres versions d'Astro (< 6)** : impossible d'avoir des empreintes automatiques ; mettez à jour Astro (voir la fiche Code) ou, en attendant, gardez `object-src 'none'; base-uri 'self'; frame-ancestors 'self'` qui protègent sans casser.
7. Testez d'abord en `Content-Security-Policy-Report-Only` sur les pages clés, puis passez en mode bloquant.

## Critères d'acceptation

- [ ] Aucun `'unsafe-eval'` dans la politique.
- [ ] `script-src` ne contient pas `'unsafe-inline'` seul : nonce ou empreintes à la place.
- [ ] Console sans violation CSP sur les pages clés ; analytics, chat, formulaires fonctionnent.
- [ ] CSP Evaluator ne signale plus de problème « high » sur `script-src`.

## Vérification après correction

```bash
curl -s https://exemple.fr/ | grep -io '<meta[^>]*content-security-policy[^>]*>' | tr ';' '\n' | grep script-src
curl -sI https://exemple.fr/ | grep -i content-security-policy | tr ';' '\n' | grep script-src
bash scripts/http_checks.sh https://exemple.fr/ /tmp/verif-http && grep -E '^\| CSP' /tmp/verif-http/http-checks.md || echo "plus d'avertissement CSP"
```

## Pièges et retour arrière

- Le contrôle automatique de l'outil ne lit que l'**en-tête** HTTP : une CSP posée par balise meta (Astro) n'est pas analysée par `http_checks.sh` ; vérifiez-la avec la deuxième commande ci-dessus.
- Le routeur `<ClientRouter />` d'Astro n'est pas compatible avec `security.csp` : retirez-le ou utilisez la View Transition native du navigateur.
- Retour arrière : restaurer l'ancienne politique (Git) ; en cas de casse en production, repassez temporairement l'en-tête en `Report-Only`.

## Pour aller plus loin

- Astro, `scriptDirective` et `styleDirective` : `resources`, `hashes`, `strictDynamic`.
- MDN, `strict-dynamic` : propagation de la confiance aux scripts chargés.
- MDN, `unsafe-inline` : pourquoi éviter, et l'effet d'un nonce ou d'une empreinte.
- CSP Evaluator : audit d'une politique.
