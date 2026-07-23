import { fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { makeCourse, routedFetch } from "../../test/fixtures";
import { CourseReader, READER_MODE_KEY } from "./CourseReader";

const CLAIM = "Locate in the lesson: Comparison reduces the problem size each step.";

/** Fetch stub for Watch mode: the video routes answer "nothing" (204), so the Watch surface renders
 *  its idle generate affordance without a real video — enough to exercise the mode. */
function quietVideoFetch() {
  const base = routedFetch();
  return vi.fn((input: Parameters<typeof fetch>[0], init?: RequestInit) => {
    const url = String(input).split("?")[0]!;
    if (/\/api\/videos\//.test(url) || url.endsWith("/videos/active")) {
      return Promise.resolve(new Response(null, { status: 204 }));
    }
    return base(input as never, init as never);
  });
}

afterEach(() => {
  localStorage.clear();
  vi.unstubAllGlobals();
});

/** Claim → lesson backlink (claim-lesson-backlink): clicking a claim in the Sources & checks rail
 *  jumps the Learn Focus-Flow to where that claim lives in the lesson. The rail is a static column,
 *  so the claim button is reachable without opening a drawer. */
describe("CourseReader — claim → lesson backlink", () => {
  it("jumps the Focus Flow to the claim's phase when its rail entry is clicked", () => {
    // Arrange — Learn mode opens on step 1 (the intro/expects bookend). The fixture's only claim
    // lives in the demonstrate phase ("Strategies & worked example").
    render(<CourseReader course={makeCourse()} />);
    expect(screen.getByText(/you can compare two numbers/i)).toBeInTheDocument(); // intro step

    // Act — click the claim in the rail (its button is labelled "Locate in the lesson: <claim>").
    fireEvent.click(
      screen.getByRole("button", {
        name: "Locate in the lesson: Comparison reduces the problem size each step.",
      }),
    );

    // Assert — the flow moved to the demonstrate content step (the step card's eyebrow names its
    // section), and we've left the intro. The rail entry is now the active/pressed one.
    const card = screen.getByRole("group", { name: "Step content" });
    expect(within(card).getByText(/Strategies & worked example/)).toBeInTheDocument();
    expect(screen.queryByText(/you can compare two numbers/i)).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", {
        name: "Locate in the lesson: Comparison reduces the problem size each step.",
      }),
    ).toHaveAttribute("aria-pressed", "true");
  });

  it("jumps to the exact chunk that holds the claim's sentence, not just the phase", () => {
    // Arrange — a lesson whose demonstrate phase spans TWO content chunks: a ~130-word filler
    // (chunk 1) then a short paragraph carrying the claim's sentence (chunk 2). Every other section
    // is emptied so the flow is exactly [chunk1, chunk2] — step 1 and step 2.
    const filler = `${Array.from({ length: 130 }, (_, i) => `w${i}`).join(" ")}.`;
    const course = makeCourse();
    const lesson = course.modules[0]!.lessons[0]!;
    lesson.segments.activate.prose = "";
    lesson.segments.apply.prose = "";
    lesson.segments.integrate.prose = "";
    lesson.segments.demonstrate.prose = `${filler}\n\nThe zephyr protocol encrypts the quokka channel.`;
    lesson.segments.demonstrate.resources = [];
    lesson.segments.demonstrate.claims = [
      { text: "Zephyr protocol encrypts the quokka channel", supportedBy: null, verifierStatus: "cut" },
    ];
    lesson.expects = [];
    lesson.selfCheck = [];
    course.modules[0]!.assessment.items = [];

    render(<CourseReader course={course} />);
    // The flow opens on chunk 1 (the filler).
    expect(screen.getByText(/step 1 of 2/i)).toBeInTheDocument();

    // Act — locate the claim whose sentence lives in chunk 2.
    fireEvent.click(
      screen.getByRole("button", {
        name: "Locate in the lesson: Zephyr protocol encrypts the quokka channel",
      }),
    );

    // Assert — it jumped past the phase's first step to chunk 2 (sentence precision, not the
    // phase-first fallback, which would have stayed on step 1).
    expect(screen.getByText(/step 2 of 2/i)).toBeInTheDocument();
  });

  it("flashes the target step when a claim is located", () => {
    render(<CourseReader course={makeCourse()} />);
    expect(screen.getByRole("group", { name: "Step content" })).not.toHaveAttribute("data-located");

    fireEvent.click(screen.getByRole("button", { name: CLAIM }));

    // The step card is lit so the eye lands on where the claim lives.
    expect(screen.getByRole("group", { name: "Step content" })).toHaveAttribute(
      "data-located",
      "true",
    );
  });

  it("switches from Watch to Learn and jumps when a claim is located", () => {
    // Arrange — an explicit Watch preference + a reachable video service opens the reader in Watch.
    localStorage.setItem(READER_MODE_KEY, "watch");
    vi.stubGlobal("fetch", quietVideoFetch());
    render(<CourseReader course={makeCourse()} apiBaseUrl="http://api.test" />);
    expect(screen.getByRole("radio", { name: "Watch" })).toBeChecked();
    expect(screen.queryByRole("region", { name: /lesson steps/i })).not.toBeInTheDocument();

    // Act — the claim lives in the lesson prose, so locating it from the (always-present) rail must
    // bring the reader to Learn.
    fireEvent.click(screen.getByRole("button", { name: CLAIM }));

    // Assert — now in Learn, on the claim's step.
    expect(screen.getByRole("radio", { name: "Learn" })).toBeChecked();
    const card = screen.getByRole("group", { name: "Step content" });
    expect(within(card).getByText(/Strategies & worked example/)).toBeInTheDocument();
  });

  // Variant coverage: a claim in any teaching phase locates to that phase's step (demonstrate is
  // covered above; here the other three).
  it.each([
    { phase: "activate" as const, label: "Warm-up" },
    { phase: "apply" as const, label: "Practice" },
    { phase: "integrate" as const, label: "Make it your own" },
  ])("locates a claim in the $phase phase to its “$label” step", ({ phase, label }) => {
    const text = `A distinctive ${phase} claim about zephyrs`;
    const course = makeCourse();
    course.modules[0]!.lessons[0]!.segments[phase].claims = [
      { text, supportedBy: null, verifierStatus: "cut" },
    ];
    render(<CourseReader course={course} />);

    fireEvent.click(screen.getByRole("button", { name: `Locate in the lesson: ${text}` }));

    const card = screen.getByRole("group", { name: "Step content" });
    expect(within(card).getByText(new RegExp(label))).toBeInTheDocument();
  });

  it("flashes even when the located claim already lives on the current step", () => {
    render(<CourseReader course={makeCourse()} />);
    // Walk to the demonstrate step (where the fixture claim lives) the normal way — no flash.
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));
    const card = screen.getByRole("group", { name: "Step content" });
    expect(within(card).getByText(/Strategies & worked example/)).toBeInTheDocument();
    expect(card).not.toHaveAttribute("data-located");

    // Locating the claim that lives on this very step still flashes (nonce-driven, not step-change).
    fireEvent.click(screen.getByRole("button", { name: CLAIM }));

    expect(screen.getByRole("group", { name: "Step content" })).toHaveAttribute(
      "data-located",
      "true",
    );
  });
});
