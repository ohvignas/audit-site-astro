---
id: secu-cle-google-publique
titre: "Clé Google (AIza…) visible dans le code client : à restreindre"
domaine: Sécurité
severite_type: basse
effort: S
declencheurs:
  - "securite:clé publique Google exposée"
sources:
  - https://cloud.google.com/docs/authentication/api-keys
  - https://firebase.google.com/docs/projects/api-keys
  - https://developers.google.com/maps/api-security-best-practices
---

# Clé Google (AIza…) visible dans le code client : à restreindre

> **En une phrase** : une clé Google `AIza…` dans le JavaScript est normale (Maps, Firebase, YouTube côté navigateur), mais sans restriction n'importe qui peut la réutiliser et vous faire payer.

## Pourquoi c'est important

Ces clés identifient votre projet, elles ne sont pas des secrets : le navigateur doit les connaître pour charger une carte ou initialiser Firebase. Il ne faut donc **pas** la révoquer par réflexe. Le risque est ailleurs : une clé sans restriction fonctionne depuis n'importe quel site et sur toutes les API activées du projet. Un tiers peut consommer votre quota ou votre budget (Maps facture à l'usage). Deux restrictions suffisent : le **référent HTTP** (votre domaine) et la liste des **API autorisées**.

## Comment le constater soi-même

```bash
# Repérer la clé dans la page (la valeur n'est volontairement pas recopiée)
curl -s https://exemple.fr/ | grep -aoE 'AIza[0-9A-Za-z_-]{35}' | sort -u | sed -E 's/(.{12}).*/\1…/'
```

Console Google Cloud, « API et services », « Identifiants », ouvrir la clé : présent si « Restrictions relatives aux applications » indique « Aucune » ou si « Restrictions relatives aux API » indique « Ne pas restreindre la clé ». Corrigé : référents HTTP renseignés et API listées une à une.

## Correction

1. Dans la console Google Cloud, ouvrir la clé et choisir **Sites web (référents HTTP)**. Ajouter `https://exemple.fr/*` et `https://www.exemple.fr/*` (un par ligne, ajouter les domaines de prévisualisation si besoin).
2. Dans « Restrictions relatives aux API », choisir **Restreindre la clé** et ne cocher que les API utilisées (par exemple Maps JavaScript API). Pour Firebase, suivre la page Firebase sur les clés d'API.
3. Si la clé est aussi utilisée côté serveur, **créer une seconde clé** restreinte par adresse IP, et ne jamais la mettre dans le code client (voir `secu-secret-dans-js-client`).
4. Configurer une alerte de budget et un quota journalier sur l'API concernée.

## Critères d'acceptation

- [ ] La clé a une restriction d'application (référents HTTP de vos domaines).
- [ ] La clé a une liste d'API autorisées, limitée à celles utilisées.
- [ ] Un appel avec la clé depuis un autre domaine est refusé.
- [ ] La carte ou le service Firebase du site fonctionne toujours.

## Vérification après correction

```bash
curl -s -o /dev/null -w '%{http_code}\n' -e https://autre-domaine.example/ "https://maps.googleapis.com/maps/api/staticmap?center=Paris&zoom=5&size=100x100&key=VOTRE_CLE"
bash scripts/security_probe.sh https://exemple.fr/ /tmp/verif-secu && sed -n '/Clés et secrets/,/Méthodes HTTP/p' /tmp/verif-secu/security-probe.md
```

La sonde signale encore la présence de la clé (c'est normal) ; la vérification utile est le refus depuis un autre référent.

## Pièges et retour arrière

- Une restriction trop stricte (domaine oublié, `www` manquant) casse la carte : testez sur le site réel après chaque changement.
- La propagation des restrictions peut prendre quelques minutes.
- Retour arrière : repasser la restriction à « Aucune » (déconseillé), jamais en supprimant la clé en production sans remplaçant.

## Pour aller plus loin

- Google Cloud, clés d'API : types de restrictions et bonnes pratiques.
- Firebase, clés d'API : pourquoi elles ne sont pas des secrets.
- Google Maps Platform : sécuriser ses clés.
