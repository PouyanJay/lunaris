import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { afterEach, beforeEach, describe, expect, it, vi, type MockInstance } from "vitest";

import { ErrorBoundary } from "./ErrorBoundary";

function Bomb({ when }: { when: boolean }) {
  if (when) throw new Error("render exploded");
  return <p>healthy content</p>;
}

describe("ErrorBoundary", () => {
  let consoleError: MockInstance;

  beforeEach(() => {
    // React logs the caught error; keep the test output clean without hiding other failures.
    consoleError = vi.spyOn(console, "error").mockImplementation(() => {});
  });

  afterEach(() => {
    consoleError.mockRestore();
  });

  it("renders its children when nothing throws", () => {
    // Arrange / Act
    render(
      <ErrorBoundary>
        <Bomb when={false} />
      </ErrorBoundary>,
    );

    // Assert
    expect(screen.getByText("healthy content")).toBeInTheDocument();
  });

  it("catches a render crash and shows the recovery fallback instead of a blank app", () => {
    // Act — the child throws during render.
    render(
      <ErrorBoundary>
        <Bomb when={true} />
      </ErrorBoundary>,
    );

    // Assert — an announced, human-readable failure with recovery actions, never a white screen.
    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.getByText(/something went wrong/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /try again/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /reload/i })).toBeInTheDocument();
  });

  it("recovers via Try again once the underlying problem is gone", () => {
    // Arrange — a wrapper whose child stops throwing after the first render crash.
    function Flaky() {
      const [explode, setExplode] = useState(true);
      return (
        <ErrorBoundary onReset={() => setExplode(false)}>
          <Bomb when={explode} />
        </ErrorBoundary>
      );
    }
    render(<Flaky />);
    expect(screen.getByRole("alert")).toBeInTheDocument();

    // Act
    fireEvent.click(screen.getByRole("button", { name: /try again/i }));

    // Assert — the children render again.
    expect(screen.getByText("healthy content")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});
