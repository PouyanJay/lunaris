import type { User } from "@supabase/supabase-js";

import { displayNameFromEmail } from "./greeting";

/** The name shown for the signed-in account. Prefers a user-set `display_name` (persisted in
 *  Supabase user_metadata via the Profile screen); falls back to a friendly name derived from the
 *  sign-in email so the account row always reads naturally, even before a name is chosen. */
export function resolveDisplayName(user: User | null): string {
  const raw = user?.user_metadata?.["display_name"];
  const stored = typeof raw === "string" ? raw.trim() : "";
  return stored || displayNameFromEmail(user?.email);
}
