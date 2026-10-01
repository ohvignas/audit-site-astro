---
name: audit-securite
description: Audit de sécurité défensif et non intrusif de SON PROPRE site Astro (SSR Node, reverse proxy, backend Convex) — en-têtes HTTP (CSP, HSTS…), TLS, fichiers exposés (.env, .git, source maps), secrets dans le JS livré, fonctions Convex publiques sans authentification, validation des entrées, XSS (set:html), dépendances vulnérables, configuration du serveur et du proxy, sauvegardes — avec correctifs. Utilise ce skill quand l'utilisateur demande si son site est sécurisé, veut un audit de sécurité, s'inquiète d'une fuite de clé ou d'un piratage, ou avant une mise en production. Uniquement sur un site dont l'utilisateur est propriétaire ou pour lequel il a une autorisation.
---

# Audit sécurité — Astro + Convex (défensif)

Scripts : `../audit-complet/scripts/` (sinon, même commande `find` que dans audit-complet §2). Format : `../audit-complet/references/format-constat.md`. Sortie : `rapports/securite.md`.

**Cadre** : uniquement le site et le serveur de l'utilisateur. Pas de force brute, pas d'exploitation, pas de scan de ports agressif, pas de charge. On observe, on lit la config et le code, on recommande. Si une faille est trouvée, on ne l'exploite pas pour la « prouver » : la preuve est la configuration ou le code.

## Données
`data/securite/security-probe.md`, `data/http/http-checks.md` (§3 en-têtes, §5 TLS), `data/code/code-scan.md` + `project-checks.md` (npm audit). Sinon :
```bash
bash $S/security_probe.sh https://site.fr/ "$AUDIT/data/securite"
```

## Checklist

### 1. Exposition publique (critiques en priorité)
- Fichiers sensibles accessibles (`security-probe.md`) : `.env`, `.git/`, sauvegardes, `package.json`, config. Un « ❌ EXPOSÉ » = critique : bloquer au proxy **et** considérer les secrets comme compromis (rotation).
- **Secrets dans le JS ou le HTML livrés** : motifs de clés détectés. Une vraie clé secrète côté client = critique → révoquer, régénérer, déplacer côté serveur.
- Variables non `PUBLIC_` utilisées dans du code client (code-scan) : fuite ou bug.
- Source maps publiques : code lisible (gravité faible sans secret, mais à désactiver en production).
- `/_image` avec une URL externe arbitraire doit être refusé (403). Sinon, c'est un proxy d'images ouvert : restreindre `image.remotePatterns`.
- Pages d'administration, de prévisualisation ou de debug : accessibles sans session ? Indexables ? (liens `?t=`, `/admin`, `/api/…`)

### 2. En-têtes et transport
- HSTS (`max-age` ≥ 1 an, `includeSubDomains` si tous les sous-domaines sont en https ; `preload` seulement en connaissance de cause), `X-Content-Type-Options: nosniff`, `Referrer-Policy`, `Permissions-Policy`, anti-clickjacking (`frame-ancestors` dans la CSP ou `X-Frame-Options`).
- **CSP** : présente ? `script-src` avec nonce/hash + `'strict-dynamic'` = très bien. `'unsafe-inline'` sans nonce ou `'unsafe-eval'` = faible. Astro ≥ 6 : `security.csp` (stable) génère une balise meta CSP avec les hashes des scripts et styles (`scriptDirective`, `styleDirective`, `directives`, `algorithm`). Si une CSP par nonce existe déjà via un middleware, ne pas en empiler une deuxième. Toute nouvelle CSP passe d'abord en `Content-Security-Policy-Report-Only`.
- **Host header derrière un proxy** : `security.allowedDomains` (≥ 5.14.2) protège contre l'injection d'en-tête `X-Forwarded-Host` et permet à `Astro.url` d'être juste. À configurer si le site est en rendu à la demande.
- **Secrets typés** : `env.schema` avec `envField.string({ context: 'server', access: 'secret' })` (`astro:env`, ≥ 5.0). Un secret importé côté client provoque alors une erreur de build au lieu d'une fuite.
- TLS 1.2+ seulement, certificat valide et renouvelé automatiquement, redirection http → https en 1 saut.
- En-têtes qui trahissent des versions (`Server: nginx/1.x`, `X-Powered-By`) → masquer.
- Cookies de session : `Secure`, `HttpOnly`, `SameSite=Lax` ou `Strict` (`curl -sI` sur une page qui pose un cookie ; ne rien afficher de sa valeur).

