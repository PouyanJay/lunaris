import js from "@eslint/js";
import globals from "globals";
import tseslint from "typescript-eslint";

/** Lint for the CopilotKit runtime service.
 *
 *  Deliberately a sibling of `apps/web/eslint.config.js` rather than a shared config: this is a
 *  Node service with no React and no browser globals, so the two differ in exactly the places that
 *  matter, and a merged config would need per-directory overrides to say the same thing.
 */
export default tseslint.config(
  { ignores: ["dist", "coverage"] },
  {
    extends: [js.configs.recommended, ...tseslint.configs.recommended],
    files: ["**/*.ts"],
    languageOptions: {
      ecmaVersion: 2022,
      globals: globals.node,
    },
    rules: {
      "@typescript-eslint/no-unused-vars": ["error", { argsIgnorePattern: "^_" }],
    },
  },
);
