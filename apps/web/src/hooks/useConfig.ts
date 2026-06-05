import { useCallback, useEffect, useRef, useState } from "react";

import { ConfigError, fetchConfig, type ConfigSetting } from "../lib/config";

export type ConfigState =
  | { status: "loading" }
  | { status: "ready"; settings: ConfigSetting[] }
  | { status: "error"; message: string };

interface Config {
  state: ConfigState;
  /** Replace one setting in place after a successful save (no full refetch). */
  apply: (updated: ConfigSetting) => void;
  reload: () => void;
}

/** Load the non-secret configuration settings, with reload + an in-place apply after a save. */
export function useConfig(apiBaseUrl: string): Config {
  const [state, setState] = useState<ConfigState>({ status: "loading" });
  const controllerRef = useRef<AbortController | null>(null);

  const load = useCallback(() => {
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;
    setState({ status: "loading" });

    fetchConfig(apiBaseUrl, controller.signal)
      .then((settings) => {
        if (controller.signal.aborted) return;
        setState({ status: "ready", settings });
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        const message =
          error instanceof ConfigError ? error.message : "Couldn't load configuration.";
        setState({ status: "error", message });
      });
  }, [apiBaseUrl]);

  useEffect(() => {
    load();
    return () => controllerRef.current?.abort();
  }, [load]);

  const apply = useCallback((updated: ConfigSetting) => {
    setState((prev) =>
      prev.status === "ready"
        ? {
            status: "ready",
            settings: prev.settings.map((s) => (s.name === updated.name ? updated : s)),
          }
        : prev,
    );
  }, []);

  return { state, apply, reload: load };
}
