import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { makeCourse } from "../../test/fixtures";
import type { Course } from "../../types/course";
import { CourseStatusMeta } from "./CourseStatusMeta";

const API = "http://api.test";

/** Mock fetch so `POST /api/courses/:id/publish` returns the now-published course. */
function stubPublish(published: Course) {
  return vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
    const url = input instanceof Request ? input.url : String(input);
    const method = (init?.method ?? "GET").toUpperCase();
    if (url.endsWith(`/api/courses/${published.id}/publish`) && method === "POST") {
      return Promise.resolve(new Response(JSON.stringify(published), { status: 200 }));
    }
    return Promise.reject(new Error(`unexpected fetch: ${method} ${url}`));
  });
}

describe("CourseStatusMeta (review → publish trigger)", () => {
  afterEach(() => vi.restoreAllMocks());

  it("renders a plain status dot (no trigger) for a published course", () => {
    render(<CourseStatusMeta course={makeCourse({ status: "published" })} apiBaseUrl={API} />);

    expect(screen.getByText("PUBLISHED")).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("keeps the REVIEW pill inert offline (no apiBaseUrl)", () => {
    render(<CourseStatusMeta course={makeCourse({ status: "review" })} />);

    expect(screen.getByText("REVIEW")).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("opens the review drawer from the REVIEW pill", () => {
    render(<CourseStatusMeta course={makeCourse({ status: "review" })} apiBaseUrl={API} />);

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Review and publish this course" }));

    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveAttribute("aria-modal", "true");
    expect(dialog).toHaveAccessibleName("Review & publish");
  });

  it("moves focus into the drawer on open and restores it to the trigger on close", async () => {
    render(<CourseStatusMeta course={makeCourse({ status: "review" })} apiBaseUrl={API} />);
    const trigger = screen.getByRole("button", { name: "Review and publish this course" });
    trigger.focus();

    fireEvent.click(trigger);
    // Focus lands on the close button — never the destructive-adjacent publish primary.
    expect(screen.getByRole("button", { name: "Close review panel" })).toHaveFocus();

    // Esc closes and returns focus to the trigger, so the keyboard user isn't dropped to the body.
    fireEvent.keyDown(window, { key: "Escape" });
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(trigger).toHaveFocus();
  });

  it("approves: POSTs to /publish and hands the published course to onPublished", async () => {
    const course = makeCourse({ id: "c-rev", status: "review" });
    const published = { ...course, status: "published" as const };
    const fetchSpy = stubPublish(published);
    const onPublished = vi.fn();
    render(<CourseStatusMeta course={course} apiBaseUrl={API} onPublished={onPublished} />);

    fireEvent.click(screen.getByRole("button", { name: "Review and publish this course" }));
    fireEvent.click(screen.getByRole("button", { name: "Approve & publish" }));

    await waitFor(() => expect(onPublished).toHaveBeenCalledTimes(1));
    // The POST hit the publish endpoint for this course.
    const called = fetchSpy.mock.calls[0]!;
    expect(String(called[0])).toBe(`${API}/api/courses/c-rev/publish`);
    expect((called[1]?.method ?? "").toUpperCase()).toBe("POST");
    // The drawer closed on success.
    expect(onPublished.mock.calls[0]![0]).toMatchObject({ status: "published" });
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    // The result is announced to assistive tech (the pill also turns green PUBLISHED visually).
    expect(screen.getByRole("status")).toHaveTextContent(/course published/i);
  });

  it("keeps the drawer open on a failed publish, showing a recovery message", async () => {
    const course = makeCourse({ id: "c-rev", status: "review" });
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(null, { status: 409 }));
    render(<CourseStatusMeta course={course} apiBaseUrl={API} />);

    fireEvent.click(screen.getByRole("button", { name: "Review and publish this course" }));
    fireEvent.click(screen.getByRole("button", { name: "Approve & publish" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/still building/i);
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("re-enables approve after a failure so the owner can retry", async () => {
    const course = makeCourse({ id: "c-rev", status: "review" });
    const published = { ...course, status: "published" as const };
    let call = 0;
    vi.spyOn(globalThis, "fetch").mockImplementation(() => {
      call += 1;
      return Promise.resolve(
        call === 1
          ? new Response(null, { status: 409 })
          : new Response(JSON.stringify(published), { status: 200 }),
      );
    });
    const onPublished = vi.fn();
    render(<CourseStatusMeta course={course} apiBaseUrl={API} onPublished={onPublished} />);

    fireEvent.click(screen.getByRole("button", { name: "Review and publish this course" }));
    fireEvent.click(screen.getByRole("button", { name: "Approve & publish" }));

    // First attempt failed → the alert shows and the button is enabled again for a retry.
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    const approve = screen.getByRole("button", { name: "Approve & publish" });
    expect(approve).toBeEnabled();

    // Retry succeeds.
    fireEvent.click(approve);
    await waitFor(() => expect(onPublished).toHaveBeenCalledTimes(1));
  });
});
