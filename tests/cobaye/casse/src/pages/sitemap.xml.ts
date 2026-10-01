import type { APIRoute } from 'astro';

const chemins = ['/', '/catalogue', '/formations', '/formations/no-code', '/formations/ia', '/formations/ia-generative',
  '/contact', '/orpheline', '/cachee', '/page-404-dans-sitemap', '/blog/article-ok', '/blog/article-casse'];

export const GET: APIRoute = ({ request }) => {
  const origin = new URL(request.url).origin; // derrière le proxy : http://
  const urls = chemins.map((c) => `<url><loc>${origin}${c}</loc></url>`).join('');
  return new Response(`<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">${urls}</urlset>`,
    { headers: { 'Content-Type': 'application/xml; charset=utf-8' } });
};
