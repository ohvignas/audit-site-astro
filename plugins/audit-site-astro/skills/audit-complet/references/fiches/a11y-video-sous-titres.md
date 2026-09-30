---
id: a11y-video-sous-titres
titre: "Vidéos sans sous-titres ni transcription (balise track absente)"
domaine: Accessibilité
severite_type: moyenne
effort: M
declencheurs:
  - "lighthouse:video-caption|Les éléments `<video>` ne contiennent pas"
sources:
  - https://www.w3.org/WAI/WCAG22/Understanding/captions-prerecorded.html
  - https://www.w3.org/WAI/WCAG22/Understanding/audio-description-or-media-alternative-prerecorded.html
  - https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Elements/track
  - https://developer.mozilla.org/en-US/docs/Web/API/WebVTT_API
  - https://dequeuniversity.com/rules/axe/4.10/video-caption
  - https://accessibilite.numerique.gouv.fr/methode/criteres-et-tests/#4.1
---

# Vidéos sans sous-titres ni transcription (balise track absente)

> **En une phrase** : les vidéos hébergées sur le site n'ont ni sous-titres ni transcription, si bien que les personnes sourdes ou malentendantes (et tous ceux qui regardent sans le son) perdent l'information.

## Pourquoi c'est important

Une grande part des vidéos est regardée sans le son (transports, bureaux). Les sous-titres sont indispensables aux personnes sourdes et malentendantes et aident les non-francophones. WCAG 1.2.2 « Sous-titres (préenregistrés) » (niveau A) ; 1.2.3 et 1.2.5 (audiodescription ou alternative) ; RGAA thématique 4 (Multimédia). Un transcript textuel améliore aussi le référencement et la citation par les moteurs d'IA. Lighthouse ne contrôle que les balises `<video>` du site (pas les vidéos YouTube/Vimeo dans une iframe).

## Comment le constater soi-même

```bash
grep -rnE "<video|<iframe[^>]*(youtube|vimeo|dailymotion)" src | head -20
grep -rn "<track" src | head
```

Chaque `<video>` doit contenir au moins un `<track kind="captions">`. Pour les vidéos intégrées (YouTube, Vimeo), ouvrez la vidéo : le bouton « Sous-titres » est-il disponible ?

## Correction

1. **Produire le fichier de sous-titres** au format WebVTT (`.vtt`), en français, avec les dialogues et les sons importants entre crochets. Export possible depuis YouTube Studio, un logiciel de montage, ou transcription automatique **relue et corrigée à la main**.

   ```text
   WEBVTT

   00:00:01.000 --> 00:00:04.500
   Bonjour, bienvenue dans cette présentation.

   00:00:04.500 --> 00:00:08.000
   [musique] Aujourd'hui, nous parlons d'accessibilité.
   ```
2. **Placer le fichier dans `public/`** (par exemple `public/sous-titres/presentation.fr.vtt`) et l'associer à la vidéo.

   ```astro
   <video controls preload="metadata" poster="/img/presentation.webp" width="1280" height="720">
     <source src="/videos/presentation.mp4" type="video/mp4" />
     <track kind="captions" src="/sous-titres/presentation.fr.vtt" srclang="fr" label="Français" default />
     <p>Votre navigateur ne lit pas cette vidéo. <a href="/videos/presentation.mp4">Télécharger la vidéo</a></p>
   </video>
   ```
3. **Vidéos intégrées (YouTube, Vimeo)** : téléversez les sous-titres sur la plateforme, activez-les par défaut si possible (paramètre `cc_load_policy=1` pour YouTube), et donnez un titre à l'iframe.

   ```astro
   <iframe title="Présentation de l'offre (vidéo, sous-titres disponibles)" src="https://www.youtube-nocookie.com/embed/IDENTIFIANT" loading="lazy" allowfullscreen></iframe>
   ```
4. **Transcription** : sous la vidéo, un bloc `<details><summary>Transcription</summary>…</details>` avec le texte complet, indispensable pour un contenu uniquement audio (podcast) et utile pour le référencement.
5. **Audiodescription** : si des informations importantes ne sont que visuelles (schémas, démonstration muette), ajoutez une piste d'audiodescription ou décrivez-les dans le texte associé (WCAG 1.2.3/1.2.5).
6. **Pas de lecture automatique avec son** ; lecture automatique éventuelle seulement muette, avec bouton pause (voir `a11y-animations-reduced-motion`).
7. **Serveur** : le type `text/vtt` doit être servi correctement (nginx le connaît par défaut dans `mime.types`, Caddy aussi) ; le fichier doit être servi depuis le même domaine (sinon CORS, attribut `crossorigin`).

## Critères d'acceptation

- [ ] Chaque `<video>` a un `<track kind="captions" srclang="fr">` avec un fichier `.vtt` valide et relu.
- [ ] Les vidéos intégrées ont des sous-titres disponibles et un `title` sur l'iframe.
- [ ] Une transcription existe pour les contenus importants.
- [ ] Aucune lecture automatique avec son.
- [ ] Lighthouse : « Les éléments `<video>` contiennent un élément `<track>` avec `[kind="captions"]` » réussi.

## Vérification après correction

```bash
curl -sI https://exemple.fr/sous-titres/presentation.fr.vtt | grep -iE '^(HTTP|content-type)'     # 200, text/vtt
npx lighthouse https://exemple.fr/page-video --only-categories=accessibility --quiet --output=json --output-path=/tmp/a11y.json --locale=fr
python3 -c "import json; print(json.load(open('/tmp/a11y.json'))['audits']['video-caption']['score'])"
```

## Pièges et retour arrière

- Des sous-titres générés automatiquement sans relecture contiennent des contresens : relire avant publication.
- Un fichier `.vtt` mal formé (première ligne autre que `WEBVTT`, minutage invalide) est ignoré par le navigateur.
- Retour arrière : retirer la balise `<track>` ; l'accessibilité se dégrade.

## Pour aller plus loin

- WCAG 1.2.2 (sous-titres préenregistrés) et 1.2.5 (audiodescription).
- MDN, élément `<track>` et format WebVTT.
- RGAA, thématique Multimédia.
