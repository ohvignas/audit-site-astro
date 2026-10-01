---
id: perf-js-tiers
titre: Scripts et intégrations tierces qui alourdissent le chargement (analytics, chat, vidéos)
domaine: Performance
severite_type: moyenne
effort: M
declencheurs:
  - "code:script\\(s\\)/embed\\(s\\) tiers repérés"
  - "lighthouse:third-party-summary|third-parties-insight|Réduire au maximum l'utilisation de code tiers|Réduire l'impact du code tiers|^Tiers$"
sources:
  - https://web.dev/articles/optimizing-content-efficiency-loading-third-party-javascript
  - https://web.dev/articles/embed-best-practices
  - https://docs.astro.build/en/guides/integrations-guide/partytown/
  - https://docs.astro.build/en/guides/client-side-scripts/
---

# Scripts et intégrations tierces qui alourdissent le chargement (analytics, chat, vidéos)

> **En une phrase** : des services externes (Google Tag Manager, Analytics, chat, YouTube, Calendly, pixels publicitaires) chargent leur propre JavaScript dès l'arrivée du visiteur, ce qui ralentit la page et bloque le thread principal.

## Pourquoi c'est important

Un site Astro léger peut perdre la moitié de sa vitesse à cause de quelques tags. Un iframe YouTube classique télécharge plusieurs centaines de Ko avant même le clic ; un widget de chat charge un framework complet ; chaque domaine tiers ajoute connexions DNS/TLS et JavaScript hors de votre contrôle. Lighthouse chiffre chaque tiers en Ko et en ms de blocage (audit « Réduire l'impact du code tiers », analyse « Tiers »). Charger des traceurs avant le consentement pose aussi un problème RGPD.

## Comment le constater soi-même

```bash
# Où le code référence-t-il des services tiers ?
grep -rnEi "googletagmanager|google-analytics|gtag\(|fbq\(|hotjar|clarity\.ms|intercom|crisp\.chat|tawk\.to|hs-scripts|calendly|youtube\.com/embed|player\.vimeo" src public | head -30
# Domaines tiers réellement appelés par la page
curl -s https://SITE/ | grep -oE '(src|href)="https?://[^"/]+' | sed -E 's/.*:\/\///' | sort | uniq -c | sort -rn
# Poids par tiers mesuré par Lighthouse
grep -i "Tiers" /tmp/verif/pagespeed-summary.md
```

Problème présent : plusieurs domaines tiers, des dizaines à centaines de Ko et du blocage attribué à ces tiers. Corrigé : tiers essentiels seuls, chargés après consentement et/ou à l'interaction.

## Correction

1. **Faire l'inventaire** : pour chaque tiers, se demander s'il est encore utilisé. Supprimer les tags orphelins (anciens pixels, tests A/B terminés).
2. **Charger l'analytics après consentement**, jamais avant. Injecter le script uniquement quand l'utilisateur accepte :

```astro
<script is:inline>
  window.chargerAnalytics = function () {
    if (window.__analyticsCharge) return;
    window.__analyticsCharge = true;
    var s = document.createElement('script');
    s.src = 'https://www.googletagmanager.com/gtag/js?id=G-XXXXXXX';
    s.async = true;
    document.head.appendChild(s);
    window.dataLayer = window.dataLayer || [];
    window.gtag = function () { window.dataLayer.push(arguments); };
    window.gtag('js', new Date());
    window.gtag('config', 'G-XXXXXXX');
  };
</script>
```

Appeler `window.chargerAnalytics()` depuis le bouton « Accepter » de la bannière de consentement.
3. **Vidéo YouTube : façade** au lieu de l'iframe. La miniature s'affiche, l'iframe n'est créée qu'au clic :

```astro
---
const { id, titre } = Astro.props;
---
<button type="button" class="yt" data-id={id} aria-label={`Lire la vidéo : ${titre}`}>
  <img src={`https://i.ytimg.com/vi/${id}/hqdefault.jpg`} alt="" width="480" height="360" loading="lazy" />
</button>
<script>
  document.querySelectorAll<HTMLButtonElement>('.yt').forEach((bouton) => {
    bouton.addEventListener('click', () => {
      const iframe = document.createElement('iframe');
      iframe.src = `https://www.youtube-nocookie.com/embed/${bouton.dataset.id}?autoplay=1`;
      iframe.allow = 'autoplay; encrypted-media; picture-in-picture';
      iframe.allowFullscreen = true;
      iframe.width = '480';
      iframe.height = '360';
      bouton.replaceWith(iframe);
    }, { once: true });
  });
</script>
```

Ajouter du CSS pour respecter un ratio (`aspect-ratio: 4 / 3`). Des bibliothèques existent (`lite-youtube-embed`, composants `astro-embed`) : à choisir après lecture de leur documentation.
4. **Chat, prise de rendez-vous, avis** : charger au clic sur un bouton (« Discuter »), ou à `client:idle` / `client:visible` dans un îlot.
5. **Tags lourds (GTM, Meta Pixel)** : envisager Partytown (`npx astro add partytown`, puis `type="text/partytown"` sur le script). Tester : tous les scripts ne fonctionnent pas dans un worker.

```js
// astro.config.mjs
import { defineConfig } from 'astro/config';
import partytown from '@astrojs/partytown';

export default defineConfig({
  integrations: [partytown({ config: { forward: ['dataLayer.push'] } })],
});
```

6. **Préconnexion** uniquement pour un tiers indispensable au premier écran : `<link rel="preconnect" href="https://cdn.exemple-tiers.com" crossorigin />`.
7. **Remplacer** un tiers lourd par une alternative légère, ou auto-héberger (statistiques sans cookies, carte statique au lieu d'une carte interactive).

## Critères d'acceptation

- [ ] Aucun script d'analytics ou de publicité ne se charge avant le consentement
- [ ] Les vidéos sont en façade : aucune requête vers `youtube.com` avant le clic
- [ ] Le poids des tiers (Lighthouse) baisse d'au moins moitié, TBT en baisse
- [ ] Les mesures et formulaires continuent de fonctionner (événements reçus dans l'outil d'analytics)

## Vérification après correction

```bash
curl -s https://SITE/ | grep -c "youtube.com/embed"     # attendu : 0
bash scripts/lighthouse_run.sh /tmp/verif https://SITE/
python3 scripts/astro_scan.py /chemin/projet --out /tmp/verif
```

## Pièges et retour arrière

- Un tag retardé peut perdre les premières mesures : c'est le compromis attendu, accepté avec le consentement.
- Partytown peut casser un script qui manipule le DOM directement : tester chaque tag.
- Retour arrière : remettre la balise `<script>` d'origine.

## Pour aller plus loin

- https://web.dev/articles/optimizing-content-efficiency-loading-third-party-javascript : maîtriser le JavaScript tiers.
- https://web.dev/articles/embed-best-practices : intégrer vidéos et widgets sans pénaliser la page.
- https://docs.astro.build/en/guides/integrations-guide/partytown/ : exécuter des scripts dans un Web Worker.
- https://docs.astro.build/en/guides/client-side-scripts/ : scripts côté client dans Astro.
