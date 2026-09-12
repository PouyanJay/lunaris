import { useContext, useEffect, useState } from "react";
import { authedFetch } from "../../lib/apiClient";
import { simDocument } from "../../lib/simDocument";
import { SimSessionContext } from "./SimSessionContext";

const ASSET_PATH = /^\/api\/live\/sims\/assets\/[0-9a-f-]{36}$/i;
type Loaded = { key: string; html?: string; failed: boolean };

/** Fetch private approved HTML through the host; credentials never enter the generated frame. */
export function useSimAsset(url: string) {
  const context = useContext(SimSessionContext);
  const approved = ASSET_PATH.test(url);
  const [loaded, setLoaded] = useState<Loaded | null>(null);
  const [attempt, setAttempt] = useState(0);
  const base = context?.apiBaseUrl ?? "";
  const key = `${base}:${context?.sessionId ?? ""}:${url}`;
  useEffect(() => {
    if (!approved) return;
    const controller = new AbortController();
    let current = true;
    const timeout = window.setTimeout(() => controller.abort(), 15000);
    void (async () => {
      try {
        const response = await authedFetch(base + url, {
          signal: controller.signal,
          redirect: "error",
        });
        if (!response.ok || !response.headers.get("Content-Type")?.startsWith("text/html"))
          throw new Error("Unavailable simulator");
        const html = await response.text();
        if (html.length > 500000) throw new Error("Oversized simulator");
        if (current)
          setLoaded({
            key,
            html: simDocument(html),
            failed: false,
          });
      } catch {
        if (current) setLoaded({ key, failed: true });
      } finally {
        window.clearTimeout(timeout);
      }
    })();
    return () => {
      current = false;
      controller.abort();
      window.clearTimeout(timeout);
    };
  }, [url, base, approved, attempt, key]);
  const result = loaded?.key === key ? loaded : null;
  return {
    src: approved ? undefined : url,
    srcDoc: approved ? result?.html : undefined,
    loading: approved && result === null,
    failed: approved && result?.failed === true,
    retry: () => {
      setLoaded(null);
      setAttempt((value) => value + 1);
    },
  };
}
