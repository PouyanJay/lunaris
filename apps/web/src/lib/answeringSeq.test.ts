import { describe, expect, it } from "vitest";

import { answeringSeqOf } from "./answeringSeq";

/** Which turn a send from the generative panel is answering (P2b T9).
 *
 *  Two sources, in order: the agent's state as the last `STATE_SNAPSHOT` left it (`turn` is the
 *  turn now in front of the learner, `SessionSnapshot.turn`), and failing that the turn the REST
 *  read said was standing when the panel mounted. The API refuses a named turn that has moved on
 *  (409), so the value has to be the *latest* one the browser has been told, and it has to be
 *  omitted rather than guessed when the browser has been told nothing. */
describe("the turn a send is answering", () => {
  it("is the turn the last state frame named", () => {
    // The panel's own runs move the session on; the REST read that seeded it does not re-read.
    expect(answeringSeqOf({ turn: 4, status: "active" }, 1)).toBe(4);
  });

  it("falls back to the standing turn the panel mounted with, before any run has answered", () => {
    expect(answeringSeqOf({}, 3)).toBe(3);
    expect(answeringSeqOf(undefined, 3)).toBe(3);
  });

  it("names nothing when neither source has a turn", () => {
    // Omitted rather than 0 or 1: the API derives the standing turn when nothing is named, and a
    // guess would be refused as stale (or worse, accepted) against a session it never saw.
    expect(answeringSeqOf({}, null)).toBeNull();
  });

  it("does not trust a turn that is not a positive integer", () => {
    // `turn: 0` is the snapshot's own "no turns at all"; anything else is not a seq.
    expect(answeringSeqOf({ turn: 0 }, 2)).toBe(2);
    expect(answeringSeqOf({ turn: "4" }, 2)).toBe(2);
    expect(answeringSeqOf({ turn: 2.5 }, 2)).toBe(2);
    expect(answeringSeqOf({ turn: -1 }, null)).toBeNull();
  });
});
