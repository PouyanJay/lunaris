import { describe, expect, it } from "vitest";

import { displayNameFromEmail, greetingForHour } from "./greeting";

describe("greetingForHour", () => {
  it("buckets the day into morning / afternoon / evening", () => {
    expect(greetingForHour(0)).toBe("morning");
    expect(greetingForHour(11)).toBe("morning");
    expect(greetingForHour(12)).toBe("afternoon");
    expect(greetingForHour(17)).toBe("afternoon");
    expect(greetingForHour(18)).toBe("evening");
    expect(greetingForHour(23)).toBe("evening");
  });
});

describe("displayNameFromEmail", () => {
  it("title-cases the local part, splitting on separators", () => {
    expect(displayNameFromEmail("ada.lovelace@example.com")).toBe("Ada Lovelace");
    expect(displayNameFromEmail("grace_hopper@navy.mil")).toBe("Grace Hopper");
    expect(displayNameFromEmail("alan-turing@bletchley.uk")).toBe("Alan Turing");
    expect(displayNameFromEmail("pouyan@lunaris.ai")).toBe("Pouyan");
  });

  it("falls back to a natural default for empty or address-less input", () => {
    expect(displayNameFromEmail(null)).toBe("there");
    expect(displayNameFromEmail(undefined)).toBe("there");
    expect(displayNameFromEmail("")).toBe("there");
    expect(displayNameFromEmail("@example.com")).toBe("there");
  });
});
