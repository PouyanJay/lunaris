import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { makeRun } from "../../test/fixtures";
import { RunList } from "./RunList";

const noop = () => {};

describe("RunList", () => {
  it("shows a labelled loading state (not a bare spinner)", () => {
    render(<RunList state={{ status: "loading" }} onRetry={noop} />);

    expect(screen.getByRole("status", { name: /loading run history/i })).toBeInTheDocument();
  });

  it("shows a recoverable error with a retry action", () => {
    const onRetry = vi.fn();
    render(<RunList state={{ status: "error", message: "history is down" }} onRetry={onRetry} />);

    expect(screen.getByRole("alert")).toHaveTextContent("history is down");
    fireEvent.click(screen.getByRole("button", { name: /retry/i }));
    expect(onRetry).toHaveBeenCalledOnce();
  });

  it("shows an empty hint when there are no runs", () => {
    render(<RunList state={{ status: "ready", runs: [] }} onRetry={noop} />);

    expect(screen.getByText(/no runs yet/i)).toBeInTheDocument();
  });

  it("renders each run with its topic and status", () => {
    const runs = [
      makeRun({ id: "c-1", topic: "binary search", status: "completed" }),
      makeRun({ id: "c-2", topic: "graphs", status: "running" }),
    ];
    render(<RunList state={{ status: "ready", runs }} onRetry={noop} />);

    expect(screen.getByText("binary search")).toBeInTheDocument();
    expect(screen.getByText("COMPLETED")).toBeInTheDocument();
    expect(screen.getByText("RUNNING")).toBeInTheDocument();
  });

  it("keeps the KC/module counts available as a tooltip (off the narrow rail)", () => {
    const runs = [makeRun({ id: "c-1", topic: "binary search", kcCount: 5, moduleCount: 3 })];
    render(<RunList state={{ status: "ready", runs }} onRetry={noop} />);

    expect(screen.getByText("binary search")).toHaveAttribute(
      "title",
      expect.stringContaining("5 KC, 3 modules"),
    );
  });

  it("is non-interactive display when no onSelectRun is given", () => {
    render(
      <RunList state={{ status: "ready", runs: [makeRun({ topic: "queues" })] }} onRetry={noop} />,
    );

    // The run still renders, just not as an interactive control.
    expect(screen.getByText("queues")).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("opens a run when selectable", () => {
    const onSelectRun = vi.fn();
    const run = makeRun({ id: "c-9", topic: "trees" });
    render(
      <RunList state={{ status: "ready", runs: [run] }} onRetry={noop} onSelectRun={onSelectRun} />,
    );

    fireEvent.click(screen.getByRole("button", { name: /trees/i }));
    expect(onSelectRun).toHaveBeenCalledWith(run);
  });
});