### 3. Backend Convex (le plus important sur ce type de stack)
Toute fonction publique est appelable directement avec le client Convex et l'URL du déploiement (visible dans le JS). Pour chaque mutation ou action publique listée par `astro_scan.py`, **lire le code** :
- qui a le droit de l'appeler ? L'identité (`ctx.auth.getUserIdentity()`) et le **rôle** sont-ils vérifiés côté serveur, pas seulement masqués dans l'interface ?
- les entrées sont-elles validées (`args` avec `v.*`, longueurs, formats) ? Un formulaire public (contact, lead) doit avoir une protection anti-abus : rate limiting (composant `@convex-dev/rate-limiter` ou logique maison), captcha ou honeypot ;
- les queries publiques renvoient-elles des champs sensibles (emails, téléphones, données d'autres utilisateurs) ?
- fonctions appelées seulement par le serveur ou des crons → `internal*` ;
- `convex/http.ts` : signatures des webhooks vérifiées, CORS restreint ;
- Convex auto-hébergé : dashboard et admin key non exposés publiquement, version à jour, sauvegardes (`npx convex export`) planifiées et testées.

### 4. Application Astro
- `set:html` / `dangerouslySetInnerHTML` avec du contenu CMS ou utilisateur → assainir côté serveur.
- Endpoints `src/pages/api/*` et Actions Astro : authentification, validation (zod), méthodes autorisées, `security.checkOrigin` actif.
- Redirections construites depuis un paramètre (`?next=`, `?redirect=`) → n'autoriser que des chemins internes (open redirect).
- Téléversement de fichiers : types et tailles contrôlés côté serveur.

### 5. Dépendances
`npm audit --omit=dev` (critiques et hautes), paquets abandonnés (aucune publication depuis plus de 2 ans) sur des fonctions sensibles, mises à jour de sécurité d'Astro et de l'adapter.

### 6. Serveur et proxy (si accès, en lecture)
- Processus Node lancé par un utilisateur dédié, pas root ; le port de l'app (ex. 4321) et celui de Convex ne sont exposés qu'au proxy (`ss -tlnp` : écoute sur 127.0.0.1 ou sur le réseau Docker interne, pas sur 0.0.0.0).
- Pare-feu (`ufw status` / `nft list ruleset`) : seuls 22, 80 et 443 ouverts ; SSH par clé, root login désactivé (`sshd -T | grep -E 'permitrootlogin|passwordauthentication'`).
- Mises à jour de sécurité de l'OS (`unattended-upgrades` ou équivalent) ; fail2ban ou équivalent.
- Fichiers `.env` du serveur : permissions 600, propriétaire l'utilisateur de l'app.
- **Sauvegardes** : base Convex + fichiers + config, hors du serveur, restauration déjà testée. Pas de sauvegarde = constat Haute.
- Supervision : alerte si le site tombe (uptime), logs d'erreurs consultables.

### 7. Hygiène du dépôt
`.env` dans `.gitignore`, aucun `.env` versionné (`git ls-files | grep -i '\.env'`), aucun secret dans l'historique (`git log -p -S 'sk_live' --all | head` ; si un secret apparaît : rotation obligatoire).

## Correctifs types

```nginx
# nginx — bloquer les fichiers cachés et les restes de build (dans le server{} du site)
location ~ /\.(?!well-known) { deny all; return 404; }
location ~* \.(map|sql|bak|zip)$ { deny all; return 404; }
server_tokens off;
```

```ts
// convex — mutation d'administration protégée
export const deleteLead = mutation({
  args: { id: v.id('leads') },
  handler: async (ctx, { id }) => {
    const identity = await ctx.auth.getUserIdentity();
    if (!identity) throw new ConvexError('Non authentifié');
    const user = await ctx.db.query('users').withIndex('by_token', q => q.eq('tokenIdentifier', identity.tokenIdentifier)).unique();
    if (user?.role !== 'admin') throw new ConvexError('Interdit');
    await ctx.db.delete(id);
  },
});
```
(Adapter à la table et au schéma d'authentification réels du projet.)

## Restitution
`rapports/securite.md` : synthèse (ce qui est bien fait compte aussi : le dire), puis les constats `SEC-NNN`. Jamais de valeur de secret dans le rapport, seulement le nom et l'emplacement.
