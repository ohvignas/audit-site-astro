import { defineCollection } from 'astro:content';
import { glob } from 'astro/loaders';
import { z } from 'astro/zod';

const blog = defineCollection({
  loader: glob({ pattern: '**/*.md', base: './src/content/blog' }),
  schema: ({ image }) => z.object({
    titre: z.string(), description: z.string(), cover: image(), auteur: z.string(),
    publie: z.coerce.date(), modifie: z.coerce.date(),
  }),
});
export const collections = { blog };
