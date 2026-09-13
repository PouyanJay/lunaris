import { createRoot } from "react-dom/client";
import { SessionView } from "../src/components/live/SessionView";
import { AuthProvider } from "../src/hooks/useAuth";
import { authedFetch } from "../src/lib/apiClient";
import "../src/index.css";
const query = new URLSearchParams(location.search);
const api = query.get("api")!;
const copilot = query.get("copilot");
const seeded = await (await authedFetch(`${api}/test/session`, { method: "POST" })).json();
createRoot(document.getElementById("root")!).render(
  <AuthProvider>
    <SessionView
      apiBaseUrl={api}
      graphId={seeded.graphId}
      topic="Functions"
      {...(copilot ? { copilotUrl: copilot } : {})}
    />
  </AuthProvider>,
);
