/** The on-device model engine ("This device" in the compute dropdown): Qwen2.5-3B over WebGPU
 *  via WebLLM, downloaded once (~1.8 GB, cached by the browser) and reused for every call on the
 *  page. One engine serves both surfaces: one-shot lesson explains and the build bridge's
 *  completions (the tab answering a device-compute Draft build). WebLLM is imported dynamically so
 *  the main bundle never pays for it; jsdom tests inject a fake loader. */

/** The pinned prebuilt artifact — the same model family/size as the server's Draft tier, so the
 *  two compute choices answer with comparable quality. */
export const DEVICE_MODEL_ID = "Qwen2.5-3B-Instruct-q4f16_1-MLC";

/** The model name as surfaces display it (the Draft banner's language-model cell while "This
 *  device" is the chosen compute) — the human name of DEVICE_MODEL_ID's family/size. */
export const DEVICE_MODEL_LABEL = "Qwen2.5-3B";

// Mirrors the server explainer's bounds (schemas/explain.py) — one block, never an unbounded prompt.
const MAX_CONTENT = 8000;
const MAX_CONTEXT = 400;

const EXPLAIN_PROMPT =
  "You are explaining a piece of a lesson to a curious learner. In 2-4 plain sentences, say what " +
  "it means and why it matters for what they're learning. Do not repeat it verbatim, and do not " +
  "output code or JSON.\n\nBlock context: {context}\n\nContent:\n{content}";

export interface DeviceProgress {
  /** 0..1 — WebLLM reports real fetch progress, so the UI can draw a determinate bar. */
  progress: number;
  text: string;
}

/** One OpenAI-style chat message — the bridge's wire shape, consumed by WebLLM directly. */
export interface ChatMessage {
  role: string;
  content: string;
}

export interface ChatBackend {
  chat(messages: ChatMessage[]): Promise<string>;
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
    chat: async (messages: ChatMessage[]) => {
      const reply = await engine.chat.completions.create({
        messages: messages as Parameters<
          typeof engine.chat.completions.create
        >[0]["messages"],
      });
      return reply.choices[0]?.message?.content ?? "";
    },
  };
};

export class DeviceEngine {
  private readonly loader: BackendLoader;
  private backendPromise: Promise<ChatBackend> | null = null;
  private progressListeners = new Set<(progress: DeviceProgress) => void>();

  constructor(loader: BackendLoader = webLlmLoader) {
    this.loader = loader;
  }

  /** Run one chat completion on this device. The first call (per page) downloads + boots the
   *  model, reporting progress to `onProgress`; later calls reuse the booted backend. */
  async chat(
    messages: ChatMessage[],
    onProgress?: (progress: DeviceProgress) => void,
  ): Promise<string> {
    if (onProgress) this.progressListeners.add(onProgress);
    try {
      const backend = await this.ensureBackend();
      return (await backend.chat(messages)).trim();
    } finally {
      if (onProgress) this.progressListeners.delete(onProgress);
    }
  }

  /** Download + boot the model WITHOUT running a completion — the device build flow front-loads
   *  the ~1.8 GB fetch (with a visible progress bar) before the build starts, so the server never
   *  waits out a first-time download mid-run. */
  async preload(onProgress?: (progress: DeviceProgress) => void): Promise<void> {
    if (onProgress) this.progressListeners.add(onProgress);
    try {
      await this.ensureBackend();
    } finally {
      if (onProgress) this.progressListeners.delete(onProgress);
    }
  }

  /** One-shot explain (the reader's Explain affordance) — a single prompted chat turn. */
  async explain(
    content: string,
    context: string | undefined,
    onProgress?: (progress: DeviceProgress) => void,
  ): Promise<string> {
    const prompt = EXPLAIN_PROMPT.replace(
      "{context}",
      (context ?? "(none)").slice(0, MAX_CONTEXT),
    ).replace("{content}", content.slice(0, MAX_CONTENT));
    return this.chat([{ role: "user", content: prompt }], onProgress);
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

// One engine per page: explains and the build bridge share the single downloaded model.
let pageEngine: DeviceEngine | null = null;

export function getDeviceEngine(): DeviceEngine {
  if (pageEngine === null) pageEngine = new DeviceEngine();
  return pageEngine;
}
