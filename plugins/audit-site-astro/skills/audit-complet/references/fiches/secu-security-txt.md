---
id: secu-security-txt
titre: "Pas de fichier security.txt pour signaler une faille"
domaine: Sécurité
severite_type: basse
effort: S
declencheurs:
  - "securite:\\| /\\.well-known/security\\.txt \\| (404|403|410) \\|"
  - "http:\\| /\\.well-known/security\\.txt \\| (404|403|410) \\|"
sources:
  - https://www.rfc-editor.org/rfc/rfc9116
  - https://securitytxt.org/
  - https://docs.astro.build/en/basics/project-structure/#public
---

# Pas de fichier security.txt pour signaler une faille

> **En une phrase** : personne ne sait à qui écrire pour vous prévenir d'une faille de sécurité, faute de fichier `/.well-known/security.txt`.

## Pourquoi c'est important

Quand un chercheur ou un visiteur découvre un problème, il cherche un contact sécurité. Le standard RFC 9116 prévoit un petit fichier texte à un emplacement connu. Sans lui, l'alerte se perd ou part sur un réseau social. Le coût est de quelques minutes ; le bénéfice est d'être prévenu avant qu'une faille soit exploitée. Ce n'est pas une obligation légale, c'est une bonne pratique (gravité basse).

## Comment le constater soi-même

```bash
curl -s -o /dev/null -w '%{http_code}\n' https://exemple.fr/.well-known/security.txt
curl -s https://exemple.fr/.well-known/security.txt
```

Absent : 404. Correct : 200, `Content-Type: text/plain`, avec au minimum les lignes `Contact:` et `Expires:`.

## Correction

1. Créez `public/.well-known/security.txt` (Astro copie `public/` tel quel dans le site publié, y compris ce dossier caché).

   ```text
   Contact: mailto:securite@exemple.fr
   Expires: 2027-12-31T23:59:59.000Z
   Preferred-Languages: fr, en
   Canonical: https://exemple.fr/.well-known/security.txt
   Policy: https://exemple.fr/politique-securite
   ```

   - `Contact` et `Expires` sont obligatoires (RFC 9116). `Contact` peut être un `mailto:` ou une URL de formulaire. Utilisez une adresse qui existe et qui est lue.
   - `Expires` : date au format ISO 8601 / RFC 3339, recommandée à moins d'un an dans le futur. Mettez un rappel dans votre calendrier pour la renouveler.
   - `Policy` et `Canonical` sont facultatifs : supprimez les lignes dont vous n'avez pas besoin (une `Policy` doit pointer vers une vraie page).
2. Si votre règle de blocage des fichiers cachés (`location ~ /\.` dans nginx) est en place, elle doit **exclure** `/.well-known/` (voir `secu-fichiers-caches-exposes`).
3. Pour un site en SSR sans dossier `public/` servi par le proxy, vérifiez que Node sert bien `dist/client/.well-known/security.txt` après `npm run build`.

## Critères d'acceptation

- [ ] `https://exemple.fr/.well-known/security.txt` répond 200 en texte brut.
- [ ] `Contact:` et `Expires:` (date future) sont présents.
- [ ] L'adresse de contact reçoit bien les messages (test d'envoi).

## Vérification après correction

```bash
curl -sI https://exemple.fr/.well-known/security.txt | grep -iE '^(HTTP|content-type)'
bash scripts/http_checks.sh https://exemple.fr/ /tmp/verif && grep security.txt /tmp/verif/http-checks.md
```

## Pièges et retour arrière

- Un fichier périmé (`Expires` passé) est traité comme absent : planifiez le renouvellement.
- Les fichiers commençant par un point sont parfois ignorés par des scripts de déploiement (`rsync` avec exclusions, `.gitignore` global) : vérifiez que le fichier est bien versionné et déployé.
- Retour arrière : supprimer le fichier.

## Pour aller plus loin

- RFC 9116 : champs, emplacement, durée de validité.
- securitytxt.org : générateur de fichier.
- Astro, dossier `public/` : fichiers copiés tels quels.
