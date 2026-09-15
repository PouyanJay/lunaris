import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router";
import LiveShell from "../src/components/live/LiveShell";
import { AuthProvider } from "../src/hooks/useAuth";
import "../src/index.css";

const api = new URLSearchParams(location.search).get("api")!;
createRoot(document.getElementById("root")!).render(
  <AuthProvider>
    <BrowserRouter>
      <LiveShell apiBaseUrl={api} />
    </BrowserRouter>
  </AuthProvider>,
);
