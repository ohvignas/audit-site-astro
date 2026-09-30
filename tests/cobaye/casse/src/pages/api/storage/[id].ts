import type { APIRoute } from 'astro';
import { readFile } from 'node:fs/promises';
import { join } from 'node:path';
export const GET: APIRoute = async () =>
  new Response(await readFile(join(process.cwd(), 'dist/client/images/storage-logo.png')), { headers: { 'Content-Type': 'image/png' } });
