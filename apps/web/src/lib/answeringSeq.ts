/** Which turn a send from the generative panel is answering (P2b T9).
 *
 *  Named on the wire in `forwardedProps.answeringSeq` so the API can refuse a late answer, one to
 *  a card the thread still shows from three turns ago, with the 409 REST gives it, rather than
 *  grading it against whatever question is up now (T4's parked hazard, AD22).
 *
 *  Two sources, in order. The agent's state as the last `STATE_SNAPSHOT` left it: its `turn` is
 *  `SessionSnapshot.turn`, the turn now in front of the learner, and it is the only thing in the
 *  panel that moves when the panel's own runs move the session on (the REST read that seeded the
 *  page does not re-read). Failing that, the standing turn the panel mounted with. Failing both,
 *  nothing: the API derives the standing turn when nothing is named, and a guess would be refused
 *  as stale, or accepted, against a session this browser never saw.
 */
export function answeringSeqOf(agentState: unknown, standingSeq: number | null): number | null {
  const named = (agentState as { turn?: unknown } | null | undefined)?.turn;
  if (typeof named === "number" && Number.isInteger(named) && named >= 1) {
    return named;
  }
  return standingSeq;
}
