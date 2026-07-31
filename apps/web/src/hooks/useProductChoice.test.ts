import { act, renderHook } from "@testing-library/react";
import type { User } from "@supabase/supabase-js";
import { describe, expect, it, vi } from "vitest";

import { useProductChoice } from "./useProductChoice";

function userWith(metadata: Record<string, unknown>): User {
  return { user_metadata: metadata } as unknown as User;
}

describe("useProductChoice", () => {
  it("seeds from the account's remembered product", () => {
    const { result } = renderHook(() => useProductChoice(userWith({ last_product: "live" })));

    expect(result.current.product).toBe("live");
  });

  // The cross-account leak. This is a single-page app: AuthProvider never remounts on
  // sign-out/sign-in, so nothing re-seeds initial state. Without the resync, signing out of an
  // account that used Studio and into one that uses Live would strand the second learner in Studio,
  // in defiance of their own stored preference — and they would have no idea why.
  it("adopts the new account's product when the signed-in user changes", () => {
    const { result, rerender } = renderHook(({ user }) => useProductChoice(user), {
      initialProps: { user: userWith({ last_product: "studio" }) },
    });
    expect(result.current.product).toBe("studio");

    rerender({ user: userWith({ last_product: "live" }) });

    expect(result.current.product).toBe("live");
  });

  it("drops the previous account's product when the new one has none", () => {
    const { result, rerender } = renderHook(({ user }) => useProductChoice(user), {
      initialProps: { user: userWith({ last_product: "live" }) },
    });

    rerender({ user: userWith({}) });

    // Null, not inherited — which routes this account to the gateway to choose for themselves.
    expect(result.current.product).toBeNull();
  });

  it("applies a choice immediately, without waiting on the write", async () => {
    // A slow round trip must not delay the decision: the redirect reads local state, and waiting
    // would bounce the user back to the gateway for the length of the request.
    const persist = vi.fn().mockReturnValue(new Promise<void>(() => {}));
    const { result } = renderHook(() => useProductChoice(userWith({}), persist));

    await act(async () => result.current.choose("live"));

    expect(result.current.product).toBe("live");
    expect(persist).toHaveBeenCalledWith("live");
  });

  it("keeps the choice when the write rejects, and does not throw", async () => {
    const persist = vi.fn().mockRejectedValue(new Error("offline"));
    const { result } = renderHook(() => useProductChoice(userWith({}), persist));

    await act(async () => result.current.choose("studio"));

    // Best-effort by design: the failure costs the learner nothing now, and the gateway simply
    // asks again next session. A rejected write must never surface as an unhandled rejection.
    expect(result.current.product).toBe("studio");
  });

  it("works with no persist implementation at all", async () => {
    const { result } = renderHook(() => useProductChoice(userWith({})));

    await act(async () => result.current.choose("live"));

    expect(result.current.product).toBe("live");
  });
});
