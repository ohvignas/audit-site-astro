import { mutation, query } from './_generated/server';
import { v } from 'convex/values';

export const creer = mutation({
  args: { email: v.string() },
  handler: async (ctx, args) => {
    await ctx.db.insert('leads', { email: args.email, source: 'site' });
  },
});

export const lister = query({
  handler: async (ctx) => {
    return await ctx.db.query('leads')
      .filter((q) => q.neq(q.field('email'), ''))
      .collect();
  },
});
