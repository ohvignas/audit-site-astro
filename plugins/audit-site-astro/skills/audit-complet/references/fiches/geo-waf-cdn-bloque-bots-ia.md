---
id: geo-waf-cdn-bloque-bots-ia
titre: Le pare-feu ou le CDN bloque des user-agents de robots IA (403, 429, challenge)
domaine: GEO / IA
severite_type: haute
effort: M
declencheurs:
  - "geo:\\(WAF/CDN \\? — à confirmer dans les logs"
sources:
  - https://developers.cloudflare.com/ai-crawl-control/features/manage-ai-crawlers/
  - https://developers.openai.com/api/docs/bots
  - https://docs.perplexity.ai/guides/bots
  - https://support.claude.com/en/articles/8896518-does-anthropic-crawl-data-from-the-web-and-how-can-site-owners-block-the-crawler
  - https://nginx.org/en/docs/http/ngx_http_map_module.html
  - https://caddyserver.com/docs/caddyfile/matchers
---

# Le pare-feu ou le CDN bloque des user-agents de robots IA

> **En une phrase** : même si `robots.txt` les autorise, des robots IA reçoivent une erreur (403, 429, 503) ou une page de vérification de la part du pare-feu, du CDN ou du serveur, et ne peuvent donc pas lire le site.

## Pourquoi c'est important

Un robot bloqué à ce niveau ne voit jamais le contenu : l'assistant correspondant ne peut ni l'indexer ni le citer, sans que rien n'apparaisse dans les outils SEO classiques. Cause n°1 : Cloudflare (réglage « Block AI bots » / **AI Crawl Control**), souvent actif par défaut sur les domaines récents, ou une règle de sécurité de l'hébergeur (Sucuri, Wordfence, ModSecurity), ou une règle maison (fail2ban, `if ($http_user_agent ~ …)` dans nginx, middleware). L'outil teste avec les user-agents publics des robots **depuis une IP quelconque** : un pare-feu qui bloque les « faux bots » (UA IA sans IP officielle) est un comportement normal. Il faut donc confirmer avec les logs si les **vrais** robots passent avant de conclure.

## Comment le constater soi-même

```bash
# Référence navigateur vs user-agents IA (adapter l'URL)
for ua in "Mozilla/5.0" \
  "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko); compatible; OAI-SearchBot/1.0; +https://openai.com/searchbot" \
  "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko); compatible; PerplexityBot/1.0; +https://perplexity.ai/perplexitybot" \
  "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; Claude-SearchBot/1.0; +Claude-SearchBot@anthropic.com)"; do
  printf '%s -> ' "${ua:0:60}"; curl -s -o /dev/null -w '%{http_code} %{size_download}\n' -A "$ua" https://SITE/
done

# Qui répond ? (en-têtes révélateurs)
curl -sI -A "PerplexityBot/1.0" https://SITE/ | grep -iE '^(HTTP|server|cf-mitigated|cf-ray|x-sucuri|x-powered)'
```

Présent : `403`, `429`, `503` ou une taille très inférieure à celle du navigateur ; `cf-mitigated: challenge` = Cloudflare ; `server: cloudflare` + `cf-ray` = le trafic passe par Cloudflare. Corrigé : `200` et une taille comparable.

Confirmer dans les logs (accès serveur) ce que reçoivent les vrais robots :

```bash
zgrep -hi 'oai-searchbot\|perplexitybot\|claude-searchbot\|gptbot' /var/log/nginx/access.log* | awk '{print $9}' | sort | uniq -c
```

Des `200` sur les vrais robots + `403` sur l'outil = pas de problème réel. Des `403`/`429` sur les vrais robots = à corriger. Aucun log de ces robots = ils ne viennent pas (ou sont arrêtés en amont, au CDN).

## Correction

