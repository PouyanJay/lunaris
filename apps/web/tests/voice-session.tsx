import { createRoot } from "react-dom/client";
import { SessionView } from "../src/components/live/SessionView";
import { authedFetch } from "../src/lib/apiClient";
import "../src/index.css";
const api = new URLSearchParams(location.search).get("api")!;
const seeded = await (await authedFetch(`${api}/test/session`, { method: "POST" })).json();
createRoot(document.getElementById("root")!).render(
  <SessionView apiBaseUrl={api} graphId={seeded.graphId} topic="Functions" />,
);
