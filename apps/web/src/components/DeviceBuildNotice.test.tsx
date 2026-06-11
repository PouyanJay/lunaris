import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { DeviceBuildNotice } from "./DeviceBuildNotice";

describe("DeviceBuildNotice", () => {
  it("announces itself as a polite live region", () => {
    // Arrange / Act
    render(<DeviceBuildNotice />);

    // Assert — assistive tech hears the standing condition without interruption.
    expect(screen.getByRole("status")).toBeInTheDocument();
  });

  it("names the constraint: keep the tab open while the build runs on this device", () => {
    // Arrange / Act
    render(<DeviceBuildNotice />);

    // Assert — the contract is explicit: the build dies with the tab.
    const notice = screen.getByRole("status");
    expect(notice).toHaveTextContent(/keep this tab open/i);
    expect(notice).toHaveTextContent(/running on your device/i);
  });
});
