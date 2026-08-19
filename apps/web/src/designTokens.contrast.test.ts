import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

/** Token contrast: the (text, surface) pairs the product actually paints must clear WCAG 2.2 AA
 *  (4.5:1 for text) in BOTH themes, computed from the token values in `index.css` rather than
 *  eyeballed. jsdom never resolves a colour, so without this a token that fails AA on one theme
 *  ships green — which is exactly what happened to `--text-muted` on dark (2.81:1, measured during
 *  T5 of the live-generative-surfaces journey and parked here for T7).
 *
 *  Pairs are the ones the shared primitives and the Live session surfaces put together. Adding a
 *  pair is the way to bring a new surface under the guard; a pair that fails is a token to fix,
 *  never a component to special-case (diverging one component trades a legibility bug for an
 *  inconsistency bug). */

const INDEX_CSS = readFileSync(join(__dirname, "index.css"), "utf8");
const AA_TEXT = 4.5;

/** Every text token × every neutral ground it can sit on. `--field` is the composer's recessed
 *  ground and `--bg-muted` is the hover/raised step, both of which carry muted text (placeholders,
 *  eyebrows inside a hovered row), so they are grounds rather than exceptions. */
const NEUTRAL_GROUNDS = [
  "--bg",
  "--bg-subtle",
  "--bg-muted",
  "--surface",
  "--surface-raised",
  "--field",
  "--field-sub",
] as const;

const TEXT_ON_NEUTRALS = ["--text", "--text-secondary", "--text-muted"] as const;

/** Pairs with a narrower footprint than "any neutral ground": each names where it is painted. */
const NAMED_PAIRS: ReadonlyArray<{ text: string; ground: string; where: string }> = [
  // The eyebrow micro-label (`.eyebrow`, `--text-muted`) sits on the accent-soft band in banners.
  { text: "--text-muted", ground: "--accent-soft", where: ".eyebrow on an accent-soft banner" },
  // The composer's error hint (`AnswerForm .hint[role=alert]`) and the session's failure line.
  { text: "--danger", ground: "--surface", where: "AnswerForm error hint" },
  { text: "--danger", ground: "--surface-raised", where: "CopilotSession composer error hint" },
  { text: "--danger", ground: "--bg", where: "SessionView failure line" },
  // Accent-as-text is only sanctioned on the accent-soft band, via the 700 step.
  { text: "--accent-700", ground: "--accent-soft", where: "banner eyebrows/actions" },
];

type Theme = "light" | "dark";

/** The declarations of one theme block, `--name` → raw value (may itself be a `var(--x)`).
 *
 *  Sliced from the block's opening line to the first `\n}` after it, which is only right while
 *  both token blocks stay flat — no nested rules, no comment with a `}` at line start. They are
 *  today; a nested rule would truncate the block and surface here as "token not defined". */
function declarations(theme: Theme): Map<string, string> {
  const selector = theme === "light" ? ":root" : '[data-theme="dark"]';
  const start = INDEX_CSS.indexOf(`${selector} {`);
  expect(start, `no ${selector} block in index.css`).toBeGreaterThanOrEqual(0);
  const end = INDEX_CSS.indexOf("\n}", start);
  const block = INDEX_CSS.slice(start, end);
  const out = new Map<string, string>();
  for (const [, name, value] of block.matchAll(/(--[a-z0-9-]+)\s*:\s*([^;]+);/g)) {
    out.set(name!, value!.trim());
  }
  return out;
}

/** A token's hex value in a theme, following `var(--x)` references. The dark block only overrides,
 *  so a token it does not name resolves through the light block. */
function resolveHex(token: string, theme: Theme): string {
  const light = declarations("light");
  const dark = declarations("dark");
  let value = (theme === "dark" ? dark.get(token) : undefined) ?? light.get(token);
  for (let hops = 0; hops < 5 && value; hops += 1) {
    const ref = /^var\((--[a-z0-9-]+)\)$/.exec(value);
    if (!ref) break;
    value = (theme === "dark" ? dark.get(ref[1]!) : undefined) ?? light.get(ref[1]!);
  }
  expect(value, `${token} is not defined for the ${theme} theme`).toBeDefined();
  expect(value, `${token} (${theme}) resolves to ${value}, not a hex colour`).toMatch(
    /^#[0-9a-f]{6}$/i,
  );
  return value!;
}

/** WCAG 2.x relative luminance of an sRGB hex colour. */
function luminance(hex: string): number {
  const channel = (i: number) => {
    const c = parseInt(hex.slice(i, i + 2), 16) / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * channel(1) + 0.7152 * channel(3) + 0.0722 * channel(5);
}

/** WCAG contrast ratio, 1:1 (identical) to 21:1 (black on white). */
function contrastRatio(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x) as [number, number];
  return (hi + 0.05) / (lo + 0.05);
}

describe.each<Theme>(["light", "dark"])("design token contrast (%s theme)", (theme) => {
  it.each(TEXT_ON_NEUTRALS.flatMap((text) => NEUTRAL_GROUNDS.map((ground) => [text, ground])))(
    "%s on %s clears AA for text",
    (text, ground) => {
      const ratio = contrastRatio(resolveHex(text, theme), resolveHex(ground, theme));
      expect(
        ratio,
        `${text} on ${ground} (${theme}) is ${ratio.toFixed(2)}:1`,
      ).toBeGreaterThanOrEqual(AA_TEXT);
    },
  );

  it.each(NAMED_PAIRS)("$text on $ground clears AA for text ($where)", ({ text, ground }) => {
    const ratio = contrastRatio(resolveHex(text, theme), resolveHex(ground, theme));
    expect(
      ratio,
      `${text} on ${ground} (${theme}) is ${ratio.toFixed(2)}:1`,
    ).toBeGreaterThanOrEqual(AA_TEXT);
  });

  it("keeps the three text weights in order, so muted still reads as muted", () => {
    // Raising the muted step to clear AA must not collapse it into the secondary step: the
    // hierarchy is what the eyebrow / body / caption rhythm rests on.
    const ground = resolveHex("--surface", theme);
    const text = contrastRatio(resolveHex("--text", theme), ground);
    const secondary = contrastRatio(resolveHex("--text-secondary", theme), ground);
    const muted = contrastRatio(resolveHex("--text-muted", theme), ground);
    expect(text).toBeGreaterThan(secondary);
    expect(secondary).toBeGreaterThan(muted);
  });
});

describe("the contrast arithmetic itself", () => {
  // The guard is only as good as its formula, so the formula is pinned to the two values everyone
  // knows: black on white is 21:1, and a colour against itself is 1:1.
  it("reports 21:1 for black on white and 1:1 for a colour on itself", () => {
    expect(contrastRatio("#000000", "#ffffff")).toBeCloseTo(21, 5);
    expect(contrastRatio("#c8860f", "#c8860f")).toBeCloseTo(1, 5);
  });
});
