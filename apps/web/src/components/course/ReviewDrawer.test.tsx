import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { makeCourse } from "../../test/fixtures";
import type { ReviewGate } from "../../types/course";
import { ReviewDrawer } from "./ReviewDrawer";

const GATES: ReviewGate[] = [
  {
    key: "structure",
    label: "Structure",
    status: "warning",
    detail: "2 of 9 lessons ship without a worked example.",
  },
  {
    key: "coverage",
    label: "Coverage",
    status: "passed",
    detail: "Every promised competency is built.",
  },
  {
    key: "grounding",
    label: "Grounding honesty",
    status: "caveat",
    detail: "This course was not grounded in the real CLB 10 standard.",
  },
];

function renderDrawer(overrides: Partial<Parameters<typeof ReviewDrawer>[0]> = {}) {
  const props = {
    open: true,
    course: makeCourse({ topic: "Bayesian inference", reviewGates: GATES }),
    pending: false,
    errorMessage: null,
    onApprove: vi.fn(),
    onClose: vi.fn(),
    ...overrides,
  };
  return { props, ...render(<ReviewDrawer {...props} />) };
}

describe("ReviewDrawer", () => {
  it("renders nothing when closed", () => {
    renderDrawer({ open: false });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("is a labelled modal dialog naming the course", () => {
    renderDrawer();
    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveAttribute("aria-modal", "true");
    expect(dialog).toHaveAccessibleName("Review & publish");
    expect(screen.getByText("Bayesian inference")).toBeInTheDocument();
  });

  it("lists each gate with its label, verdict, and reason", () => {
    renderDrawer();
    const list = screen.getByRole("list");
    const rows = within(list).getAllByRole("listitem");
    expect(rows).toHaveLength(3);

    const structure = rows[0]!;
    expect(within(structure).getByText("Structure")).toBeInTheDocument();
    expect(within(structure).getByText("Needs work")).toBeInTheDocument();
    expect(
      within(structure).getByText(/2 of 9 lessons ship without a worked example/),
    ).toBeInTheDocument();
    // The caveat gate reads its verbatim honest reason.
    expect(screen.getByText(/not grounded in the real CLB 10 standard/i)).toBeInTheDocument();
    expect(screen.getByText("Caveat")).toBeInTheDocument();
  });

  it("shows a neutral note when no gates were recorded", () => {
    renderDrawer({ course: makeCourse({ reviewGates: [] }) });
    expect(screen.queryByRole("list")).not.toBeInTheDocument();
    expect(screen.getByText(/no blocking gates were recorded/i)).toBeInTheDocument();
  });

  it("calls onApprove from the Approve & publish button", () => {
    const { props } = renderDrawer();
    fireEvent.click(screen.getByRole("button", { name: "Approve & publish" }));
    expect(props.onApprove).toHaveBeenCalledOnce();
    expect(props.onClose).not.toHaveBeenCalled();
  });

  it("calls onClose from the Keep in review button", () => {
    const { props } = renderDrawer();
    fireEvent.click(screen.getByRole("button", { name: "Keep in review" }));
    expect(props.onClose).toHaveBeenCalledOnce();
    expect(props.onApprove).not.toHaveBeenCalled();
  });

  it("closes on Escape", () => {
    const { props } = renderDrawer();
    fireEvent.keyDown(window, { key: "Escape" });
    expect(props.onClose).toHaveBeenCalledOnce();
  });

  it("disables the actions and shows a pending label while publishing", () => {
    renderDrawer({ pending: true });
    const approve = screen.getByRole("button", { name: "Publishing…" });
    expect(approve).toBeDisabled();
    expect(approve).toHaveAttribute("aria-busy", "true");
    expect(screen.getByRole("button", { name: "Keep in review" })).toBeDisabled();
  });

  it("surfaces a publish failure as an alert, keeping the drawer open", () => {
    renderDrawer({ errorMessage: "This course is still building — it can't be published yet." });
    expect(screen.getByRole("alert")).toHaveTextContent(/still building/i);
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });
});
