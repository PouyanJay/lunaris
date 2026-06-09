import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { KeylessProvisioningBanner } from "./KeylessProvisioningBanner";

describe("KeylessProvisioningBanner", () => {
  it("shows a provisioning notice while the GPU is waking", () => {
    render(<KeylessProvisioningBanner status="provisioning" />);
    const banner = screen.getByRole("status");
    expect(banner).toHaveTextContent(/waking up the local gpu/i);
    expect(banner).toHaveTextContent(/30–60s/);
    expect(screen.getByText("PROVISIONING")).toBeInTheDocument();
  });

  it("announces politely so a screen reader hears the wait without stealing focus", () => {
    render(<KeylessProvisioningBanner status="provisioning" />);
    expect(screen.getByRole("status")).toHaveAttribute("aria-live", "polite");
  });

  it.each(["ready", "unreachable", "not_applicable", null] as const)(
    "renders nothing when status is %s",
    (status) => {
      const { container } = render(<KeylessProvisioningBanner status={status} />);
      expect(container).toBeEmptyDOMElement();
    },
  );
});
