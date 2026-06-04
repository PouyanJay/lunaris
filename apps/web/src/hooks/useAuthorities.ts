import { useCallback, useEffect, useRef, useState } from "react";

import { AuthoritiesError, fetchAuthorities } from "../lib/authorities";
import type { SourceAuthority } from "../types/course";

export type AuthoritiesState =
  | { status: "loading" }
  | { status: "empty" }
  | { status: "ready"; authorities: SourceAuthority[] }
  | { status: "error"; message: string };

interface Authorities {
  state: AuthoritiesState;
  reload: () => void;
}

/** Load the global trust-config rows, with reload (used after an upsert/delete). */
export function useAuthorities(apiBaseUrl: string): Authorities {
  const [state, setState] = useState<AuthoritiesState>({ status: "loading" });
  const controllerRef = useRef<AbortController | null>(null);

  const load = useCallback(() => {
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;
    setState({ status: "loading" });

    fetchAuthorities(apiBaseUrl, controller.signal)
      .then((authorities) => {
        if (controller.signal.aborted) return;
        setState(authorities.length === 0 ? { status: "empty" } : { status: "ready", authorities });
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        const message =
          error instanceof AuthoritiesError ? error.message : "Couldn't load trusted sources.";
        setState({ status: "error", message });
      });
  }, [apiBaseUrl]);

  useEffect(() => {
    load();
    return () => controllerRef.current?.abort();
  }, [load]);

  return { state, reload: load };
}
