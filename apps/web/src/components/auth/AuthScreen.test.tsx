import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

const { useAuthMock } = vi.hoisted(() => ({ useAuthMock: vi.fn() }));
vi.mock("../../hooks/useAuth", () => ({ useAuth: useAuthMock }));

import { AuthScreen } from "./AuthScreen";

function fillCredentials(email: string, password: string) {
  fireEvent.change(screen.getByLabelText("Email"), { target: { value: email } });
  fireEvent.change(screen.getByLabelText("Password"), { target: { value: password } });
}

describe("AuthScreen", () => {
  it("signs in with the entered email and password", async () => {
    const signIn = vi.fn().mockResolvedValue(undefined);
    useAuthMock.mockReturnValue({ signIn, signUp: vi.fn() });
    render(<AuthScreen />);

    fillCredentials("a@b.com", "secret1");
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));

    await waitFor(() => expect(signIn).toHaveBeenCalledWith("a@b.com", "secret1"));
  });

  it("disables the submit control while a sign-in is in flight", async () => {
    let release = () => {};
    const signIn = vi.fn().mockReturnValue(
      new Promise<void>((resolve) => {
        release = resolve;
      }),
    );
    useAuthMock.mockReturnValue({ signIn, signUp: vi.fn() });
    render(<AuthScreen />);

    fillCredentials("a@b.com", "secret1");
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByRole("button", { name: "Signing in…" })).toBeDisabled();
    release();
  });

  it("surfaces a sign-in error in an alert", async () => {
    const signIn = vi.fn().mockRejectedValue(new Error("Invalid login credentials"));
    useAuthMock.mockReturnValue({ signIn, signUp: vi.fn() });
    render(<AuthScreen />);

    fillCredentials("a@b.com", "secret1");
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Invalid login credentials");
  });

  it("creates an account and shows the email-confirmation notice", async () => {
    const signUp = vi.fn().mockResolvedValue({ needsConfirmation: true });
    useAuthMock.mockReturnValue({ signIn: vi.fn(), signUp });
    render(<AuthScreen />);

    fireEvent.click(screen.getByRole("button", { name: "Create one" }));
    fillCredentials("new@b.com", "secret1");
    fireEvent.click(screen.getByRole("button", { name: "Create account" }));

    await waitFor(() => expect(signUp).toHaveBeenCalledWith("new@b.com", "secret1"));
    expect(await screen.findByText(/Check new@b\.com/)).toBeInTheDocument();
  });
});
