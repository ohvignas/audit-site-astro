import type { APIRoute } from 'astro';
// Banc v2.1 : les pages de src/pages/v21/ entrent dans le sitemap automatiquement (sinon not_in_sitemap sur le propre)
const v21 = Object.keys(import.meta.glob('./v21/*.astro'))
  .map((p) => (p === './v21/index.astro' ? '/v21' : p.slice(1, -6))).sort();
const chemins = ['/', '/catalogue', '/formations', '/formations/no-code', '/formations/ia', '/formations/ia-generative',
  '/blog/article-ok', '/blog/article-casse', '/a-propos', '/contact', '/mentions-legales', '/confidentialite', ...v21];
const maj = '2026-09-01';
export const GET: APIRoute = ({ site }) => {
  const urls = chemins.map((c) => `<url><loc>${new URL(c, site).href.replace(/\/$/, c === '/' ? '/' : '')}</loc><lastmod>${maj}</lastmod></url>`).join('');
  return new Response(`<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">${urls}</urlset>`,
    { headers: { 'Content-Type': 'application/xml; charset=utf-8' } });
};
