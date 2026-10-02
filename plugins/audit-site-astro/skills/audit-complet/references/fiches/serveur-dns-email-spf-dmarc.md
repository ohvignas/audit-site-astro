---
id: serveur-dns-email-spf-dmarc
titre: SPF et DMARC absents, permissifs ou mal formés
domaine: Sécurité
severite_type: moyenne
effort: S
declencheurs:
  - "domaine:^(spf_absent|spf_multiple|spf_permissif|spf_trop_de_requetes|dmarc_absent|dmarc_none)$"
sources:
  - https://www.rfc-editor.org/rfc/rfc7208
  - https://www.rfc-editor.org/rfc/rfc7489
  - https://internet.nl/test-mail/
---

# SPF et DMARC absents, permissifs ou mal formés

> **En une phrase** : sans SPF strict ni DMARC, n'importe qui peut envoyer des e-mails au nom du domaine du site (hameçonnage, spam) et les vrais e-mails du site risquent d'atterrir en courrier indésirable.

## Pourquoi c'est important

SPF liste les serveurs autorisés à envoyer du courrier pour le domaine ; DMARC dit aux destinataires quoi faire des messages qui échouent à SPF et à DKIM, et où envoyer les rapports. Sans eux, un tiers peut usurper le domaine (hameçonnage de vos clients, atteinte à la réputation) et les e-mails légitimes du site (formulaire de contact, confirmations, devis) sont jugés moins fiables. Gmail et Yahoo exigent SPF, DKIM et DMARC des expéditeurs de plus de 5 000 messages par jour depuis 2024 ; les petits expéditeurs y gagnent aussi en délivrabilité.

L'outil règle la gravité selon le courrier réellement géré par le domaine :

- **SPF `+all`** (ou `all` nu) : n'importe quel serveur est autorisé, l'usurpation est ouverte (haute) ; `?all` : aucune protection (basse). Seul le premier mécanisme `all` compte (RFC 7208 §5.1 : `-all +all` est un `-all`) ; un `+all` hérité d'un `include:` ou d'un `redirect=` est détecté de la même façon.
- **SPF multiple** (plusieurs enregistrements `v=spf1`) ou **plus de 10 requêtes DNS** : le SPF est invalide (erreur permanente, RFC 7208), les destinataires l'ignorent (moyenne).
- **DMARC absent** : moyenne si le domaine reçoit des e-mails (enregistrement MX non nul), basse sinon (durcissement recommandé : un domaine sans e-mail devrait publier `v=spf1 -all` et `p=reject`).
- **SPF absent** : moyenne si le domaine reçoit des e-mails (MX non nul), basse sinon (même règle que DMARC). **DMARC en `p=none`** : info (surveillance seule, étape normale d'un déploiement). Un DMARC sans `p=` valide est signalé « invalide » (les destinataires l'ignorent).

Le domaine contrôlé est le domaine enregistrable de la Public Suffix List (`www.exemple.fr` et `beta.exemple.fr` donnent `exemple.fr` ; `www.exemple.co.uk` donne `exemple.co.uk`). DMARC est cherché sur le nom exact du site, puis sur ses ancêtres jusqu'au domaine enregistrable ; la politique `sp=` prime pour les sous-domaines quand l'enregistrement est publié sur un ancêtre. DKIM n'est pas testé (le sélecteur est inconnu : vérifier chez le fournisseur d'envoi).

**Site hébergé sur un sous-domaine de plateforme** (`monsite.github.io`, `monsite.vercel.app`, `monsite.netlify.app`, `monsite.pages.dev`, `monsite.herokuapp.com`…) : SPF, DMARC, CAA et DNSSEC appartiennent à la plateforme, pas au propriétaire du site. L'outil n'émet alors aucun constat (statut « plateforme partagée ») ; ces contrôles ne s'appliquent qu'avec un domaine personnalisé.

## Comment le constater soi-même

```bash
curl -s -H 'accept: application/dns-json' 'https://cloudflare-dns.com/dns-query?name=DOMAINE&type=TXT'
curl -s -H 'accept: application/dns-json' 'https://cloudflare-dns.com/dns-query?name=_dmarc.DOMAINE&type=TXT'
curl -s -H 'accept: application/dns-json' 'https://cloudflare-dns.com/dns-query?name=DOMAINE&type=MX'
# ou : dig +short TXT DOMAINE ; dig +short TXT _dmarc.DOMAINE ; dig +short MX DOMAINE
```

