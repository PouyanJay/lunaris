import type { AuthChangeEvent, Session } from "@supabase/supabase-js";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import { AuthProvider } from "../../hooks/useAuth";
import { runsSent, stubCopilotRuntime } from "../../test/copilotRuntimeStub";
import { CopilotSession } from "./CopilotSession";

const auth = vi.hoisted(() => ({ getSession: vi.fn(), onAuthStateChange: vi.fn() }));
vi.mock("../../lib/supabase", () => ({ supabase: { auth } }));

afterEach(() => vi.unstubAllGlobals());

function session(token: string): Session {
  return {
    access_token: token,
    refresh_token: "fixture-refresh",
    expires_in: 3600,
    token_type: "bearer",
    user: {
      id: "learner",
      aud: "authenticated",
      app_metadata: {},
      user_metadata: {},
      created_at: "2026-09-12",
    },
  };
}

it("authenticates actual kit runs with the current session token and clears it on sign-out", async () => {
  auth.getSession.mockResolvedValue({ data: { session: session("first-token") } });
  let changed: (event: AuthChangeEvent, value: Session | null) => void = () => {};
  auth.onAuthStateChange.mockImplementation((listener) => {
    changed = listener;
    return { data: { subscription: { unsubscribe: vi.fn() } } };
  });
  stubCopilotRuntime();
  render(
    <AuthProvider>
      <CopilotSession
        runtimeUrl="http://runtime.test"
        sessionId="sess-auth"
        topic="Ohm's law"
        standingTurn="What happens when voltage doubles?"
        standingSeq={1}
      />
    </AuthProvider>,
  );
  const box = await screen.findByRole("textbox", { name: /your answer/i });
  for (const [index, token] of ["first-token", "refreshed-token", null].entries()) {
    if (index > 0)
      await act(async () =>
        changed(token ? "TOKEN_REFRESHED" : "SIGNED_OUT", token ? session(token) : null),
      );
    await waitFor(() => expect(box).toBeEnabled());
    fireEvent.change(box, { target: { value: "Current doubles." } });
    fireEvent.keyDown(box, { key: "Enter", metaKey: true });
    await waitFor(() => expect(runsSent()).toHaveLength(index + 1));
    const calls = vi
      .mocked(fetch)
      .mock.calls.filter(([input]) => String(input).endsWith("/agent/live/run"));
    const headers = new Headers(calls[index]?.[1]?.headers);
    expect(headers.get("authorization")).toBe(token ? `Bearer ${token}` : null);
    expect(headers.get("x-lunaris-session-id")).toBe("sess-auth");
  }
});
