import { defineConfig } from 'astro/config';
import node from '@astrojs/node';
import react from '@astrojs/react';

export default defineConfig({
  site: 'https://casse.cobaye.test',
  output: 'server',
  adapter: node({ mode: 'standalone' }),
  integrations: [react()],
  // C12 : pas de security.allowedDomains — C13 : pas de csp — C14 : pas d'env.schema
  // C15 : pas de trailingSlash — P08 : pas de prefetch — P09 : pas de cache de routes — P10 : pas d'image.layout
  image: { remotePatterns: [{ protocol: 'https' }] }, // X06 : n'importe quel domaine https accepté par /_image
  redirects: {
    '/ancienne-page': '/page-intermediaire', // S08, S09 (chaîne)
    '/page-intermediaire': '/formations/ia',
  },
  vite: { build: { sourcemap: true } }, // C16, X02
});
