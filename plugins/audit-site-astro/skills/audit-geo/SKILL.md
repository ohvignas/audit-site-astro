---
name: audit-geo
description: Audit GEO (Generative Engine Optimization) — visibilité et citations d'un site dans ChatGPT, Perplexity, Claude, Gemini, Copilot, Google AI Overviews / AI Mode — accès des robots IA (robots.txt, WAF, Cloudflare), llms.txt, entités et données structurées (Organization, sameAs, auteurs), contenu « citable », signaux de confiance, présence hors site, logs des bots IA et trafic référent IA, protocole de test manuel. Utilise ce skill dès que l'utilisateur parle de GEO, AEO, LLMO, de référencement dans les IA, de ChatGPT/Perplexity qui ne citent pas son site, d'AI Overviews, de llms.txt ou de robots IA (GPTBot, ClaudeBot…), même s'il dit juste « être visible dans l'IA ».
---

# Audit GEO — visibilité dans les moteurs IA

Scripts : `../audit-complet/scripts/`. Format : `../audit-complet/references/format-constat.md`. Sortie : `rapports/geo.md`.

## Ce qu'on sait (et ce qu'on ne sait pas)
Les assistants IA citent des pages qu'ils peuvent **récupérer** (robots, serveur), **comprendre** (texte présent dans le HTML sans JS, structure claire) et **juger fiables** (entité identifiable, preuves, mentions ailleurs sur le web). La plupart s'appuient sur un index de recherche : Google pour AI Overviews et AI Mode, Bing pour Copilot et une partie des autres assistants, plus leurs propres index (OAI-SearchBot, PerplexityBot, Claude-SearchBot). **Bien référencé en SEO classique = base du GEO.** Rester honnête dans le rapport : les effets de llms.txt ou du balisage FAQ sur les citations ne sont pas démontrés. Les présenter comme des paris à faible coût, pas comme des leviers garantis.

## Données
`data/geo/geo.json` + `geo-summary.md`, `data/crawl/pages.json`. Sinon :
```bash
python3 $S/geo_check.py https://site.fr/ --out "$AUDIT/data/geo" --crawl "$AUDIT/data/crawl/pages.json" --sample 12
```

## Checklist

### 1. Accès des robots (bloquant si raté)
- **robots.txt par robot** (tableau du rapport). Distinguer :
  - robots de **recherche et citation** (OAI-SearchBot, ChatGPT-User, PerplexityBot, Perplexity-User, Claude-SearchBot, Claude-User, Googlebot, Bingbot, Applebot, DuckAssistBot, MistralAI-User) → à **autoriser** pour être cité ;
  - robots d'**entraînement** (GPTBot, ClaudeBot, Google-Extended, Applebot-Extended, CCBot, Meta-ExternalAgent, Bytespider) → choix business. Les bloquer n'empêche pas d'être cité par la recherche en direct. Présenter le choix à l'utilisateur sans le trancher à sa place.
