---
id: secu-sauvegardes-dumps-exposes
titre: "Sauvegardes, dumps de base de données ou archives accessibles publiquement"
domaine: Sécurité
severite_type: critique
effort: S
declencheurs:
  - "securite:\\| /(backup\\.zip|backup\\.sql|dump\\.sql|db\\.sqlite) \\| \\d+ \\| \\d+ \\| (❌ EXPOSÉ|⚠️ répond 200)"
sources:
  - https://owasp.org/www-project-web-security-testing-guide/latest/4-Web_Application_Security_Testing/02-Configuration_and_Deployment_Management_Testing/04-Review_Old_Backup_and_Unreferenced_Files_for_Sensitive_Information
  - https://www.cnil.fr/fr/notifier-une-violation-de-donnees-personnelles
  - https://nginx.org/en/docs/http/ngx_http_core_module.html#location
---

# Sauvegardes, dumps de base de données ou archives accessibles publiquement

> **En une phrase** : une sauvegarde (`backup.zip`, `dump.sql`, `db.sqlite`) est téléchargeable par n'importe qui, avec toutes les données qu'elle contient.

## Pourquoi c'est important

Une sauvegarde contient en général la totalité de la base : contacts, messages, mots de passe hachés, parfois des données personnelles de clients. Si elle est publique, c'est une **violation de données** au sens du RGPD, qui impose dans certains cas une notification à la CNIL sous 72 heures (à évaluer avec la personne chargée des données personnelles ou un juriste). C'est aussi la cible favorite des robots, qui testent ces noms de fichiers par défaut.

## Comment le constater soi-même

```bash
for p in /backup.zip /backup.sql /dump.sql /db.sqlite; do
  printf '%s -> ' "$p"; curl -s -o /dev/null -I -w '%{http_code} %{content_type} %{size_download}\n' "https://exemple.fr$p"
done
```

Présent : 200 (ou 206) et un type `application/zip`, `application/x-sql`, `application/octet-stream`. Corrigé : 404. Ne téléchargez pas le fichier en entier, l'en-tête suffit ; ne le conservez pas.

## Correction

1. **Retirer le fichier immédiatement** du dossier servi (`rm` après en avoir mis une copie en lieu sûr **hors** du serveur web si c'est la seule sauvegarde).
2. **Bloquer les extensions de sauvegarde** au serveur web.

   ```nginx
   location ~* \.(sql|sqlite3?|db|bak|old|orig|swp|zip|tar|tar\.gz|tgz|7z|rar)$ { return 404; }
   ```

   ```caddy
   @sauvegardes path_regexp sauv (?i)\.(sql|sqlite3?|db|bak|old|orig|swp|zip|tar|tgz|gz|7z|rar)$
   respond @sauvegardes 404
   ```

   Attention : si votre site distribue légitimement des `.zip` (ressources à télécharger), placez-les sous un dossier dédié et excluez ce dossier de la règle.
3. **Évaluer l'impact** : qu'y avait-il dans le fichier, depuis quand était-il en ligne (date de modification du fichier, journaux d'accès `grep 'backup' /var/log/nginx/access.log`) ? Faites tourner les secrets contenus (jetons, clés) et, si des mots de passe d'utilisateurs y figuraient, imposez leur réinitialisation.
4. **Décider de la notification** : informez le responsable des données ; en cas de données personnelles exposées, la CNIL indique la procédure de notification.
5. **Mettre les sauvegardes au bon endroit** : en dehors de la racine web, chiffrées, sur un stockage distinct. Pour Convex : `npx convex export --path ./sauvegardes/` depuis un poste ou une tâche planifiée qui envoie l'archive vers un stockage privé, jamais dans `public/`.
6. Supprimez les fichiers de ce type de `public/` et ajoutez-les à `.gitignore` (`*.sql`, `*.sqlite`, `*.zip`).

## Critères d'acceptation

- [ ] Les 4 URL répondent 404.
- [ ] Aucune archive ni dump dans `public/`, `dist/` ou la racine web (`find dist public -name '*.sql' -o -name '*.zip' -o -name '*.sqlite'`).
- [ ] Les secrets présents dans la sauvegarde ont été renouvelés ; la décision de notification est documentée.
- [ ] Les sauvegardes sont stockées hors du serveur web.

## Vérification après correction

```bash
bash scripts/security_probe.sh https://exemple.fr/ /tmp/verif-secu
grep -E 'backup|dump|sqlite' /tmp/verif-secu/security-probe.md
```

## Pièges et retour arrière

- Ne supprimez pas la seule copie de vos données : déplacez-la d'abord.
- Une règle sur `.zip` peut bloquer des téléchargements légitimes ; testez les liens de téléchargement du site.
- Retour arrière : retirer le bloc `location` / `@sauvegardes` puis recharger (déconseillé).

## Pour aller plus loin

- OWASP : recherche de fichiers de sauvegarde oubliés.
- CNIL : notifier une violation de données personnelles.
- nginx `location` : filtres par extension.
