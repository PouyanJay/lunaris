import { render, screen } from "@testing-library/react";
import { act } from "react";
import { describe, expect, it, vi } from "vitest";

import { SIM_REPORT, SimFrame } from "./SimFrame";

/** Tier 3's socket in the browser (Phase 2b, T6).
 *
 *  Two things are under test and neither is the simulator, because there is no simulator — A3 says
 *  the stub proves the socket and Phase 3 replaces the stub, not the mount.
 *
 *  **The sandbox.** The document loads from our own API origin, so a frame granted
 *  `allow-same-origin` would run with our cookies, our storage and our credentialed fetch — and
 *  Phase 3's simulators are *generated*. That attribute is the whole security posture, so it is
 *  asserted rather than assumed.
 *
 *  **The message check.** A sandboxed frame posts with `origin === "null"`, a value any other
 *  framed document can present too, so origin identifies nothing here. `event.source` is the only
 *  check that says "this came from the frame I mounted", and a test that let a message through from
 *  somewhere else would be describing a hole rather than a contract.
 */

const REPORT = "In the placeholder simulator I moved the dial to 70.";

function mount(overrides: Partial<Parameters<typeof SimFrame>[0]> = {}) {
  const onAnswer = vi.fn();
  const view = render(
    <SimFrame
      url="/api/live/sims/stub"
      title="Divergence — placeholder simulator"
      appId="lunaris.sim.stub"
      answerable
      busy={false}
      onAnswer={onAnswer}
      {...overrides}
    />,
  );
  const frame = view.container.querySelector("iframe") as HTMLIFrameElement;
  return { onAnswer, frame, view };
}

/** A message as the browser delivers it, with `source` set to whichever window sent it.
 *
 *  `source` is read-only on a constructed `MessageEvent` in jsdom, so it is defined onto the event
 *  rather than passed — which is also exactly what makes the production check meaningful: nothing
 *  outside the browser can forge it. */
function post(source: Window | null, data: unknown, origin = "") {
  const event = new MessageEvent("message", { data, origin });
  Object.defineProperty(event, "source", { value: source });
  act(() => {
    window.dispatchEvent(event);
  });
}

describe("the sandbox around a simulator", () => {
  it("denies the frame our origin", () => {
    // `allow-scripts` alone. With `allow-same-origin` beside it the sandbox is decorative: the
    // frame would run as us, on our origin, with everything we can reach.
    const { frame } = mount();

    expect(frame.getAttribute("sandbox")).toBe("allow-scripts");
  });

  it("loads the simulator the turn named, under a name a learner can read", () => {
    const { frame } = mount();

    expect(frame.getAttribute("src")).toBe("/api/live/sims/stub");
    expect(frame.getAttribute("title")).toBe("Divergence — placeholder simulator");
  });

  it("does not hand the simulator the URL that framed it", () => {
    // A generated document should not learn which session a learner is in from a referrer header.
    const { frame } = mount();

    expect(frame.getAttribute("referrerpolicy")).toBe("no-referrer");
  });
});

describe("what the simulator is allowed to say", () => {
  it("takes what the learner did in the frame as their answer", () => {
    const { onAnswer, frame } = mount();

    post(frame.contentWindow, { type: SIM_REPORT, appId: "lunaris.sim.stub", report: REPORT });

    expect(onAnswer).toHaveBeenCalledWith(REPORT);
  });

  it("ignores a message from anywhere but the frame it mounted", () => {
    // The check that carries the sandbox. A sandboxed frame posts with `origin === "null"`, which
    // any other framed document can also present — so origin cannot be what decides this, and a
    // renderer that trusted it would let any page on the tab answer a learner's turn for them.
    const { onAnswer } = mount();

    post(window, { type: SIM_REPORT, appId: "lunaris.sim.stub", report: "Not from the frame." });

    expect(onAnswer).not.toHaveBeenCalled();
  });

  it("ignores a message claiming the frame's own opaque origin", () => {
    // The sharp version of the test above, and the one that actually pins the rule. A sandboxed
    // frame posts with `origin === "null"` — and so does *every other* sandboxed frame on the page,
    // so that string is a claim anyone can make rather than an identity. A renderer that accepted
    // it would let any embedded ad, widget or generated document answer a learner's turn.
    const { onAnswer } = mount();

    post(window, { type: SIM_REPORT, appId: "lunaris.sim.stub", report: REPORT }, "null");

    expect(onAnswer).not.toHaveBeenCalled();
  });

  it("ignores a report from a simulator other than the one mounted", () => {
    const { onAnswer, frame } = mount();

    post(frame.contentWindow, { type: SIM_REPORT, appId: "someone.else", report: REPORT });

    expect(onAnswer).not.toHaveBeenCalled();
  });

  it("ignores messages that are not a report at all", () => {
    // A frame shares the message channel with everything else on the page — bundlers, extensions
    // and dev tooling all post to `window` — so the type is a filter, not decoration.
    const { onAnswer, frame } = mount();

    post(frame.contentWindow, { type: "webpackHotUpdate" });
    post(frame.contentWindow, null);
    post(frame.contentWindow, "a string");
    post(frame.contentWindow, { type: SIM_REPORT, appId: "lunaris.sim.stub", report: "   " });
    post(frame.contentWindow, { type: SIM_REPORT, appId: "lunaris.sim.stub", report: 42 });

    expect(onAnswer).not.toHaveBeenCalled();
  });

  it("takes one report and not a second", () => {
    // The turn advances on the first, so a second would be graded against whatever question
    // replaced it — the same stale-answer hazard the REST path names explicitly.
    const { onAnswer, frame } = mount();

    post(frame.contentWindow, { type: SIM_REPORT, appId: "lunaris.sim.stub", report: REPORT });
    post(frame.contentWindow, { type: SIM_REPORT, appId: "lunaris.sim.stub", report: "Again." });

    expect(onAnswer).toHaveBeenCalledTimes(1);
  });

  it("takes nothing from a simulator on a turn that has already been answered", () => {
    // A past turn's frame is a record of what the learner was assessed by, so it still renders —
    // but a learner scrolling back and pressing send in it must not answer the turn they are on.
    const { onAnswer, frame } = mount({ answerable: false });

    post(frame.contentWindow, { type: SIM_REPORT, appId: "lunaris.sim.stub", report: REPORT });

    expect(onAnswer).not.toHaveBeenCalled();
  });
});

describe("what the learner is told", () => {
  it("says what to do, because a bare frame explains nothing", () => {
    mount();

    expect(screen.getByRole("status")).toHaveTextContent(/work in the simulator/i);
  });

  it("confirms the send, so nothing looks like it went nowhere", () => {
    const { frame } = mount();

    post(frame.contentWindow, { type: SIM_REPORT, appId: "lunaris.sim.stub", report: REPORT });

    expect(screen.getByRole("status")).toHaveTextContent(/sent what you did/i);
  });

  it("says it is being marked while it is being marked", () => {
    mount({ busy: true });

    expect(screen.getByRole("status")).toHaveTextContent(/marking/i);
  });

  it("says a past turn's simulator is a record rather than inviting an answer", () => {
    mount({ answerable: false });

    expect(screen.getByRole("status")).toHaveTextContent(/record of that turn/i);
  });
});
