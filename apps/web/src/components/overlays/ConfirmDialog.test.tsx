import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ConfirmDialog } from "./ConfirmDialog";

const base = {
  title: "Delete this course?",
  description: "This can’t be undone.",
  confirmLabel: "Delete course",
  onConfirm: () => {},
  onCancel: () => {},
};

describe("ConfirmDialog", () => {
  it("renders nothing when closed", () => {
    render(<ConfirmDialog {...base} open={false} />);

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("is a labelled, described modal dialog when open", () => {
    render(<ConfirmDialog {...base} open />);

    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveAttribute("aria-modal", "true");
    expect(dialog).toHaveAccessibleName("Delete this course?");
    expect(dialog).toHaveAccessibleDescription("This can’t be undone.");
  });

  it("invokes onConfirm and onCancel from the action buttons", () => {
    const onConfirm = vi.fn();
    const onCancel = vi.fn();
    render(<ConfirmDialog {...base} open onConfirm={onConfirm} onCancel={onCancel} />);

    fireEvent.click(screen.getByRole("button", { name: "Delete course" }));
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));

    expect(onConfirm).toHaveBeenCalledOnce();
    expect(onCancel).toHaveBeenCalledOnce();
  });

  it("cancels on Escape from within the dialog", () => {
    const onCancel = vi.fn();
    render(<ConfirmDialog {...base} open onCancel={onCancel} />);

    // Fire from the dialog so this exercises the capture-phase handler intercepting a key from
    // inside (not merely a global window listener).
    fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" });

    expect(onCancel).toHaveBeenCalledOnce();
  });

  it("moves focus to the confirm action on open (keyboard lands inside the dialog)", () => {
    render(<ConfirmDialog {...base} open />);

    expect(screen.getByRole("button", { name: "Delete course" })).toHaveFocus();
  });

  it("shows the pending label and disables both actions while in flight", () => {
    render(<ConfirmDialog {...base} open pending pendingLabel="Deleting…" />);

    expect(screen.getByRole("button", { name: "Deleting…" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Cancel" })).toBeDisabled();
  });

  it("surfaces an error message without closing", () => {
    render(<ConfirmDialog {...base} open errorMessage="This run is still building." />);

    expect(screen.getByRole("alert")).toHaveTextContent("This run is still building.");
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("restores focus to the triggering control when it closes", () => {
    function Harness({ open }: { open: boolean }) {
      return (
        <>
          <button>Open</button>
          <ConfirmDialog {...base} open={open} />
        </>
      );
    }
    const { rerender } = render(<Harness open={false} />);
    const trigger = screen.getByRole("button", { name: "Open" });
    trigger.focus();

    // Open: focus moves into the dialog (onto the confirm action).
    rerender(<Harness open />);
    expect(screen.getByRole("button", { name: "Delete course" })).toHaveFocus();

    // Close: focus returns to the control that opened it (WCAG focus management).
    rerender(<Harness open={false} />);
    expect(trigger).toHaveFocus();
  });
});
