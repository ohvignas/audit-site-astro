---
id: secu-fichiers-caches-exposes
titre: "Fichiers cachés accessibles publiquement (.env, .git, .npmrc, .DS_Store)"
domaine: Sécurité
severite_type: critique
effort: S
declencheurs:
  - "securite:\\| /\\.env[\\w.]* \\| \\d+ \\| \\d+ \\| ❌ EXPOSÉ"
  - "securite:\\| /\\.git/(HEAD|config) \\| \\d+ \\| \\d+ \\| ❌ EXPOSÉ"
  - "securite:\\| /\\.npmrc \\| \\d+ \\| \\d+ \\| ❌ EXPOSÉ"
  - "securite:\\| /\\.DS_Store \\| \\d+ \\| \\d+ \\| ❌ EXPOSÉ"
sources:
  - https://owasp.org/www-project-web-security-testing-guide/latest/4-Web_Application_Security_Testing/02-Configuration_and_Deployment_Management_Testing/04-Review_Old_Backup_and_Unreferenced_Files_for_Sensitive_Information
  - https://nginx.org/en/docs/http/ngx_http_core_module.html#location
  - https://caddyserver.com/docs/caddyfile/matchers#path
  - https://docs.astro.build/en/guides/environment-variables/
---

# Fichiers cachés accessibles publiquement (.env, .git, .npmrc, .DS_Store)

> **En une phrase** : un fichier qui ne doit jamais quitter le serveur (secrets, historique du code, jeton npm) se télécharge avec une simple URL ; tout ce qu'il contient doit être considéré comme volé.

## Pourquoi c'est important

Des robots parcourent en permanence Internet à la recherche de `/.env` et de `/.git/`. Un `.env` public donne directement les clés d'API, mots de passe de base de données ou clés de déploiement (par exemple `CONVEX_DEPLOY_KEY`). Un dossier `.git/` public permet de reconstituer tout le dépôt, **historique compris**, donc aussi les secrets supprimés depuis. Un `.npmrc` peut contenir un jeton de publication de paquets. Le simple fait que le fichier ait été servi une fois suffit : il faut faire tourner les secrets (rotation), pas seulement bloquer l'URL.

## Comment le constater soi-même

```bash
for p in /.env /.env.local /.env.production /.git/HEAD /.git/config /.npmrc /.DS_Store; do
  printf '%s -> ' "$p"; curl -s -o /dev/null -w '%{http_code}\n' "https://exemple.fr$p"
done
# Contenu (sans l'afficher en entier ni le copier ailleurs) :
curl -s https://exemple.fr/.git/HEAD | head -1     # présent : "ref: refs/heads/main"
```

- Problème présent : code 200 et contenu réel (`ref: refs/`, lignes `NOM=valeur`). Attention : certains sites répondent 200 avec leur page d'accueil pour toute URL inconnue, ce n'est pas une fuite (la sonde de l'outil écarte ce cas).
- Corrigé : 404 (ou 403) sur tous ces chemins.

## Correction

1. **Traiter comme compromis** : notez les variables qui figuraient dans le fichier (noms seulement, jamais les valeurs dans un ticket ou un chat). Faites tourner chaque secret : voir la fiche `secu-secret-dans-js-client` (section « Rotation »). Pour `.git/`, faites tourner tout secret ayant existé un jour dans l'historique.
2. **Bloquer au serveur web** (correctif immédiat, avant de chercher la cause).

   nginx, dans le `server { }` du site :

   ```nginx
   # Tout fichier ou dossier caché, sauf /.well-known/ (Let's Encrypt, security.txt)
   location ~ /\.(?!well-known/) { return 404; }
   ```

   Caddy, dans le bloc du site (Caddy utilise des expressions RE2 sans « lookahead » : on exclut avec `not`) :

   ```caddy
   @masques {
       path /.*
       not path /.well-known/*
   }
   respond @masques 404
   ```

   Rechargez : `sudo nginx -t && sudo systemctl reload nginx` ou `caddy reload --config /etc/caddy/Caddyfile`.
3. **Corriger la cause**, sinon le problème reviendra :
   - Le serveur web pointe sur la racine du projet (`root /var/www/monsite;` où se trouve le dépôt). Il doit pointer sur `dist/client` (Astro en SSR avec `@astrojs/node`) ou `dist` (site statique). En SSR Node, mieux : `proxy_pass` / `reverse_proxy` vers `127.0.0.1:4321` et aucun `root`.
   - Un fichier sensible a été mis dans `public/` : tout ce qui est dans `public/` est publié tel quel. Déplacez-le hors du projet ou supprimez-le.
   - Image Docker construite avec `COPY . .` sans `.dockerignore` : créez `.dockerignore` avec `.env*`, `.git`, `.npmrc`, `node_modules`, puis reconstruisez.
   - `.DS_Store` : ajoutez-le à `.gitignore`, supprimez-le du dépôt (`git rm --cached .DS_Store`).
4. **Hygiène du dépôt** : `.env*` dans `.gitignore` (sauf `.env.example`), voir `secu-env-versionne-git`.
5. Faites relire les journaux d'accès du serveur pour les requêtes sur ces chemins (`grep -E '\.env|\.git/' /var/log/nginx/access.log`) : cela indique si une lecture a déjà eu lieu et depuis quand.

## Critères d'acceptation

- [ ] Les 7 URL ci-dessus répondent 404 ou 403.
- [ ] `/.well-known/security.txt` et le renouvellement de certificat fonctionnent encore.
- [ ] Tous les secrets qui étaient dans le fichier exposé ont été remplacés, les anciens révoqués.
- [ ] La cause (racine du serveur, `public/`, image Docker) est corrigée.
- [ ] Aucune régression : le site et ses assets (`/_astro/...`) répondent en 200.

## Vérification après correction

```bash
bash scripts/security_probe.sh https://exemple.fr/ /tmp/verif-secu
grep -E '\.env|\.git|\.npmrc|DS_Store' /tmp/verif-secu/security-probe.md
```

Aucune ligne ne doit contenir « ❌ EXPOSÉ ».

## Pièges et retour arrière

- Ne bloquez pas `/.well-known/` : le renouvellement des certificats Let's Encrypt (HTTP-01) et `security.txt` en dépendent.
- Bloquer l'URL sans faire tourner les secrets ne sert à rien si le fichier a déjà été lu.
- Retour arrière : retirer le bloc `location` / `@cache` puis recharger le serveur (déconseillé).
- Sauvegardez la configuration du serveur avant modification (`cp /etc/nginx/sites-available/site{,.bak}`) et testez avec `nginx -t`.

## Pour aller plus loin

- OWASP, revue des fichiers de sauvegarde et non référencés : méthode de détection des fichiers sensibles.
- nginx, directive `location` : expressions régulières et priorité.
- Caddy, matcher `path` : syntaxe des chemins.
- Astro, variables d'environnement : quelles variables restent côté serveur.
