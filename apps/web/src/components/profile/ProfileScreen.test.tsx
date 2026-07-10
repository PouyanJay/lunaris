import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { User } from "@supabase/supabase-js";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ProfileScreen } from "./ProfileScreen";

// The screen reads its account off useAuth; drive it through a mocked hook so each test can set the
// user + spy on the mutations without standing up a Supabase-backed AuthProvider.
const auth = {
  user: null as User | null,
  updateDisplayName: vi.fn<(name: string) => Promise<void>>(),
  signOut: vi.fn<() => Promise<void>>(),
};

vi.mock("../../hooks/useAuth", () => ({ useAuth: () => auth }));

function makeUser(email: string, metadata: Record<string, unknown> = {}): User {
  return { email, user_metadata: metadata } as unknown as User;
}

describe("ProfileScreen", () => {
  beforeEach(() => {
    auth.user = makeUser("pj.autech@gmail.com");
    auth.updateDisplayName = vi.fn().mockResolvedValue(undefined);
    auth.signOut = vi.fn().mockResolvedValue(undefined);
  });

  it("shows a designed notice, not a blank, when there's no session", () => {
    auth.user = null;
    const onGoHome = vi.fn();
    render(<ProfileScreen onGoHome={onGoHome} />);

    expect(screen.getByRole("heading", { name: /not signed in/i })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /go home/i }));
    expect(onGoHome).toHaveBeenCalledOnce();
  });

  it("seeds the name field from the email-derived display name and the email is shown", () => {
    render(<ProfileScreen onGoHome={vi.fn()} />);

    expect(screen.getByLabelText(/display name/i)).toHaveValue("Pj Autech");
    expect(screen.getByText("pj.autech@gmail.com")).toBeInTheDocument();
  });

  it("prefers a stored display_name over the email-derived one", () => {
    auth.user = makeUser("pj.autech@gmail.com", { display_name: "Pouyan" });
    render(<ProfileScreen onGoHome={vi.fn()} />);

    expect(screen.getByLabelText(/display name/i)).toHaveValue("Pouyan");
  });

  it("saves a trimmed display name and confirms with a Saved status", async () => {
    render(<ProfileScreen onGoHome={vi.fn()} />);

    fireEvent.change(screen.getByLabelText(/display name/i), { target: { value: "  Ada  " } });
    fireEvent.click(screen.getByRole("button", { name: /save name/i }));

    await screen.findByText("Saved");
    expect(auth.updateDisplayName).toHaveBeenCalledWith("Ada");
  });

  it("rejects a blank name inline without calling the mutation", () => {
    render(<ProfileScreen onGoHome={vi.fn()} />);

    fireEvent.change(screen.getByLabelText(/display name/i), { target: { value: "   " } });
    fireEvent.click(screen.getByRole("button", { name: /save name/i }));

    expect(screen.getByText(/enter a display name/i)).toBeInTheDocument();
    expect(auth.updateDisplayName).not.toHaveBeenCalled();
  });

  it("surfaces a save failure as a recoverable message", async () => {
    auth.updateDisplayName = vi.fn().mockRejectedValue(new Error("Network down"));
    render(<ProfileScreen onGoHome={vi.fn()} />);

    fireEvent.click(screen.getByRole("button", { name: /save name/i }));

    expect(await screen.findByText("Network down")).toBeInTheDocument();
  });

  it("signs out and returns home", async () => {
    const onGoHome = vi.fn();
    render(<ProfileScreen onGoHome={onGoHome} />);

    fireEvent.click(screen.getByRole("button", { name: /sign out/i }));

    await waitFor(() => expect(onGoHome).toHaveBeenCalledOnce());
    expect(auth.signOut).toHaveBeenCalledOnce();
  });
});
