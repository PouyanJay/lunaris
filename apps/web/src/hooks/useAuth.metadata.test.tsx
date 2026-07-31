import { renderHook } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

// The real metadata-write path — previously only ever reached through a mocked `useAuth`, so the
// body that actually talks to Supabase (and the shape of what it writes) was never executed.
const { updateUser, getSession, onAuthStateChange } = vi.hoisted(() => ({
  updateUser: vi.fn(),
  getSession: vi.fn(),
  onAuthStateChange: vi.fn(),
}));

vi.mock("../lib/supabase", () => ({
  supabase: { auth: { updateUser, getSession, onAuthStateChange } },
}));

import { AuthProvider, useAuth } from "./useAuth";

function wrapper({ children }: { children: ReactNode }) {
  return <AuthProvider>{children}</AuthProvider>;
}

describe("useAuth — metadata writes", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    getSession.mockResolvedValue({ data: { session: null } });
    onAuthStateChange.mockReturnValue({ data: { subscription: { unsubscribe: vi.fn() } } });
    updateUser.mockResolvedValue({ error: null });
  });

  it("writes the remembered product under the key the reader looks for", async () => {
    const { result } = renderHook(() => useAuth(), { wrapper });

    await result.current.updateLastProduct("live");

    // `last_product` is the same constant `resolveLastProduct` reads, so a rename cannot silently
    // split the write path from the read path.
    expect(updateUser).toHaveBeenCalledWith({ data: { last_product: "live" } });
  });

  it("writes the display name without disturbing the product", async () => {
    const { result } = renderHook(() => useAuth(), { wrapper });

    await result.current.updateDisplayName("Ada");

    // A patch, not a replacement: Supabase merges `data`, so writing one field must not name the
    // other. Sending both would let a stale display name clobber a fresh product, and vice versa.
    expect(updateUser).toHaveBeenCalledWith({ data: { display_name: "Ada" } });
  });

  it("surfaces a rejected write to the caller", async () => {
    updateUser.mockResolvedValue({ error: new Error("offline") });
    const { result } = renderHook(() => useAuth(), { wrapper });

    await expect(result.current.updateLastProduct("studio")).rejects.toThrow("offline");
  });
});
