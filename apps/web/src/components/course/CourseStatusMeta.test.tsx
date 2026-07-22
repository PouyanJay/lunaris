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
});