Problème présent : aucune réponse commençant par `v=spf1` (ou plusieurs, ou fin en `+all`), aucune réponse commençant par `v=DMARC1` sur `_dmarc`. Corrigé : un seul `v=spf1 … -all` et un `v=DMARC1; p=…`.

## Correction

Ces enregistrements se modifient dans la zone DNS du domaine (registrar, Cloudflare, OVH, Gandi…), pas dans le code d'Astro ni dans Convex.

1. **SPF : un seul enregistrement TXT** sur le domaine, listant chaque service qui envoie du courrier (hébergeur de messagerie, Brevo, Resend…) et se terminant par `-all` :

```text
exemple.fr.  TXT  "v=spf1 include:<fournisseur-1> include:<fournisseur-2> -all"
```

   Domaine sans e-mail (aucun MX, aucun envoi) : `"v=spf1 -all"` et un MX nul `0 .` (RFC 7505).

2. **DMARC : déployer par paliers** sur `_dmarc.exemple.fr` :

```text
_dmarc.exemple.fr.  TXT  "v=DMARC1; p=none; rua=mailto:dmarc@exemple.fr"
```

   Lire les rapports agrégés quelques semaines, corriger les expéditeurs oubliés, puis passer à `p=quarantine`, puis à `p=reject`. Domaine sans e-mail : `"v=DMARC1; p=reject"` directement.

3. **Mécanisme `ptr`** : déprécié (RFC 7208 §5.5), à retirer : lent, peu fiable et coûteux en requêtes DNS.

4. **Plus de 10 requêtes DNS** : retirer les services inutilisés, remplacer les `include:` redondants par les adresses `ip4:`/`ip6:` fixes, ou faire aplatir le SPF par le fournisseur d'envoi. Ne jamais publier deux enregistrements SPF : les fusionner en un seul.

## Critères d'acceptation

- [ ] Un seul enregistrement `v=spf1` sur le domaine, terminé par `-all` (ou `~all` le temps d'un déploiement), sans `+all` ni `?all`, 10 requêtes DNS au plus
- [ ] Un enregistrement `v=DMARC1` sur `_dmarc` (ou hérité du domaine organisationnel), avec `p=quarantine` ou `p=reject` à terme
- [ ] `spf_*` et `dmarc_absent` absents de `data/domaine/issues.json`
- [ ] E-mails transactionnels du site toujours délivrés (`Authentication-Results: spf=pass dmarc=pass` dans l'en-tête d'un message de test)

## Vérification après correction

```bash
python3 scripts/domaine_check.py https://SITE/ --out /tmp/verif/domaine && cat /tmp/verif/domaine/domaine.md
```

Puis envoyer un message de test depuis le site vers une boîte Gmail et lire « Afficher l'original » : `SPF: PASS`, `DKIM: PASS`, `DMARC: PASS`. Les changements DNS se propagent selon le TTL (souvent quelques minutes à quelques heures).

## Pièges et retour arrière

- Passer directement en `p=reject` bloque les envois oubliés (outil de facturation, newsletter, CRM) : toujours commencer par `p=none` et lire les rapports.
- Un SPF en `-all` sans le service d'envoi du site fait rejeter les e-mails du formulaire de contact : lister tous les expéditeurs avant de durcir.
- Retour arrière : revenir à `p=none` pour DMARC et à `~all` pour SPF ; un TTL court (300 s) avant l'intervention accélère le retour.
- Le résultat est « non vérifié » (⚠️) si les résolveurs DNS-over-HTTPS (Cloudflare, Google) ne répondent pas : relancer, ce n'est pas un défaut du site.

## Pour aller plus loin

- https://www.rfc-editor.org/rfc/rfc7208 : SPF (limite de 10 requêtes DNS au §4.6.4).
- https://www.rfc-editor.org/rfc/rfc7489 : DMARC (recherche de l'enregistrement et domaine organisationnel).
- https://internet.nl/test-mail/ : test public de la configuration e-mail d'un domaine.
