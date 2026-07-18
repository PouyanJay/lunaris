import "@fontsource/geist-sans/400.css";
import "@fontsource/geist-sans/500.css";
import "@fontsource/geist-sans/600.css";
import "@fontsource/geist-mono/400.css";
import "@fontsource/geist-mono/500.css";
import "@xyflow/react/dist/style.css";
import "./index.css";

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import App from "./App";
import { ErrorBoundary } from "./components/states/ErrorBoundary";
import { registerCoverCache } from "./lib/coverCache";

// Cache constant cover artwork by content path, so a rotating signed-URL token never re-downloads
// identical images (production builds only; no-op in the dev server and where SWs are unavailable).
registerCoverCache();

const root = document.getElementById("root");
if (!root) throw new Error("Root element #root not found");

createRoot(root).render(
  <StrictMode>
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  </StrictMode>,
);