1. **Sauvegarde** : exporter la configuration actuelle du pare-feu/CDN (capture des règles, ou copie du fichier de conf) avant de changer quoi que ce soit.
2. **Cloudflare** : dans le tableau de bord du domaine, ouvrir **AI Crawl Control**, onglet des crawlers. Autoriser les crawlers de recherche/citation souhaités (OAI-SearchBot, PerplexityBot, Claude-SearchBot, et les robots à la demande ChatGPT-User, Perplexity-User, Claude-User) ; garder « bloquer » pour les robots d'entraînement si tel est le choix (fiche `geo-robots-bots-entrainement`). Les blocages créent des règles WAF personnalisées que l'on peut affiner dans la section WAF. Vérifier aussi la fonction « Block AI bots » du domaine et les règles de Bot Fight Mode. L'interface évolue : la documentation Cloudflare fait foi.
3. **Autres pare-feu / hébergeur** : ajouter une exception pour ces user-agents **et** leurs IP officielles (listes JSON publiées : `https://openai.com/searchbot.json`, `https://openai.com/chatgpt-user.json`, `https://www.perplexity.com/perplexitybot.json`, `https://www.perplexity.com/perplexity-user.json`, `https://claude.com/crawling/bots.json`). Ne pas autoriser un UA seul sans IP : n'importe qui peut le falsifier.
4. **nginx / Caddy / code maison** : chercher une règle de blocage par user-agent.

```bash
grep -rniE 'gptbot|oai-searchbot|claudebot|perplexity|bytespider|\$http_user_agent|header_regexp|user-agent' /etc/nginx /etc/caddy Caddyfile 2>/dev/null
grep -rniE "user-agent|userAgent" src/middleware* 2>/dev/null
```

   Retirer ou restreindre la règle qui vise les robots de recherche. Exemple nginx qui ne bloque que des robots d'entraînement précis et laisse les autres passer :

```nginx
# http { ... }
map $http_user_agent $bloque_entrainement {
    default 0;
    ~*(GPTBot|ClaudeBot|CCBot|Bytespider|Meta-ExternalAgent) 1;
}
# server { ... }
if ($bloque_entrainement) { return 403; }
```

5. Faire appliquer les règles par l'humain (changement de CDN ou de pare-feu : c'est lui qui le fait), patienter quelques minutes (propagation des règles), puis relancer le test.

## Critères d'acceptation

- [ ] Les user-agents OAI-SearchBot, PerplexityBot, Claude-SearchBot (et à la demande) reçoivent `200` avec un corps de taille comparable au navigateur
- [ ] Les logs montrent des `200` pour les vrais robots (ou l'absence de blocage est attestée côté CDN)
- [ ] Le choix concernant l'entraînement reste appliqué
- [ ] Aucune régression : le site reste protégé contre les vrais abus (pas de règle de sécurité globale désactivée)

## Vérification après correction

```bash
python3 scripts/geo_check.py https://SITE/ --out /tmp/verif/geo --sample 3
grep -A25 'Réponse réelle' /tmp/verif/geo/geo-summary.md
```

Attendu : colonne « Signal » à « — » pour chaque robot de recherche.

## Pièges et retour arrière

- Un signal sur un robot d'**entraînement** (GPTBot, ClaudeBot, CCBot, Bytespider…) est normal si le propriétaire a choisi de les bloquer : ne rien corriger dans ce cas.
- Un signal sur un robot d'**entraînement** (GPTBot, ClaudeBot, CCBot, Bytespider…) est normal si le propriétaire a choisi de les bloquer : ne rien corriger dans ce cas.
- Ne jamais désactiver entièrement le pare-feu ou le mode « Under Attack » pour résoudre ce point : faire une exception ciblée.
- Un blocage des robots d'entraînement dans Cloudflare peut aussi affecter des robots « multi-usages » (Googlebot, Bingbot, Applebot) selon la configuration : tester après changement.
- Retour arrière : réimporter la configuration sauvegardée ou désactiver la règle ajoutée.

## Pour aller plus loin

- https://developers.cloudflare.com/ai-crawl-control/features/manage-ai-crawlers/ : autoriser ou bloquer chaque crawler.
- https://developers.openai.com/api/docs/bots : listes d'IP et rôle de chaque robot OpenAI.
- https://docs.perplexity.ai/guides/bots : règles WAF conseillées (UA + IP).
- https://support.claude.com/en/articles/8896518-does-anthropic-crawl-data-from-the-web-and-how-can-site-owners-block-the-crawler : robots d'Anthropic.
- https://nginx.org/en/docs/http/ngx_http_map_module.html et https://caddyserver.com/docs/caddyfile/matchers : `map` nginx et matchers Caddy.
