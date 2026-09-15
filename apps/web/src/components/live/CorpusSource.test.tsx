import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { CorpusSource } from "./CorpusSource";

const courses = [{ courseId: "course-a", title: "Patient data" }];

it("prepares only the explicitly selected course and makes no verification claim", () => {
  const prepare = vi.fn();
  const select = vi.fn();
  const { rerender } = render(
    <CorpusSource courses={courses} courseId="" onSelect={select} onPrepare={prepare} />,
  );
  expect(prepare).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: /Source course/ }));
  fireEvent.pointerDown(screen.getByRole("option", { name: "Patient data" }));
  expect(select).toHaveBeenCalledWith("course-a");
  rerender(
    <CorpusSource courses={courses} courseId="course-a" onSelect={select} onPrepare={prepare} />,
  );
  fireEvent.click(screen.getByRole("button", { name: "Prepare course" }));
  expect(prepare).toHaveBeenCalledWith("course-a");
  expect(screen.queryByRole("status")).not.toBeInTheDocument();
});

it("shows persisted source identity as pending, with busy and recoverable error states", () => {
  const props = { courses, courseId: "course-a", onSelect: vi.fn(), onPrepare: vi.fn() };
  const { rerender } = render(<CorpusSource {...props} busy />);
  expect(screen.getByRole("button", { name: "Preparing course…" })).toBeDisabled();
  expect(screen.getByRole("button", { name: /Source course/ })).toBeDisabled();
  rerender(<CorpusSource {...props} source={{ title: "Persisted course", status: "pending" }} />);
  expect(screen.getByText("Persisted course")).toBeVisible();
  expect(screen.getByRole("status")).toHaveTextContent("Awaiting verification");
  rerender(<CorpusSource {...props} error="Could not prepare this course. Try again." />);
  expect(screen.getByRole("alert")).toHaveTextContent("Try again");
  expect(screen.getByRole("button", { name: "Prepare course" })).toBeEnabled();
});

it("offers a recovery link when there are no source courses", () => {
  render(<CorpusSource courses={[]} courseId="" onSelect={vi.fn()} onPrepare={vi.fn()} />);
  expect(screen.getByRole("link", { name: "Open Studio" })).toHaveAttribute("href", "/");
  expect(screen.queryByRole("button", { name: "Prepare course" })).not.toBeInTheDocument();
});

it("explains an empty selection without submitting", () => {
  const prepare = vi.fn();
  render(<CorpusSource courses={courses} courseId="" onSelect={vi.fn()} onPrepare={prepare} />);
  fireEvent.click(screen.getByRole("button", { name: "Prepare course" }));
  expect(prepare).not.toHaveBeenCalled();
  expect(screen.getByRole("alert")).toHaveTextContent("Choose a source course before preparing.");
  const control = screen.getByRole("button", { name: /Source course/ });
  expect(control).toHaveFocus();
  expect(control).toHaveAttribute("aria-invalid", "true");
  expect(control).toHaveAttribute("aria-describedby", screen.getByRole("alert").id);
});
