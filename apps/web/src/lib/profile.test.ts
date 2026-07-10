import type { User } from "@supabase/supabase-js";
import { describe, expect, it } from "vitest";

import { resolveDisplayName } from "./profile";

/** A minimal User stand-in — resolveDisplayName only reads `email` and `user_metadata`. */
function makeUser(email: string | undefined, metadata: Record<string, unknown> = {}): User {
  return { email, user_metadata: metadata } as unknown as User;
}

describe("resolveDisplayName", () => {
  it("prefers a user-set display_name from metadata", () => {
    const user = makeUser("pj.autech@gmail.com", { display_name: "Pouyan" });
    expect(resolveDisplayName(user)).toBe("Pouyan");
  });

  it("trims a stored display_name", () => {
    const user = makeUser("pj.autech@gmail.com", { display_name: "  Pouyan  " });
    expect(resolveDisplayName(user)).toBe("Pouyan");
  });

  it("falls back to the email-derived name when no display_name is set", () => {
    const user = makeUser("pj.autech@gmail.com");
    expect(resolveDisplayName(user)).toBe("Pj Autech");
  });

  it("falls back when the stored display_name is blank or non-string", () => {
    expect(resolveDisplayName(makeUser("ada.lovelace@x.com", { display_name: "   " }))).toBe(
      "Ada Lovelace",
    );
    expect(resolveDisplayName(makeUser("ada.lovelace@x.com", { display_name: 42 }))).toBe(
      "Ada Lovelace",
    );
  });

  it("returns the natural default for a null user", () => {
    expect(resolveDisplayName(null)).toBe("there");
  });
});
