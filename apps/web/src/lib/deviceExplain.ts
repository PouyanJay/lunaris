/** The on-device explain engine ("This device" in the compute dropdown): Qwen2.5-3B over WebGPU
 *  via WebLLM, downloaded once (~1.8 GB, cached by the browser) and reused for every explain on
 *  the page. WebLLM is imported dynamically so the main bundle never pays for it; jsdom tests
 *  inject a fake loader. The Phase 2 build bridge reuses this engine seam. */

/** The pinned prebuilt artifact — the same model family/size as the server's Draft tier, so the
 *  two compute choices answer with comparable quality. */
export const DEVICE_MODEL_ID = "Qwen2.5-3B-Instruct-q4f16_1-MLC";

// Mirrors the server explainer's bounds (schemas/explain.py) — one block, never an unbounded prompt.
const MAX_CONTENT = 8000;
const MAX_CONTEXT = 400;

const PROMPT =
  "You are explaining a piece of a lesson to a curious learner. In 2-4 plain sentences, say what " +
  "it means and why it matters for what they're learning. Do not repeat it verbatim, and do not " +
  "output code or JSON.\n\nBlock context: {context}\n\nContent:\n{content}";

export interface DeviceProgress {
  /** 0..1 — WebLLM reports real fetch progress, so the UI can draw a determinate bar. */
  progress: number;
  text: string;
}

export interface ChatBackend {
  complete(prompt: string): Promise<string>;
}

export type BackendLoader = (
  modelId: string,
  onProgress: (progress: DeviceProgress) => void,
) => Promise<ChatBackend>;

/** The real loader: dynamic-imports WebLLM and boots the pinned model on this device's GPU. */
const webLlmLoader: BackendLoader = async (modelId, onProgress) => {
  const { CreateMLCEngine } = await import("@mlc-ai/web-llm");
  const engine = await CreateMLCEngine(modelId, {
    initProgressCallback: (report) => {
      onProgress({ progress: report.progress, text: report.text });
    },
  });
  return {
    complete: async (prompt: string) => {
      const reply = await engine.chat.completions.create({
        messages: [{ role: "user", content: prompt }],
      });
      return reply.choices[0]?.message?.content ?? "";
    },
  };
};

export class DeviceExplainEngine {
  private readonly loader: BackendLoader;
  private backendPromise: Promise<ChatBackend> | null = null;
  private progressListeners = new Set<(progress: DeviceProgress) => void>();

  constructor(loader: BackendLoader = webLlmLoader) {
    this.loader = loader;
  }

  /** One-shot explain. The first call (per page) downloads + boots the model, reporting progress
   *  to `onProgress`; later calls reuse the booted backend. A failed load clears the shared
   *  promise so a retry starts a fresh download instead of replaying the failure forever. */
  async explain(
    content: string,
    context: string | undefined,
    onProgress?: (progress: DeviceProgress) => void,
  ): Promise<string> {
    if (onProgress) this.progressListeners.add(onProgress);
    try {
      const backend = await this.ensureBackend();
      const prompt = PROMPT.replace("{context}", (context ?? "(none)").slice(0, MAX_CONTEXT)).replace(
        "{content}",
        content.slice(0, MAX_CONTENT),
      );
      return (await backend.complete(prompt)).trim();
    } finally {
      if (onProgress) this.progressListeners.delete(onProgress);
    }
  }

  private ensureBackend(): Promise<ChatBackend> {
    if (this.backendPromise === null) {
      this.backendPromise = this.loader(DEVICE_MODEL_ID, (progress) => {
        for (const listener of this.progressListeners) listener(progress);
      }).catch((error: unknown) => {
        this.backendPromise = null; // a failed download must not be cached as "the engine"
        throw error;
      });
    }
    return this.backendPromise;
  }
}

// One engine per page: every block shares the single downloaded model.
let pageEngine: DeviceExplainEngine | null = null;

export function getDeviceExplainEngine(): DeviceExplainEngine {
  if (pageEngine === null) pageEngine = new DeviceExplainEngine();
  return pageEngine;
}
