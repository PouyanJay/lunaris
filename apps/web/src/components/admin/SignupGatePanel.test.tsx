import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { fetchSignupGateMock, updateSignupGateMock } = vi.hoisted(() => ({
  fetchSignupGateMock: vi.fn(),
  updateSignupGateMock: vi.fn(),
}));
vi.mock("../../lib/signupGate", () => ({
  fetchSignupGate: fetchSignupGateMock,
  updateSignupGate: updateSignupGateMock,
}));

import { SignupGatePanel } from "./SignupGatePanel";

const GATE = { inviteCode: "LUNARIS-BETA", enforced: true, updatedAt: null };

describe("SignupGatePanel", () => {
  beforeEach(() => {
    fetchSignupGateMock.mockResolvedValue(GATE);
    updateSignupGateMock.mockReset();
  });

  it("shows the current invitation code once loaded", async () => {
    render(<SignupGatePanel apiBaseUrl="http://api.test" />);

    const field = (await screen.findByLabelText("Invitation code")) as HTMLInputElement;
    expect(field.value).toBe("LUNARIS-BETA");
  });

  it("rotates the code: edits the field, saves, and confirms the new value", async () => {
    updateSignupGateMock.mockResolvedValue({ ...GATE, inviteCode: "AUTUMN-2026" });
    render(<SignupGatePanel apiBaseUrl="http://api.test" />);

    const field = await screen.findByLabelText("Invitation code");
    fireEvent.change(field, { target: { value: "AUTUMN-2026" } });
    fireEvent.click(screen.getByRole("button", { name: "Save code" }));

    await waitFor(() =>
      expect(updateSignupGateMock).toHaveBeenCalledWith("http://api.test", {
        inviteCode: "AUTUMN-2026",
      }),
    );
    // The visible outcome — a success notice, and Save back to disabled (draft === saved).
    expect(await screen.findByText("Invitation code updated.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save code" })).toBeDisabled();
  });

  it("surfaces a save error and keeps the panel open", async () => {
    updateSignupGateMock.mockRejectedValueOnce(
      new Error("The invitation code must not be empty."),
    );
    render(<SignupGatePanel apiBaseUrl="http://api.test" />);

    const field = await screen.findByLabelText("Invitation code");
    fireEvent.change(field, { target: { value: "NEW-CODE" } });
    fireEvent.click(screen.getByRole("button", { name: "Save code" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "The invitation code must not be empty.",
    );
    // The panel stays usable (the code field is still there), not replaced by the load-error view.
    expect(screen.getByLabelText("Invitation code")).toBeInTheDocument();
  });

  it("disables Save until the code actually changes", async () => {
    render(<SignupGatePanel apiBaseUrl="http://api.test" />);

    await screen.findByLabelText("Invitation code");
    expect(screen.getByRole("button", { name: "Save code" })).toBeDisabled();
  });

  it("toggles enforcement off via the switch", async () => {
    updateSignupGateMock.mockResolvedValue({ ...GATE, enforced: false });
    render(<SignupGatePanel apiBaseUrl="http://api.test" />);

    await screen.findByLabelText("Invitation code");
    fireEvent.click(screen.getByRole("switch", { name: "Require invitation code" }));

    await waitFor(() =>
      expect(updateSignupGateMock).toHaveBeenCalledWith("http://api.test", { enforced: false }),
    );
  });

  it("surfaces a load failure with a retry", async () => {
    fetchSignupGateMock.mockRejectedValueOnce(new Error("Admin access required"));
    render(<SignupGatePanel apiBaseUrl="http://api.test" />);

    expect(await screen.findByRole("alert")).toHaveTextContent("Admin access required");
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });
});
