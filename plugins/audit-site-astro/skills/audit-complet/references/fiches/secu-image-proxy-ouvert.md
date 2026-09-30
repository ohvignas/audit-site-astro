---
id: secu-image-proxy-ouvert
titre: "Endpoint /_image utilisable comme proxy d'images ouvert (remotePatterns trop large)"
domaine: Sécurité
severite_type: moyenne
effort: S
declencheurs:
  - "securite:proxy d'images ouvert"
  - "securite:/_image indéterminé"
sources:
  - https://docs.astro.build/en/reference/configuration-reference/#imageremotepatterns
  - https://docs.astro.build/en/reference/configuration-reference/#imagedomains
  - https://docs.astro.build/en/guides/images/#authorizing-remote-images
---

# Endpoint /_image utilisable comme proxy d'images ouvert (remotePatterns trop large)

> **En une phrase** : `/_image` accepte de télécharger et de re-servir une image depuis un domaine que vous n'avez pas choisi, ce qui fait de votre serveur un relais gratuit pour n'importe qui.

## Pourquoi c'est important

Sur un site Astro rendu à la demande, l'endpoint `/_image` redimensionne des images, y compris distantes. Il ne doit obéir qu'aux domaines déclarés dans `image.domains` / `image.remotePatterns`. Si la liste est trop large (motif sans `hostname`, `**`, domaine de stockage partagé), n'importe qui peut faire télécharger et transformer des images arbitraires par votre serveur : consommation de bande passante et de processeur, hébergement d'images détournées derrière votre nom de domaine, et sonde de votre réseau interne (SSRF) si un motif accepte des adresses internes. Une requête vers un domaine non autorisé doit recevoir 403.

## Comment le constater soi-même

```bash
# Image réelle sur un domaine non autorisé : attendu 403 (ou 404 si le site est 100 % statique)
curl -s -o /dev/null -w '%{http_code} %{content_type}\n' 'https://exemple.fr/_image?href=https%3A%2F%2Fwww.google.com%2Fimages%2Fbranding%2Fgooglelogo%2F1x%2Fgooglelogo_color_272x92dp.png&w=16&f=webp'
# Configuration (motifs trop larges à repérer)
grep -nE "remotePatterns|domains|hostname|pathname" astro.config.*
```

Problème présent : 200 avec une image, ou `hostname: '**'`, motif sans `hostname`, `**.com`. Corrigé : 403 pour tout ce qui n'est pas explicitement listé. La sonde de l'outil demande à `/_image` de transformer une vraie image PNG d'un domaine tiers : « ❌ proxy d'images ouvert » si elle reçoit une image (200, `image/*`), « ⚠️ /_image indéterminé » sur un 5xx, une redirection ou une image distante injoignable. Un 5xx signifie souvent que le domaine est **autorisé** mais que le téléchargement a échoué : relisez `remotePatterns` dans ce cas aussi. Testez également avec un domaine que vous contrôlez et qui n'est pas autorisé.

## Correction

1. **Lister uniquement les sources réellement utilisées** (CMS, stockage). Fichier `astro.config.mjs` :

   ```js
   // astro.config.mjs
   import { defineConfig } from 'astro/config';

   export default defineConfig({
     image: {
       // Domaine exact, sans joker
       domains: ['images.exemple.fr'],
       remotePatterns: [
         // Un bucket précis et un dossier précis, en https uniquement
         { protocol: 'https', hostname: 'cdn.exemple.fr', pathname: '/medias/**' },
         // Stockage Convex : le sous-domaine exact de votre déploiement
         { protocol: 'https', hostname: 'nom-du-deploiement.convex.cloud', pathname: '/api/storage/**' },
       ],
     },
   });
   ```

   Règles de motifs (documentation Astro) : `hostname` commençant par `**.` autorise tous les sous-domaines, `*.` un seul niveau ; `pathname` finissant par `/**` autorise tous les sous-chemins, `/*` un seul niveau. Sans joker, la valeur doit correspondre exactement.
2. **Supprimer** les motifs génériques : `hostname: '**'`, `{ protocol: 'https' }` seul, `**.amazonaws.com` (tous les buckets du monde), `**.convex.cloud` (tous les déploiements Convex). Préférez le nom exact de votre bucket / déploiement.
3. Astro suit les redirections HTTP : la destination finale doit aussi correspondre à un motif autorisé ; ne listez pas de service de redirection ou de raccourcisseur d'URL.
4. **Pour un site sans images distantes**, laissez `domains` et `remotePatterns` vides (valeur par défaut) : aucune image distante ne sera transformée.
5. **Défense en profondeur** au proxy : limiter la fréquence des appels à `/_image` et mettre en cache les résultats, ce qui protège aussi les performances.

   ```nginx
   limit_req_zone $binary_remote_addr zone=images:10m rate=20r/s;
   location /_image { limit_req zone=images burst=40 nodelay; proxy_pass http://127.0.0.1:4321; }
   ```

   (la ligne `limit_req_zone` va dans le contexte `http`.)
6. Reconstruisez, redéployez, retestez.

## Critères d'acceptation

- [ ] `remotePatterns` / `domains` ne contiennent que des domaines que vous contrôlez ou utilisez.
- [ ] La requête de test vers `example.com` renvoie 403.
- [ ] Les images du site (locales et distantes autorisées) s'affichent toujours.
- [ ] Aucun avertissement de build sur des images distantes non autorisées.

## Vérification après correction

```bash
curl -s -o /dev/null -w '%{http_code}\n' 'https://exemple.fr/_image?href=https%3A%2F%2Fexample.com%2Fx.png&w=100&f=webp'   # 403
bash scripts/security_probe.sh https://exemple.fr/ /tmp/verif-secu && grep '_image' /tmp/verif-secu/security-probe.md
```

## Pièges et retour arrière

- Restreindre trop fort casse l'affichage des images d'un CMS : listez chaque domaine réel (regardez les URL dans le HTML, `grep -oE 'https://[^/"]+' dist -r | sort -u`).
- Une image affichée par une balise `<img>` brute n'est pas concernée : elle ne passe pas par `/_image`.
- Retour arrière : remettre l'ancienne liste (Git), reconstruire, redéployer.

## Pour aller plus loin

- Astro, `image.remotePatterns` : propriétés et jokers.
- Astro, `image.domains` : liste de domaines exacts.
- Guide des images Astro : autoriser des images distantes.
