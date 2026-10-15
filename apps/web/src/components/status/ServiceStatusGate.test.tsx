import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ServiceStatusGate } from "./ServiceStatusGate";

function healthz(status: number) {
  return vi
    .fn()
    .mockResolvedValue(new Response(status === 200 ? '{"status":"ok"}' : "", { status }));
}

describe("ServiceStatusGate", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders the app while the API is healthy", async () => {
    const fetchMock = healthz(200);
    vi.stubGlobal("fetch", fetchMock);

    render(
      <ServiceStatusGate apiBaseUrl="http://api.test">
        <p>the app</p>
      </ServiceStatusGate>,
    );

    expect(screen.getByText("the app")).toBeInTheDocument();
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(screen.getByText("the app")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: /offline/i })).not.toBeInTheDocument();
  });

  it("replaces the app with the offline notice when the API is unreachable", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));

    render(
      <ServiceStatusGate apiBaseUrl="http://api.test">
        <p>the app</p>
      </ServiceStatusGate>,
    );

    expect(await screen.findByRole("heading", { name: /lunaris is offline/i })).toBeInTheDocument();
    expect(screen.queryByText("the app")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: /contact@pouyan\.ai/i })).toHaveAttribute(
      "href",
      "mailto:contact@pouyan.ai",
    );
  });
});
