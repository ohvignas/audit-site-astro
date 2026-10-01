---
id: secu-sri-scripts-tiers
titre: "Scripts tiers chargés sans Subresource Integrity (SRI)"
domaine: Sécurité
severite_type: basse
effort: S
declencheurs:
  - "crawl:sri_absent"
  - "crawl:sri_non_applicable"
sources:
  - https://developer.mozilla.org/en-US/docs/Web/Security/Subresource_Integrity
  - https://developer.mozilla.org/en-US/observatory/docs/tests_and_scoring
  - https://docs.stripe.com/security/guide#content-security-policy
---

# Scripts tiers chargés sans Subresource Integrity

> **En une phrase** : un script servi par un hôte tiers s'exécute sur le site sans vérification ; si cet hôte est compromis, le code malveillant tourne chez tous les visiteurs.

## Pourquoi c'est important

L'attribut `integrity` (empreinte SHA-384) fait bloquer un fichier modifié. MDN HTTP Observatory le teste. Il n'est utile que pour un fichier **figé** : une bibliothèque à version exacte sur un CDN. Pour un script dont le contenu change par conception, il casserait la page à chaque mise à jour du fournisseur.

L'outil distingue donc deux constats :

- **`sri_absent` (basse, à vérifier)** : script d'un hôte tiers sans `integrity`, hors des cas ci-dessous. Cas typique : bibliothèque de jsdelivr, unpkg ou cdnjs à version exacte (`lib@1.2.3`, `/ajax/libs/jquery/3.7.1/`), ou fichier d'un hôte inconnu, à héberger soi-même ou à épingler.
- **`sri_non_applicable` (info, rien à corriger)** : chargeurs sans version dont le contenu change à dessein (Google Tag Manager et gtag, Google Analytics, Plausible, Stripe.js, Cloudflare Insights et Turnstile, reCAPTCHA, hCaptcha, pixels et widgets courants) et bibliothèques de jsdelivr/unpkg/cdnjs sans version exacte (`@latest`, `@1`, aucun `@`). Stripe demande explicitement de ne pas y mettre de SRI. Pour une bibliothèque de CDN sans version exacte, le seul conseil est d'épingler une version, puis d'ajouter l'empreinte.

Ne sont pas comptés : les scripts du même hôte que la page (y compris les modules `/_astro/` du site), les feuilles de style tierces (Google Fonts sert un CSS différent selon le navigateur, impossible à hacher) et les scripts `type="text/plain"` ou `text/partytown` bloqués par un gestionnaire de consentement.

## Comment le constater soi-même

```bash
curl -s https://SITE/ | grep -oE '<script[^>]+src="(https?:)?//[^"]+"[^>]*>' | grep -v integrity
```

## Correction

1. Pour une bibliothèque à version exacte (ex. `https://cdn.jsdelivr.net/npm/lib@1.2.3/dist/lib.min.js`), calculer l'empreinte :
```bash
curl -s URL | openssl dgst -sha384 -binary | openssl base64 -A
```
2. L'ajouter dans le composant Astro. `crossorigin="anonymous"` est nécessaire ici parce que le script vient d'une autre origine et porte un `integrity` : sans lui, le navigateur refuse de vérifier l'empreinte et bloque le script. Il est inutile sur un script du même site et sans intérêt sur un script sans `integrity`. Le CDN doit aussi renvoyer `Access-Control-Allow-Origin` (jsdelivr, unpkg et cdnjs le font).
```astro
<script is:inline src="https://cdn.jsdelivr.net/npm/lib@1.2.3/dist/lib.min.js"
  integrity="sha384-EMPREINTE" crossorigin="anonymous"></script>
```
3. Mieux encore : installer la bibliothèque avec npm et l'importer (Astro la sert depuis `/_astro/`, même origine, plus de SRI nécessaire).
4. Pour un chargeur dynamique (GTM, Stripe, reCAPTCHA…) : ne rien faire. Pour limiter le risque, passer par une politique CSP (`script-src` restreint à ces hôtes) plutôt que par une empreinte.

## Critères d'acceptation

- [ ] Chaque script tiers figé a un `integrity` et `crossorigin="anonymous"`, ou est auto-hébergé
- [ ] Les scripts dynamiques (GTM, Stripe…) sont listés comme exceptions assumées
- [ ] Aucune erreur « Failed to find a valid digest » dans la console

## Vérification après correction

```bash
python3 scripts/crawl_site.py https://SITE/ --out /tmp/verif/crawl --liens-externes 0
python3 -c "import json;[print(e['signature']) for e in json.load(open('/tmp/verif/crawl/issues.json')).get('sri_absent',{}).get('examples',[])]"
```

## Pièges et retour arrière

- Une mise à jour du fichier sur le CDN sans nouvelle empreinte bloque le script : toujours épingler une version exacte, jamais `@latest`.
- Un `integrity` sur un chargeur dynamique (GTM, Stripe) casse le script dès que le fournisseur le met à jour.
- Retour arrière : retirer l'attribut `integrity`.
