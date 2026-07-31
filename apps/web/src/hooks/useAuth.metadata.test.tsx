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

  it("writes the display name as a patch, not a replacement", async () => {
    const { result } = renderHook(() => useAuth(), { wrapper });

    await result.current.updateDisplayName("Ada");

    // Supabase merges `data`, so a write must name only its own field. Naming others would let a
    // stale value clobber a fresh one written elsewhere.
    expect(updateUser).toHaveBeenCalledWith({ data: { display_name: "Ada" } });
  });

  it("surfaces a rejected write to the caller", async () => {
    updateUser.mockResolvedValue({ error: new Error("offline") });
    const { result } = renderHook(() => useAuth(), { wrapper });

    await expect(result.current.updateDisplayName("Ada")).rejects.toThrow("offline");
  });
});
