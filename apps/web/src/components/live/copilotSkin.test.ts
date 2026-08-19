import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

/** AD1 / AD35: the CopilotKit panel takes the kit's machinery and none of its skin. Two things
 *  make that true, and both are facts about source rather than about a rendered DOM, so they are
 *  pinned here where jsdom cannot help:
 *
 *  1. The kit's stylesheet is never imported. Beyond its `--copilot-kit-*` custom properties it
 *     carries a system font stack, pill radii, hover motion and a vendor tag that no property
 *     reaches — loading it and binding the properties would still inherit the skin.
 *  2. Everything the panel paints comes from tokens: its stylesheets carry no colour literal.
 *
 *  Limits, stated: (1) is a literal match on the two published specifiers, so a re-export, an alias
 *  or a differently-spelled subpath would slip past it; (2) reads only the three panel stylesheets
 *  named below, so a new one must be added here to be guarded. */

const SRC_ROOT = join(__dirname, "..", "..");
const KIT_STYLESHEETS = [
  "@copilotkit/react-ui/styles.css",
  "@copilotkit/react-ui/v2/styles.css",
  // Not a stylesheet, but it imports one: `@copilotkit/react-core/v2` (the entry that exports
  // `useCopilotKit` / `useAgent`) pulls in the kit's 90 kB Tailwind sheet on import. Found in T9,
  // reaching for `setProperties`; the root entry's `properties` prop is the seam instead. Its
  // `/v2/headless` sibling is CSS-free but carries its own context, so hooks from it cannot see
  // the root provider, forbidden by the same prefix.
  "@copilotkit/react-core/v2",
];
const PANEL_STYLESHEETS = [
  "CopilotSession.module.css",
  "CopilotSlots.module.css",
  "Speech.module.css",
].map((name) => join(__dirname, name));

function walk(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const path = join(dir, entry.name);
    return entry.isDirectory() ? walk(path) : [path];
  });
}

describe("the CopilotKit panel's skin", () => {
  it("never loads the kit's own stylesheet", () => {
    const importers = walk(SRC_ROOT)
      .filter((file) => /\.(tsx?|css)$/.test(file) && !file.includes(".test."))
      .filter((file) => {
        const source = readFileSync(file, "utf8");
        return KIT_STYLESHEETS.some((sheet) => source.includes(sheet));
      })
      .map((file) => file.replace(SRC_ROOT, "src"));

    expect(importers, `the kit's stylesheet is imported by: ${importers.join(", ")}`).toEqual([]);
  });

  it.each(PANEL_STYLESHEETS)("%s paints from tokens only, no colour literals", (stylesheet) => {
    const css = readFileSync(stylesheet, "utf8").replace(/\/\*[\s\S]*?\*\//g, "");
    const literals = [...css.matchAll(/#[0-9a-f]{3,8}\b|\b(?:rgba?|hsla?|oklch|color)\(/gi)].map(
      (match) => match[0],
    );

    expect(literals, `colour literals in ${stylesheet}: ${literals.join(", ")}`).toEqual([]);
  });
});
