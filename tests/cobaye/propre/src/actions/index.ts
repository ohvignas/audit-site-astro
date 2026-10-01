import { defineAction } from 'astro:actions';
import { z } from 'astro/zod';

export const server = {
  inscrire: defineAction({
    accept: 'form',
    input: z.object({ email: z.email() }),
    handler: async ({ email }) => ({ ok: true, domaine: email.split('@')[1] }),
  }),
};
