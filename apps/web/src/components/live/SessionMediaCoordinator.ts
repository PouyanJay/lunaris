/** Coordinates only local media; stopping never submits an answer or starts a microphone. */
export class SessionMediaCoordinator {
  constructor(readonly scope: string = "") {}

  private readonly stops = new Map<string, () => void>();

  private readonly blocks = new Set<symbol>();
  private readonly listeners = new Set<() => void>();

  readonly isBlocked = (): boolean => this.blocks.size > 0;
  readonly subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  };

  block(reason: string): () => void {
    const token = Symbol(reason);
    this.blocks.add(token);
    this.stopAll();
    this.listeners.forEach((listener) => listener());
    return () => {
      this.blocks.delete(token);
      this.listeners.forEach((listener) => listener());
    };
  }

  register(owner: string, stop: () => void): () => void {
    this.stops.get(owner)?.();
    this.stops.set(owner, stop);
    return () => {
      if (this.stops.get(owner) === stop) this.stops.delete(owner);
    };
  }

  activate(owner: string): boolean {
    if (this.isBlocked()) return false;
    for (const [registered, stop] of this.stops) {
      if (registered !== owner) stop();
    }
    return true;
  }

  stopAll(): void {
    for (const stop of this.stops.values()) stop();
  }
}
