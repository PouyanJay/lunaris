import { useCallback, useState } from "react";

import { ConfigError, updateConfig, type ConfigSetting } from "../lib/config";

export interface SaveFeedback {
  tone: "ok" | "error";
  message: string;
}

interface SaveOptions {
  /** When the value is read at process start (langsmith), a save needs a restart to take effect. */
  restartRequired?: boolean;
}

export interface ConfigSaver {
  /** Persist one config value, applying it in place on success and recording per-key busy/feedback. */
  save: (name: string, value: string, opts?: SaveOptions) => Promise<void>;
  busy: Record<string, boolean>;
  feedback: Record<string, SaveFeedback>;
}

/** Shared save behaviour for the config panels (model selection + the video section): optimistic
 *  per-key busy + a success/error message, applying the returned setting in place after a PUT. One
 *  place so both panels confirm a save identically. */
export function useConfigSaver(
  apiBaseUrl: string,
  apply: (updated: ConfigSetting) => void,
): ConfigSaver {
  const [busy, setBusy] = useState<Record<string, boolean>>({});
  const [feedback, setFeedback] = useState<Record<string, SaveFeedback>>({});

  const save = useCallback(
    async (name: string, value: string, opts?: SaveOptions) => {
      setBusy((prev) => ({ ...prev, [name]: true }));
      setFeedback(({ [name]: _removed, ...rest }) => rest);
      try {
        apply(await updateConfig(apiBaseUrl, name, value));
        const message = opts?.restartRequired ? "Saved — restart to apply" : "Saved";
        setFeedback((prev) => ({ ...prev, [name]: { tone: "ok", message } }));
      } catch (error: unknown) {
        const message = error instanceof ConfigError ? error.message : "Couldn't save.";
        setFeedback((prev) => ({ ...prev, [name]: { tone: "error", message } }));
      } finally {
        setBusy((prev) => ({ ...prev, [name]: false }));
      }
    },
    [apiBaseUrl, apply],
  );

  return { save, busy, feedback };
}
