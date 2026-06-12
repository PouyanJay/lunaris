import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ExplainProvider } from "../explain/ExplainContext";
import { Callout } from "./Callout";

function jsonResponse(body: unknown) {
  return { ok: true, status: 200, json: async () => body } as Response;
}

describe("Callout explain affordance", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("offers no Explain button outside an available explain capability", () => {
    // Arrange / Act — no provider (the context default is unavailable).
    render(<Callout variant="insight">Relaxation never increases a distance.</Callout>);

    // Assert
    expect(screen.queryByRole("button", { name: /explain/i })).not.toBeInTheDocument();
  });

  it("explains the callout's text with its variant as context", async () => {
    // Arrange
    const fetchMock = vi.fn(async () => jsonResponse({ explanation: "Distances only shrink." }));
    vi.stubGlobal("fetch", fetchMock);
    render(
      <ExplainProvider apiBaseUrl="http://test" available={true}>
        <Callout variant="insight">
          <p>
            Relaxation never <strong>increases</strong> a distance.
          </p>
        </Callout>
      </ExplainProvider>,
    );

    // Act
    fireEvent.click(screen.getByRole("button", { name: /explain/i }));

    // Assert — the nested markup flattens to the prose the model sees; the variant steers it.
    await waitFor(() => expect(screen.getByText("Distances only shrink.")).toBeInTheDocument());
    const [, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    const payload = JSON.parse(init.body as string) as { content: string; context?: string };
    expect(payload.content).toBe("Relaxation never increases a distance.");
    expect(payload.context).toMatch(/insight/i);
  });
});
