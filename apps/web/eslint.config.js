import js from "@eslint/js";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";
import globals from "globals";
import tseslint from "typescript-eslint";

export default tseslint.config(
  { ignores: ["dist", "coverage"] },
  {
    extends: [js.configs.recommended, ...tseslint.configs.recommended],
    files: ["**/*.{ts,tsx}"],
    languageOptions: {
      ecmaVersion: 2022,
      globals: globals.browser,
    },
    plugins: {
      "react-hooks": reactHooks,
      "react-refresh": reactRefresh,
    },
    rules: {
      ...reactHooks.configs.recommended.rules,
      "react-refresh/only-export-components": ["warn", { allowConstantExport: true }],
      "@typescript-eslint/no-unused-vars": ["error", { argsIgnorePattern: "^_" }],
    },
  },
  {
    files: ["**/*.test.{ts,tsx}", "src/test/**"],
    languageOptions: { globals: { ...globals.browser, ...globals.node } },
  },
  // ─── The one-way product boundary ────────────────────────────────────────────────────────────
  // Lunaris Live may build on Studio's shared foundations; Studio must never depend on Live. That
  // is the whole basis for keeping the two products in one repo — Live can be flagged off, broken,
  // or lifted into its own repo without Studio noticing. A convention would rot silently and drag
  // Live's dependencies into Studio's bundle, so it is enforced here instead.
  //
  // components/gateway/ is the single sanctioned crossing: it is the fork, so it necessarily knows
  // both sides, and it reaches Live only through a lazy import that keeps the bundles split.
  {
    files: ["src/**/*.{ts,tsx}"],
    ignores: ["src/components/live/**", "src/components/gateway/**"],
    rules: {
      "no-restricted-imports": [
        "error",
        {
          patterns: [
            {
              // Matched against the import specifier as written, which is relative — so this keys
              // on the `live/` directory segment rather than a `components/live` prefix that only
              // appears in absolute paths.
              group: ["**/live", "**/live/*", "**/live/**"],
              message:
                "Studio must not import Lunaris Live. Live depends on Studio's foundations, never the reverse — route through components/gateway/, which owns the fork.",
            },
          ],
        },
      ],
    },
  },
);