- **Réponse réelle** : un 403, 429 ou une page de challenge pour un user-agent IA = blocage par le WAF/CDN (Cloudflare « Block AI bots » / AI Crawl Control, souvent activé par défaut sur les nouveaux domaines ; règles de sécurité de l'hébergeur ; fail2ban). À confirmer dans les logs : un faux user-agent peut être bloqué alors que le vrai robot (IP vérifiée) passe.
- Lignes `Content-Signal:` dans robots.txt = robots.txt géré par Cloudflare : le signaler et vérifier que les signaux correspondent au choix de l'utilisateur.
- **Logs** (si accès serveur) : les robots IA viennent-ils vraiment, et que reçoivent-ils ?
  ```bash
  zgrep -hoiE 'gptbot|oai-searchbot|chatgpt-user|claudebot|claude-searchbot|claude-user|perplexitybot|perplexity-user|bingbot|googlebot|applebot|duckassistbot|mistralai-user|meta-externalagent|amazonbot|ccbot|bytespider' /var/log/nginx/access.log* | tr A-Z a-z | sort | uniq -c | sort -rn
  zgrep -hi 'oai-searchbot\|perplexitybot\|claude-searchbot' /var/log/nginx/access.log* | awk '{print $9}' | sort | uniq -c   # statuts reçus
  ```
- **Trafic référent IA** (logs ou analytics) : referers `chatgpt.com`, `perplexity.ai`, `gemini.google.com`, `copilot.microsoft.com`, `claude.ai` :
  ```bash
  zgrep -hoE '"https?://(chatgpt\.com|chat\.openai\.com|(www\.)?perplexity\.ai|gemini\.google\.com|copilot\.microsoft\.com|claude\.ai)[^"]*"' /var/log/nginx/access.log* | cut -d/ -f3 | sort | uniq -c | sort -rn
  ```

### 2. Index de recherche sous-jacents
- Indexation Google (voir audit-seo-technique) **et Bing** : site vérifié dans Bing Webmaster Tools, sitemap soumis, **IndexNow** pour signaler les nouvelles pages et les mises à jour (fichier clé + ping à la publication ; faisable depuis un endpoint Astro ou une action Convex au moment de publier).
- Pas de `nosnippet`, de `max-snippet` restrictif ni de `data-nosnippet` sur le contenu utile (colonne « Limites ») : ces directives excluent des AI Overviews.

### 3. Entité : qui publie ?
- JSON-LD **Organization** (ou EducationalOrganization, LocalBusiness) sur l'accueil : `name`, `url`, `logo`, `description`, `sameAs` (LinkedIn, Google Business Profile, YouTube, Instagram, Wikidata si elle existe, annuaires sectoriels), `address`, `contactPoint`. Même `@id` réutilisé sur tout le site.
- **Nom de marque cohérent** partout (`noms_entite`, og:site_name, suffixe des titles, footer) : les IA agrègent par nom.
- **Personnes** : auteurs et formateurs avec une page dédiée et un schema `Person` (`jobTitle`, `sameAs` LinkedIn), reliés aux articles par `author`.
- Page **à propos** substantielle : histoire, chiffres, équipe, certifications, presse.

### 4. Contenu « citable »
Pour chaque gabarit clé (accueil, formation, métier, article) :
- le texte essentiel est dans le **HTML initial** (colonne « Mots » : si c'est faible alors que la page paraît riche, du contenu est chargé en JS ou par un îlot `client:only`) ;
- des **réponses directes** : un paragraphe de 40 à 60 mots qui répond à la question juste sous le titre qui la pose ; des définitions ; des chiffres précis avec leur source et leur date ;
- des **titres en questions** là où c'est naturel (colonne « Q° ») ; des listes et **tableaux** (comparatifs, prix, durées, prérequis) ;
- des **données propres** (chiffres d'insertion, taux de satisfaction, études de cas) : c'est ce qu'une IA ne trouve pas ailleurs, donc ce qu'elle cite ;
- **dates** de publication et de mise à jour visibles + `dateModified` en JSON-LD ;
- une **FAQ** visible sur les pages business (FAQPage en JSON-LD reste utile pour la compréhension, même si Google n'affiche plus ces résultats enrichis pour la plupart des sites).

### 5. llms.txt (pari à faible coût)
- Présent ? Format : `# Nom`, `> résumé en une phrase`, sections `## …` avec des listes `- [Titre](URL absolue) : description`. Liens valides (`liens_casses`). `llms-full.txt` optionnel.
- Dans Astro : un endpoint `src/pages/llms.txt.ts` généré depuis les données (formations, articles) évite qu'il se périme. Un fichier statique dans `public/` se périme.

### 6. Présence hors site (souvent le vrai levier)
Les IA recoupent les sources. Lister avec l'utilisateur : avis Google et Trustpilot, annuaires et plateformes du secteur (ex. Mon Compte Formation, France Travail, Qualiopi pour la formation), articles de presse ou de partenaires, Wikipédia/Wikidata si c'est légitime, forums et communautés (Reddit, LinkedIn), comparatifs tiers où la marque devrait apparaître. C'est hors du code : en faire un plan d'actions séparé.

### 7. Test de présence (mesure de départ)
Préparer 10 à 15 questions réelles des cibles (à partir du contexte business), par exemple « meilleure formation no-code IA éligible CPF », « comment devenir chef de projet IA ». Donner à l'utilisateur un tableau à remplir en testant dans ChatGPT (recherche activée), Perplexity, Gemini, Copilot, Claude et Google (AI Overview / AI Mode) : marque citée (oui/non), URL citée, concurrents cités, position. À refaire tous les mois : c'est l'indicateur GEO le plus honnête.

## Correctifs types

```ts
// src/pages/llms.txt.ts — généré depuis les données, jamais périmé
import type { APIRoute } from 'astro';
export const GET: APIRoute = async ({ site }) => {
  const formations = await getFormations(); // requête Convex existante du projet
  const lines = [
    '# Nom de la marque',
    '> Une phrase qui dit qui vous êtes, pour qui, et ce qui vous distingue.',
    '', '## Formations',
    ...formations.map(f => `- [${f.titre}](${new URL(`/formations/${f.slug}`, site)}): ${f.resume}`),
  ];
  return new Response(lines.join('\n'), { headers: { 'Content-Type': 'text/plain; charset=utf-8' } });
};
```

```astro
<!-- Organization réutilisable (layout), même @id partout -->
<script type="application/ld+json" set:html={JSON.stringify({
  "@context": "https://schema.org", "@type": "EducationalOrganization",
  "@id": new URL('/#organization', Astro.site).href, "name": "Marque", "url": Astro.site?.href,
  "logo": new URL('/logo.png', Astro.site).href,
  "sameAs": ["https://www.linkedin.com/company/…", "https://g.page/…", "https://www.youtube.com/@…"]
})} />
```
(`set:html` avec `JSON.stringify` de données maîtrisées = sans risque ; ne pas y injecter de texte utilisateur non échappé.)

## Restitution
`rapports/geo.md` : tableau d'accès des robots, puis les constats `GEO-NNN`, puis en annexes le **plan hors site** et le **protocole de test** (les questions + le tableau vide à remplir).
