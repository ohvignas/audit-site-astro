import type { APIRoute } from 'astro';
export const GET: APIRoute = async () => {
  await new Promise((r) => setTimeout(r, 800));
  return new Response('window.__bloquant = true;', { headers: { 'Content-Type': 'application/javascript' } });
};
