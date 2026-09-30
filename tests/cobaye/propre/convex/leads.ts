import { mutation, query } from './_generated/server';
import { v } from 'convex/values';

export const creer = mutation({
  args: { email: v.string() },
  handler: async (ctx, args) => {
    const identite = await ctx.auth.getUserIdentity();
    if (!identite) throw new Error('Non authentifié');
    await ctx.db.insert('leads', { email: args.email, source: 'site', proprietaire: identite.subject });
  },
});

export const lister = query({
  args: { limite: v.number() },
  handler: async (ctx, { limite }) => {
    const identite = await ctx.auth.getUserIdentity();
    if (!identite) return [];
    return await ctx.db.query('leads').withIndex('par_proprietaire', (q) => q.eq('proprietaire', identite.subject)).take(limite);
  },
});
