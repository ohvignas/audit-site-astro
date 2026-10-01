import { defineConfig, envField, fontProviders, memoryCache } from 'astro/config';
import node from '@astrojs/node';
import react from '@astrojs/react';

export default defineConfig({
  site: 'https://propre.cobaye.test',
  output: 'server',
  adapter: node({ mode: 'standalone' }),
  integrations: [react()],
  trailingSlash: 'never',
  prefetch: { prefetchAll: false, defaultStrategy: 'hover' },
  image: {
    layout: 'constrained',
    responsiveStyles: true,
    remotePatterns: [{ protocol: 'https', hostname: 'propre.cobaye.test' }],
  },
  fonts: [{ provider: fontProviders.fontsource(), name: 'Inter', cssVariable: '--font-inter', weights: [400, 700], subsets: ['latin'] }],
  cache: { provider: memoryCache() },
  routeRules: { '/formations/[slug]': { maxAge: 300, swr: 60, tags: ['formations'] } },
  security: {
    allowedDomains: [{ hostname: 'propre.cobaye.test', protocol: 'https' }],
    csp: true,
  },
  env: { schema: { SECRET_KEY: envField.string({ context: 'server', access: 'secret', optional: true }) } },
});
