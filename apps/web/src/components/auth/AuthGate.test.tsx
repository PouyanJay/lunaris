import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

const { useAuthMock } = vi.hoisted(() => ({ useAuthMock: vi.fn() }));
vi.mock("../../hooks/useAuth", () => ({ useAuth: useAuthMock }));
vi.mock("./AuthScreen", () => ({ AuthScreen: () => <div>auth-screen</div> }));

import { AuthGate } from "./AuthGate";

function Child() {
  return <div>protected-app</div>;
}

describe("AuthGate", () => {
  it("renders children unguarded when auth is disabled", () => {
    useAuthMock.mockReturnValue({ enabled: false, loading: false, session: null });

    render(
      <AuthGate>
        <Child />
      </AuthGate>,
    );

    expect(screen.getByText("protected-app")).toBeInTheDocument();
  });

  it("shows the auth screen when enabled and signed out", () => {
    useAuthMock.mockReturnValue({ enabled: true, loading: false, session: null });

    render(
      <AuthGate>
        <Child />
      </AuthGate>,
    );

    expect(screen.getByText("auth-screen")).toBeInTheDocument();
    expect(screen.queryByText("protected-app")).not.toBeInTheDocument();
  });

  it("shows a loading state while the session is restoring", () => {
    useAuthMock.mockReturnValue({ enabled: true, loading: true, session: null });

    render(
      <AuthGate>
        <Child />
      </AuthGate>,
    );

    expect(screen.getByRole("status")).toHaveTextContent("Loading");
    expect(screen.queryByText("protected-app")).not.toBeInTheDocument();
  });

  it("renders children once a session exists", () => {
    useAuthMock.mockReturnValue({ enabled: true, loading: false, session: { user: {} } });

    render(
      <AuthGate>
        <Child />
      </AuthGate>,
    );

    expect(screen.getByText("protected-app")).toBeInTheDocument();
  });
});
