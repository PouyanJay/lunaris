/** The time-of-day bucket for the Home greeting, from a local 0–23 hour. Morning < 12,
 *  afternoon < 18, evening otherwise. */
export type GreetingPart = "morning" | "afternoon" | "evening";

export function greetingForHour(hour: number): GreetingPart {
  if (hour < 12) return "morning";
  if (hour < 18) return "afternoon";
  return "evening";
}

/** A friendly display name from a sign-in email — the local-part, split on separators and
 *  title-cased ("ada.lovelace@x.com" → "Ada Lovelace"). Falls back to "there" for an empty or
 *  address-less email, so the greeting always reads naturally. This is the fallback when no
 *  profile display_name is set — see resolveDisplayName in lib/profile.ts. */
export function displayNameFromEmail(email: string | null | undefined): string {
  const local = email?.split("@")[0]?.trim();
  if (!local) return "there";
  const name = local
    .split(/[._-]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
  return name || "there";
}
