---
id: geo-bing-webmaster-indexnow
titre: Bing Webmaster Tools et IndexNow (index de Bing, base de Copilot)
domaine: GEO / IA
severite_type: basse
effort: S
declencheurs: []
sources:
  - https://www.indexnow.org/documentation
  - https://www.bing.com/indexnow/getstarted
  - https://blogs.bing.com/webmaster/February-2026/Introducing-AI-Performance-in-Bing-Webmaster-Tools-Public-Preview
  - https://docs.astro.build/en/guides/endpoints/
  - https://docs.convex.dev/functions/actions
---

# Bing Webmaster Tools et IndexNow

> **En une phrase** : Bing alimente Copilot et d'autres assistants ; vérifier le site dans Bing Webmaster Tools, y soumettre le sitemap et notifier chaque nouvelle page ou mise à jour via IndexNow accélère la découverte du contenu.

*Fiche sans déclencheur automatique : l'outil ne détecte pas l'absence de Bing Webmaster Tools ni d'IndexNow (il vérifie seulement que Bingbot n'est pas bloqué, voir `geo-robots-bots-recherche-bloques`). À inclure sur demande ou dans tout plan d'action GEO.*

## Pourquoi c'est important

Bing est l'index de Copilot et sert de source à une partie des autres assistants et moteurs. Un site absent ou peu exploré par Bing est donc moins susceptible d'être cité par ces outils. **IndexNow** est un protocole ouvert : on prévient les moteurs participants (dont Bing) qu'une URL a été créée, modifiée ou supprimée, au lieu d'attendre le prochain passage du robot. Il ne garantit pas l'indexation (les moteurs gardent leur décision de crawl), et Google n'en fait pas partie à ma connaissance (vérifier la liste des participants sur indexnow.org). Bing Webmaster Tools propose aussi un rapport « AI Performance » (aperçu public depuis février 2026) qui indique combien de fois le site est cité dans Copilot et les résumés IA de Bing : c'est une des rares mesures officielles de citation IA.

## Comment le constater soi-même

```bash
# Fichier clé IndexNow présent ? (remplacer CLE)
curl -s -o /dev/null -w '%{http_code}\n' https://SITE/CLE.txt
# Balise de vérification Bing ou fichier d'authentification
curl -s https://SITE/ | grep -io 'msvalidate.01[^>]*'
curl -s -o /dev/null -w '%{http_code}\n' https://SITE/BingSiteAuth.xml
# Sitemap déclaré
curl -s https://SITE/robots.txt | grep -i '^sitemap'
```

Dans Bing Webmaster Tools (https://www.bing.com/webmasters), le site est « vérifié » et le sitemap apparaît avec le statut « Réussi ».

## Correction

1. Créer un compte Bing Webmaster Tools **avec une adresse professionnelle du propriétaire** (action à faire faire par le propriétaire). Ajouter le site : soit importer depuis Google Search Console, soit saisir l'URL. Vérifier la propriété par l'une des méthodes proposées : fichier `BingSiteAuth.xml` à placer dans `public/`, balise `<meta name="msvalidate.01" content="…" />` dans le `<head>`, ou enregistrement DNS CNAME.
2. Soumettre le sitemap (`https://exemple.fr/sitemap-index.xml`) dans la section Sitemaps.
3. **IndexNow, clé** : générer une clé (8 à 128 caractères : lettres, chiffres, tirets), par exemple `openssl rand -hex 16`. Créer `public/<cle>.txt` dont le contenu est exactement la clé (UTF-8). La clé n'est pas un secret (elle est publique par conception) mais ne la partager qu'avec ce que vous souhaitez notifier.
4. **IndexNow, notification après chaque déploiement** : script `scripts/indexnow.mjs`, appelé après le build (pas de dépendance) :

```js
// scripts/indexnow.mjs — usage : node scripts/indexnow.mjs https://exemple.fr/page-1/ https://exemple.fr/page-2/
const HOST = 'exemple.fr';
const KEY = process.env.INDEXNOW_KEY; // même valeur que le nom de public/<cle>.txt
if (!KEY) { console.error('INDEXNOW_KEY manquante'); process.exit(1); }
const urlList = process.argv.slice(2);
if (urlList.length === 0) { console.error('Aucune URL'); process.exit(1); }

const res = await fetch('https://api.indexnow.org/indexnow', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json; charset=utf-8' },
  body: JSON.stringify({ host: HOST, key: KEY, keyLocation: `https://${HOST}/${KEY}.txt`, urlList }),
});
console.log('IndexNow', res.status); // 200 ou 202 = accepté
```

   Réponses : `200` soumis, `202` reçu (clé en cours de validation), `400` format invalide, `403` clé invalide, `422` URL hors du domaine, `429` trop de requêtes. Jusqu'à 10 000 URL par requête. Ne notifier que les URL **modifiées** ou nouvelles (pas tout le site à chaque déploiement).
5. **Variante Convex** : si la publication passe par Convex (nouvel article enregistré), déclencher une action serveur (les actions Convex peuvent appeler `fetch`) :

```ts
// convex/indexnow.ts
import { action } from './_generated/server';
import { v } from 'convex/values';

export const notifier = action({
  args: { urls: v.array(v.string()) },
  handler: async (_ctx, { urls }) => {
    const key = process.env.INDEXNOW_KEY; // npx convex env set INDEXNOW_KEY <cle>
    if (!key || urls.length === 0) return { status: 0 };
    const res = await fetch('https://api.indexnow.org/indexnow', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json; charset=utf-8' },
      body: JSON.stringify({ host: 'exemple.fr', key, keyLocation: `https://exemple.fr/${key}.txt`, urlList: urls }),
    });
    return { status: res.status };
  },
});
```

6. Dans Bing Webmaster Tools, consulter les rapports IndexNow et « AI Performance » (si disponible pour le site) une fois par mois.

## Critères d'acceptation

- [ ] Le site est vérifié dans Bing Webmaster Tools et le sitemap est en statut « Réussi »
- [ ] `https://SITE/<cle>.txt` répond `200` et contient exactement la clé
- [ ] Une notification de test renvoie `200` ou `202`
- [ ] Bingbot n'est pas bloqué (robots.txt et pare-feu)
- [ ] Aucune régression : build OK, la clé n'est pas commitée dans un fichier de configuration privé

## Vérification après correction

```bash
curl -s https://SITE/CLE.txt
INDEXNOW_KEY=CLE node scripts/indexnow.mjs https://SITE/une-page-modifiee/
curl -sI -A 'Mozilla/5.0 (compatible; bingbot/2.0; +http://www.bing.com/bingbot.htm)' https://SITE/ | head -1
```

## Pièges et retour arrière

- Le fichier clé doit être à la racine du domaine (ou indiqué par `keyLocation`) : un `404` provoque un `403`/`422` de l'API.
- Ne pas soumettre d'URL `noindex`, redirigées ou en erreur.
- Retour arrière : supprimer `public/<cle>.txt` et le script ; retirer le site de Bing Webmaster Tools n'a pas d'autre effet.

## Pour aller plus loin

- https://www.indexnow.org/documentation : protocole, clé, codes de réponse.
- https://www.bing.com/indexnow/getstarted : mise en route côté Bing.
- https://blogs.bing.com/webmaster/February-2026/Introducing-AI-Performance-in-Bing-Webmaster-Tools-Public-Preview : rapport AI Performance.
- https://docs.astro.build/en/guides/endpoints/ : endpoints Astro.
- https://docs.convex.dev/functions/actions : actions Convex.
