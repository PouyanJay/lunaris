import "@testing-library/jest-dom/vitest";

import { clearCoverViews } from "../hooks/coverViewCache";
import { clearLibraryCache } from "../hooks/libraryCache";
import { clearSeenImages } from "../lib/imageCache";

// React Flow measures node geometry with ResizeObserver, which jsdom lacks.
class ResizeObserverStub {
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
}

globalThis.ResizeObserver ??= ResizeObserverStub as unknown as typeof ResizeObserver;

// React Flow reads matchMedia for color-mode detection; jsdom doesn't implement it.
globalThis.matchMedia ??= ((query: string) => ({
  matches: false,
  media: query,
  onchange: null,
  addEventListener: () => {},
  removeEventListener: () => {},
  addListener: () => {},
  removeListener: () => {},
  dispatchEvent: () => false,
})) as unknown as typeof globalThis.matchMedia;

// jsdom's localStorage isn't a usable Storage on the default opaque origin (it lacks the Storage
// methods), so persistence-backed hooks can't round-trip. Install a deterministic in-memory Storage.
class MemoryStorage implements Storage {
  private store = new Map<string, string>();
  get length(): number {
    return this.store.size;
  }
  clear(): void {
    this.store.clear();
  }
  getItem(key: string): string | null {
    return this.store.has(key) ? this.store.get(key)! : null;
  }
  key(index: number): string | null {
    return Array.from(this.store.keys())[index] ?? null;
  }
  removeItem(key: string): void {
    this.store.delete(key);
  }
  setItem(key: string, value: string): void {
    this.store.set(key, String(value));
  }
}

Object.defineProperty(globalThis, "localStorage", {
  value: new MemoryStorage(),
  writable: true,
  configurable: true,
});

// One shared store spans the whole run, so reset it after every test — a persisted write in one
// test (e.g. the sidebar's collapse/width preference) must never leak into the next and flip its
// initial state. (`afterEach` is a Vitest global; `globals: true` is set in vite.config.)
afterEach(() => localStorage.clear());

// Routing tests (and any router-driven interaction) mutate the jsdom URL, which persists across
// tests in a file — reset it so every test starts from "/" regardless of what ran before.
afterEach(() => window.history.replaceState(null, "", "/"));

// The module-scoped caches survive navigation in the app by design, so state from one test must not
// carry into the next — reset them like the other shared stores: the library's SWR cache, the
// per-job cover-exchange cache, and the seen-images set that skips the cover crossfade.
afterEach(() => {
  clearLibraryCache();
  clearCoverViews();
  clearSeenImages();
});
