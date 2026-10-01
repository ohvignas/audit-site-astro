---
id: serveur-dns-caa-dnssec-ipv6
titre: CAA, DNSSEC et IPv6 absents
domaine: Serveur / HTTP
severite_type: basse
effort: S
declencheurs:
  - "domaine:^(caa_absent|dnssec_absent|ipv6_absent)$"
sources:
  - https://www.rfc-editor.org/rfc/rfc8659
  - https://internet.nl/test-site/
  - https://developers.cloudflare.com/dns/dnssec/
---

# CAA, DNSSEC et IPv6 absents

> **En une phrase** : le domaine n'a ni enregistrement CAA, ni signature DNSSEC, ni adresse IPv6 : trois mesures de robustesse sans risque immédiat, mais mesurées par les outils de conformité.

## Pourquoi c'est important

Ce sont des bonus de robustesse, jamais une urgence : l'outil les classe en information. **CAA** restreint les autorités de certification autorisées à émettre un certificat pour le domaine (limite les certificats frauduleux). **DNSSEC** signe les réponses DNS pour empêcher leur falsification en route. **IPv6** rend le site joignable par les réseaux qui n'ont plus (ou peu) d'IPv4, sans passer par une traduction. internet.nl les mesure et pénalise leur absence dans le score d'un site.

DNSSEC est détecté par le bit AD (« données authentifiées ») d'un résolveur validant, lu sur le SOA du domaine et sur l'adresse du site ; CAA est cherché en remontant l'arbre depuis le nom du site (RFC 8659) ; IPv6 par la présence d'un enregistrement AAAA sur le nom du site.

## Comment le constater soi-même

```bash
curl -s -H 'accept: application/dns-json' 'https://cloudflare-dns.com/dns-query?name=DOMAINE&type=CAA'
curl -s -H 'accept: application/dns-json' 'https://cloudflare-dns.com/dns-query?name=SITE&type=AAAA'
curl -s -H 'accept: application/dns-json' 'https://cloudflare-dns.com/dns-query?name=DOMAINE&type=SOA' | grep -o '"AD":[a-z]*'
# ou : dig +short CAA DOMAINE ; dig +short AAAA SITE ; dig +dnssec SOA DOMAINE (drapeau « ad »)
```

Problème présent : pas de réponse de type CAA (257), pas de réponse AAAA (28), `"AD":false`. Corrigé : réponses présentes et `"AD":true`.

## Correction

Ces réglages se font chez le registrar, l'hébergeur DNS ou le CDN, pas dans le code d'Astro ni dans Convex.

1. **CAA** : ajouter un enregistrement par autorité réellement utilisée pour le certificat du site (Let's Encrypt, Google Trust Services, etc.) :

```text
exemple.fr.  CAA  0 issue "letsencrypt.org"
```

2. **DNSSEC** : l'activer chez l'hébergeur DNS (Cloudflare : un clic dans l'onglet DNS, puis recopier l'enregistrement DS chez le registrar du domaine). Le DS doit être publié chez le registrar pour que la chaîne de confiance soit complète.

3. **IPv6** : activer l'enregistrement AAAA chez l'hébergeur ou le CDN (Cloudflare : proxy activé = IPv6 automatique ; sinon ajouter l'AAAA avec l'adresse IPv6 du serveur, après avoir vérifié que le serveur web écoute bien en IPv6, par exemple `listen [::]:443 ssl;` dans nginx).

## Critères d'acceptation

- [ ] Un enregistrement CAA nomme l'autorité de certification en service (et celle de renouvellement)
- [ ] Le SOA du domaine répond `"AD":true` ; le DS est publié chez le registrar
- [ ] Le site répond en IPv4 et en IPv6 : `curl -4 -sI https://SITE/` et `curl -6 -sI https://SITE/` renvoient tous deux 200
- [ ] `caa_absent`, `dnssec_absent` et `ipv6_absent` absents de `data/domaine/issues.json`

## Vérification après correction

```bash
python3 scripts/domaine_check.py https://SITE/ --out /tmp/verif/domaine && cat /tmp/verif/domaine/domaine.md
curl -6 -sI https://SITE/ | head -1
```

internet.nl/test-site/ refait le contrôle complet (IPv6, DNSSEC, HTTPS, e-mail) ; les caches DNS peuvent retarder le résultat de quelques minutes à quelques heures.

## Pièges et retour arrière

- Un CAA qui ne nomme pas l'autorité de renouvellement bloque l'émission du certificat suivant : lister toutes les autorités utilisées (certificat du site, du CDN, de l'hébergeur de messagerie).
- Une mauvaise DS (ou un changement de fournisseur DNS sans transfert de la signature) rend le domaine injoignable pour les résolveurs validants : retour arrière en retirant la DS chez le registrar (le délai dépend du TTL de la DS).
- Une AAAA vers un serveur qui n'écoute pas en IPv6 casse le site pour les visiteurs IPv6 : tester avec `curl -6` avant de publier.
- Le résultat est « non vérifié » (⚠️) si les résolveurs DNS-over-HTTPS (Cloudflare, Google) ne répondent pas : relancer, ce n'est pas un défaut du site.

## Pour aller plus loin

- https://www.rfc-editor.org/rfc/rfc8659 : enregistrement CAA et remontée de l'arbre DNS.
- https://internet.nl/test-site/ : test public IPv6, DNSSEC et HTTPS d'un site.
- https://developers.cloudflare.com/dns/dnssec/ : activer DNSSEC et publier la DS chez le registrar.
