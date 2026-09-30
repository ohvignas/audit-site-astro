---
id: secu-tls-certificat
titre: "TLS obsolète (1.0/1.1 accepté) ou certificat proche de l'expiration"
domaine: Sécurité
severite_type: haute
effort: S
declencheurs:
  - "http:TLS 1\\.[01] : ⚠️ encore accepté"
  - "http:Expiration dans \\*\\*(-\\d+|\\d|[12]\\d) jours"
  - "http:TLS 1\\.2 : non accepté"
  - "http:certificat illisible"
  - "http:TLS non vérifié"      # audit lancé avec AUDIT_INSECURE_TLS=1 : le certificat n'a pas été contrôlé
sources:
  - https://nginx.org/en/docs/http/ngx_http_ssl_module.html#ssl_protocols
  - https://caddyserver.com/docs/caddyfile/directives/tls#protocols
  - https://caddyserver.com/docs/automatic-https
  - https://ssl-config.mozilla.org/
  - https://eff-certbot.readthedocs.io/en/stable/using.html#renewing-certificates
---

# TLS obsolète (1.0/1.1 accepté) ou certificat proche de l'expiration

> **En une phrase** : le serveur accepte encore des protocoles de chiffrement abandonnés depuis 2021, ou son certificat va expirer (auquel cas les navigateurs afficheront un écran d'alerte et le site sera inaccessible).

## Pourquoi c'est important

TLS 1.0 et 1.1 sont dépréciés (RFC 8996) : les navigateurs récents ne les utilisent plus, mais les laisser actifs expose à des attaques de rétrogradation et fait échouer les audits de conformité. Un **certificat expiré** est plus brutal : le navigateur bloque l'accès (« Votre connexion n'est pas privée »), Google peut ne plus explorer le site et les formulaires s'arrêtent. Le renouvellement doit être automatique ; un délai de moins de 30 jours restants signale qu'il ne l'est pas.

## Comment le constater soi-même

```bash
# Date d'expiration et émetteur
echo | openssl s_client -servername exemple.fr -connect exemple.fr:443 2>/dev/null | openssl x509 -noout -enddate -issuer
# Protocoles acceptés (les anciens OpenSSL/curl peuvent refuser de tester 1.0/1.1 : utiliser nmap ou testssl.sh si disponible)
curl -sv --tlsv1.1 --tls-max 1.1 https://exemple.fr/ -o /dev/null 2>&1 | grep -iE 'SSL connection|alert|error'
nmap --script ssl-enum-ciphers -p 443 exemple.fr | grep -E 'TLSv'
```

Problème présent : TLSv1.0 / TLSv1.1 listés, ou `notAfter` à moins de 30 jours. Corrigé : seuls TLSv1.2 et TLSv1.3, expiration à plus de 30 jours et renouvellement automatique actif. Un « TLS 1.2 : non accepté » dans le rapport est en revanche un vrai problème de compatibilité (serveur limité à 1.3, ou curl sans support).

## Correction

### Protocoles

1. **nginx** : dans le `server` en 443 (ou le contexte `http`).

   ```nginx
   ssl_protocols TLSv1.2 TLSv1.3;
   ssl_prefer_server_ciphers off;
   ```

   Pour la liste de suites de chiffrement, utilisez le profil « Intermediate » du générateur de configuration Mozilla plutôt qu'une liste écrite à la main. Rechargez : `sudo nginx -t && sudo systemctl reload nginx`. Vérifiez qu'aucun autre fichier (`/etc/nginx/conf.d/`, `options-ssl-nginx.conf` de Certbot) ne redéclare `ssl_protocols` avec TLSv1 / TLSv1.1.
2. **Caddy** : par défaut il n'accepte que TLS 1.2 et 1.3. Si votre Caddyfile contient une directive `protocols` ou un bloc `tls` personnalisé, remplacez-la ou supprimez-la.

   ```caddy
   exemple.fr {
       tls {
           protocols tls1.2 tls1.3
       }
       reverse_proxy 127.0.0.1:4321
   }
   ```
3. **CDN / hébergeur** (Cloudflare, Netlify, Vercel) : version minimale de TLS réglable dans le tableau de bord (Cloudflare : « Minimum TLS Version » = 1.2).

### Certificat

4. Vérifier le **renouvellement automatique**.
   - Caddy : automatique (ports 80 et 443 joignables depuis Internet). Regardez les journaux : `journalctl -u caddy | grep -i -E 'certificate|renew|error'`.
   - Certbot : `systemctl list-timers | grep certbot` (une minuterie doit exister), puis test à blanc `sudo certbot renew --dry-run`. En cas d'échec : port 80 bloqué, nom de domaine qui ne pointe plus vers le serveur, règle de blocage qui inclut `/.well-known/` (voir `secu-fichiers-caches-exposes`).
   - Certificat acheté manuellement : remplacez par Let's Encrypt (gratuit et automatique) ou mettez un rappel de calendrier à 45 jours de l'échéance.
5. **Certificat déjà expiré** : `sudo certbot renew --force-renewal` puis rechargement de nginx ; sous Caddy, `sudo systemctl restart caddy` après avoir corrigé la cause.
6. Ajoutez une **alerte d'expiration** (supervision, ou un contrôle planifié avec `echo | openssl s_client -servername exemple.fr -connect exemple.fr:443 2>/dev/null | openssl x509 -noout -checkend 2592000` qui retourne un code d'erreur si l'échéance est dans moins de 30 jours).

## Critères d'acceptation

- [ ] TLS 1.0 et 1.1 refusés ; TLS 1.2 et 1.3 acceptés.
- [ ] Certificat valide plus de 30 jours, chaîne complète, renouvellement automatique testé (`--dry-run` OK).
- [ ] Le site s'ouvre correctement en https depuis un navigateur récent et un mobile.

## Vérification après correction

```bash
echo | openssl s_client -servername exemple.fr -connect exemple.fr:443 2>/dev/null | openssl x509 -noout -enddate
bash scripts/http_checks.sh https://exemple.fr/ /tmp/verif-http && sed -n '/TLS \/ certificat/,/Fichiers techniques/p' /tmp/verif-http/http-checks.md
```

## Pièges et retour arrière

- Retirer TLS 1.0/1.1 coupe de très vieux appareils (Android < 5, Windows XP) : c'est voulu.
- Une intégration ancienne (imprimante, application métier) qui appelle votre site peut dépendre de TLS 1.0 : testez avant de couper.
- Sauvegardez la configuration avant de modifier (`cp -r /etc/nginx /etc/nginx.bak`).
- Retour arrière : restaurer la sauvegarde ; ne réactivez jamais TLS 1.0/1.1 durablement.

## Pour aller plus loin

- nginx `ssl_protocols` : liste des protocoles.
- Caddy `tls` (sous-directive `protocols`) et HTTPS automatique.
- Générateur de configuration TLS de Mozilla : profils Modern, Intermediate.
- Certbot : renouvellement des certificats.
