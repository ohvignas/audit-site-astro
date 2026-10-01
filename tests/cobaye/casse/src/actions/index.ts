import { defineAction } from 'astro:actions';

export const server = {
  // C18 : action publique sans schéma input — aucune validation des données reçues
  inscrire: defineAction({
    accept: 'form',
    handler: async (donnees) => ({ ok: true, recu: donnees instanceof FormData }),
  }),
};
