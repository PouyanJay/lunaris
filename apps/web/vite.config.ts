import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    css: false,
    // Force auth OFF in tests: the App/AuthGate suites assume the single-user, no-login path. A
    // developer's local .env (e.g. VITE_SUPABASE_* for `make run` against cloud auth) would
    // otherwise flip the AuthGate on under jsdom and hang the app on the session check. Blanking
    // these here (overriding any loaded .env) keeps the suite deterministic.
    env: { VITE_SUPABASE_URL: "", VITE_SUPABASE_ANON_KEY: "" },
  },
});
