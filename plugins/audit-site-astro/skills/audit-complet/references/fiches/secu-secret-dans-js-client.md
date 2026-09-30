---
id: secu-secret-dans-js-client
titre: "Clé secrète présente dans le code envoyé au navigateur (et rotation)"
domaine: Sécurité
severite_type: critique
effort: M
declencheurs:
  - "securite:Motifs de secrets trouvés"
  - "code:Variables d'environnement non PUBLIC_ référencées dans du code client"
sources:
  - https://docs.astro.build/en/guides/environment-variables/
  - https://docs.astro.build/en/guides/actions/
  - https://docs.astro.build/en/guides/endpoints/
  - https://docs.convex.dev/cli/deploy-key-types
  - https://docs.github.com/en/code-security/secret-scanning/introduction/about-secret-scanning
---

# Clé secrète présente dans le code envoyé au navigateur (et rotation)

> **En une phrase** : une clé qui doit rester secrète est visible dans le HTML ou le JavaScript du site, donc utilisable par n'importe qui tant qu'elle n'est pas révoquée.

## Pourquoi c'est important

Tout ce qui est envoyé au navigateur est public. Une clé Stripe `sk_live_`, OpenAI `sk-`, Anthropic `sk-ant-`, AWS `AKIA…`, une clé privée, un jeton GitHub ou une **clé de déploiement Convex** permet d'agir à votre place : dépenser sur votre compte, lire des données, modifier votre backend. Des robots scannent les sites et les dépôts publics et exploitent une clé en quelques minutes. Supprimer la clé du code ne suffit pas : elle a pu être copiée, il faut la **révoquer**.

Ne sont **pas** des secrets : l'URL publique d'un déploiement Convex (`PUBLIC_CONVEX_URL`), une clé Stripe `pk_live_`, un identifiant Google Analytics, une clé Google Maps restreinte par domaine (`AIza…`). En cas de doute, vérifiez dans la documentation du fournisseur.

## Comment le constater soi-même

```bash
# Dans le HTML et le JS livrés (les valeurs ne sont volontairement pas recopiées)
curl -s https://exemple.fr/ > /tmp/page.html
grep -aoE '(sk_live_|sk-ant-|sk-[A-Za-z0-9]{20}|AKIA[0-9A-Z]{16}|ghp_|xox[baprs]-|BEGIN (RSA |EC )?PRIVATE KEY|CONVEX_DEPLOY_KEY)' /tmp/page.html | sort -u
# Dans le code source
grep -rnE "import\.meta\.env\.[A-Z_]+" src --include=*.tsx --include=*.jsx --include=*.svelte --include=*.vue | grep -v PUBLIC_
```

Présent : au moins un motif trouvé, ou une variable sans `PUBLIC_` lue dans un composant client. Corrigé : aucun résultat.

## Correction

1. **Révoquer et remplacer la clé, sans attendre** (avant même de corriger le code). Ne collez jamais la valeur dans un ticket ou un chat.

   | Fournisseur | Où faire tourner la clé |
   |---|---|
   | Convex (clé de déploiement) | Tableau de bord du déploiement, page Settings : supprimer la clé (« Delete ») puis générer une nouvelle clé ; en ligne de commande `npx convex deployment token` permet de créer et de supprimer (`token delete`) une clé. Mettez la nouvelle valeur dans le secret de votre CI / hébergeur. |
   | Stripe | Tableau de bord, Développeurs, Clés API : « Renouveler la clé » (roll) sur la clé secrète, avec expiration de l'ancienne. |
   | OpenAI, Anthropic | Console du fournisseur, section clés d'API : créer une nouvelle clé, supprimer l'ancienne. |
   | AWS | IAM, utilisateur, identifiants de sécurité : créer une seconde clé, migrer, désactiver puis supprimer l'ancienne. |
   | GitHub | Paramètres, Developer settings : révoquer le jeton, en créer un nouveau avec le minimum de droits. |
   | Slack, Resend, autres | Tableau de bord du service, section clés / jetons : révoquer puis recréer. |
   | Clé privée (`BEGIN PRIVATE KEY`) | Générer une nouvelle paire, déployer la nouvelle clé publique, retirer l'ancienne. |

   Ensuite, consultez le journal d'activité du service pour détecter un usage suspect entre la publication et la révocation.
2. **Trouver d'où vient la fuite** : variable lue dans un composant client (`.tsx`, `.jsx`, `.svelte`, `.vue`, `<script>` d'un `.astro`, îlot `client:*`) ou préfixée `PUBLIC_` par erreur.
3. **Déplacer l'appel côté serveur**. Le composant client appelle une Action ou un endpoint Astro qui, lui, détient le secret.

   ```ts
   // src/pages/api/contact.ts (rendu à la demande : nécessite un adaptateur, ex. @astrojs/node)
   import type { APIRoute } from 'astro';
   import { RESEND_API_KEY } from 'astro:env/server';

   export const prerender = false;

   export const POST: APIRoute = async ({ request }) => {
     const donnees = await request.json();
     const reponse = await fetch('https://api.resend.com/emails', {
       method: 'POST',
       headers: { Authorization: `Bearer ${RESEND_API_KEY}`, 'Content-Type': 'application/json' },
       body: JSON.stringify({ from: 'site@exemple.fr', to: 'contact@exemple.fr', subject: 'Contact', text: String(donnees.message ?? '').slice(0, 2000) }),
     });
     return new Response(null, { status: reponse.ok ? 204 : 502 });
   };
   ```
4. **Déclarer la variable comme secret serveur** pour que toute future fuite fasse échouer le build : voir `secu-astro-env-schema`.
5. **Secret déjà dans l'historique Git** : la rotation de l'étape 1 reste obligatoire ; voir aussi `secu-env-versionne-git` pour la purge.
6. Reconstruisez, faites redéployer par l'humain, et relancez la vérification. Ajoutez un contrôle automatique (GitHub secret scanning, `gitleaks` en intégration continue).

## Critères d'acceptation

- [ ] L'ancienne clé est révoquée (l'appel avec l'ancienne valeur échoue).
- [ ] Aucun motif de secret dans le HTML ni dans les scripts livrés.
- [ ] Plus aucune variable sans `PUBLIC_` lue dans du code client.
- [ ] Les fonctions qui utilisaient la clé marchent avec la nouvelle, via le serveur.
- [ ] Aucune régression : formulaires et intégrations testés.

## Vérification après correction

```bash
bash scripts/security_probe.sh https://exemple.fr/ /tmp/verif-secu
sed -n '/Clés et secrets/,/Méthodes HTTP/p' /tmp/verif-secu/security-probe.md
python3 scripts/astro_scan.py /chemin/du/projet --out /tmp/verif-code && grep -i "PUBLIC_" /tmp/verif-code/code-scan.md
```

## Pièges et retour arrière

- Préfixer une variable par `PUBLIC_` la publie : à réserver aux valeurs publiques.
- Le CDN ou le navigateur peut garder l'ancienne page : purgez le cache.
- Ne faites pas tourner la clé avant d'avoir prévu où mettre la nouvelle valeur (secrets de l'hébergeur, `.env` du serveur) : sinon interruption de service.
- Retour arrière : impossible et non souhaitable pour la clé compromise ; annulez seulement le changement de code si une régression apparaît.

## Pour aller plus loin

- Astro, variables d'environnement : `PUBLIC_` contre secrets serveur.
- Astro Actions et endpoints : appeler un service avec un secret depuis le serveur.
- Convex, types de clés de déploiement : créer et supprimer une clé.
- GitHub secret scanning : détection automatique de secrets.
