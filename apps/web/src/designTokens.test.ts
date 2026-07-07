import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

/** Token integrity: every CSS custom property referenced anywhere in src/ must be defined
 *  somewhere (index.css tokens, a component-scoped property in a module.css, or an inline
 *  style / setProperty in TSX). A `var(--x, fallback)` reference is exempt — the fallback
 *  makes it self-sufficient. Guards against silently-dead styles: an undefined token makes
 *  the declaration invalid at computed-value time, which the browser hides and jsdom never
 *  sees. */

const SRC_ROOT = join(__dirname);

function walk(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) return walk(path);
    return [path];
  });
}

function collect(): { defined: Set<string>; required: Map<string, Set<string>> } {
  const files = walk(SRC_ROOT);
  const defined = new Set<string>();
  // token name -> files that reference it without a fallback
  const required = new Map<string, Set<string>>();

  const requireToken = (name: string, file: string) => {
    const holders = required.get(name) ?? new Set<string>();
    holders.add(file.replace(SRC_ROOT, "src"));
    required.set(name, holders);
  };

  for (const file of files) {
    if (file.endsWith(".css")) {
      const css = readFileSync(file, "utf8");
      for (const [, name] of css.matchAll(/(--[a-z0-9-]+)\s*:/g)) defined.add(name ?? "");
      for (const [, name, close] of css.matchAll(/var\(\s*(--[a-z0-9-]+)\s*([,)])/g)) {
        if (name && close === ")") requireToken(name, file);
      }
    } else if (/\.(tsx?|jsx?)$/.test(file) && !file.includes(".test.")) {
      const source = readFileSync(file, "utf8");
      // Inline style objects ({ "--x": … }) and element.style.setProperty("--x", …).
      for (const [, name] of source.matchAll(/["'](--[a-z0-9-]+)["']\s*[:,]/g))
        defined.add(name ?? "");
    }
  }
  return { defined, required };
}

describe("design tokens", () => {
  it("defines every custom property referenced without a fallback", () => {
    const { defined, required } = collect();

    const missing = [...required.entries()]
      .filter(([name]) => !defined.has(name))
      .map(([name, holders]) => `${name} (referenced in ${[...holders].join(", ")})`);

    expect(missing, `undefined design tokens:\n  ${missing.join("\n  ")}`).toEqual([]);
  });
});
