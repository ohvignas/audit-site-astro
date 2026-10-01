---
id: secu-cookies-attributs
titre: "Cookies sans attributs de sécurité (Secure, SameSite, HttpOnly, préfixes)"
domaine: Sécurité
severite_type: moyenne
effort: S
declencheurs:
  - "http:\\| Cookie [^|]+ \\|.*(⚠️|❌)"
sources:
  - https://developer.mozilla.org/en-US/docs/Web/HTTP/Cookies
  - https://developer.mozilla.org/en-US/observatory/docs/tests_and_scoring
  - https://owasp.org/www-project-secure-headers/
---

# Cookies sans attributs de sécurité

> **En une phrase** : un cookie posé sans `Secure` peut partir en clair, sans `SameSite` il accompagne les requêtes d'autres sites (CSRF), et un cookie de session sans `HttpOnly` est lisible par un script injecté.

## Pourquoi c'est important

MDN HTTP Observatory pénalise les cookies sans `Secure` et sans `HttpOnly` pour les sessions. Avec Astro, `Astro.cookies.set()` et les sessions (≥ 5.7) acceptent ces options ; un middleware ou un proxy peut aussi en poser.

L'outil distingue deux familles, d'après le **nom** du cookie (jamais sa valeur, qui n'est ni lue ni écrite) :

- **Cookie de session** (nom contenant `sid`, `session`, `auth`, `token`) : un attribut manquant (`Secure` sur un site https, `SameSite`, `HttpOnly`) est signalé en ❌ (gravité haute), car un vol de ce cookie donne accès au compte.
- **Autres cookies** : `Secure` ou `SameSite` manquants en ⚠️ (basse) ; `HttpOnly` manquant en ℹ️ seulement, car un cookie lu par JavaScript (préférences, jeton CSRF en double soumission, mesure d'audience `_ga`, `_fbp`…) ne peut pas l'avoir.

## Comment le constater soi-même

```bash
curl -sI https://SITE/ | grep -i '^set-cookie' | sed -E 's/=[^;]*/=…/'    # noms et attributs, sans les valeurs
```

## Correction

1. Dans Astro :
```ts
Astro.cookies.set('session', id, { path: '/', secure: true, httpOnly: true, sameSite: 'lax', maxAge: 60 * 60 * 24 });
```
2. Préfixe `__Host-` pour un cookie de session : impose `Secure`, `Path=/` et l'absence de `Domain`.
3. Cookie posé par nginx ou un CDN : ajouter les attributs dans sa configuration (`proxy_cookie_flags ~ secure samesite=lax;` avec nginx ≥ 1.19.3).

## Critères d'acceptation

- [ ] Chaque ligne « Cookie » de `http-checks.md` est ✅ ou ℹ️ (HttpOnly volontairement absent pour un cookie lu en JavaScript)
- [ ] Connexion, panier et formulaires fonctionnent toujours

## Vérification après correction

```bash
bash scripts/http_checks.sh https://SITE/ /tmp/verif && grep '| Cookie ' /tmp/verif/http-checks.md
```

## Pièges et retour arrière

- `SameSite=None` exige `Secure` ; `SameSite=Strict` casse les retours depuis un prestataire de paiement : préférer `Lax`.
- Un cookie consulté par un script (préférences d'affichage, mesure d'audience) ne doit pas recevoir `HttpOnly`.
- L'outil ne voit que les cookies posés par l'en-tête `Set-Cookie` de la page testée, pas ceux que JavaScript crée côté navigateur.
- Retour arrière : rétablir les options précédentes de `cookies.set` / du proxy.
