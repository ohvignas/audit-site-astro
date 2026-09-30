import { defineSchema, defineTable } from 'convex/server';
import { v } from 'convex/values';
export default defineSchema({
  leads: defineTable({ email: v.string(), source: v.any() }),
});
