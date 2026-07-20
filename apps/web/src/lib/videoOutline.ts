/** A timed span on the video timeline (a chapter or a transcript cue). */
interface Span {
  startS: number;
  endS: number;
}

/** The index of the span containing `currentTime` — the active chapter/cue as the video plays.
 *  Spans are contiguous and ordered; a time at or past the last span's end stays on the last one,
 *  a time before the first stays on the first, and an empty list is -1 (nothing active). */
export function activeSpanIndex(spans: readonly Span[], currentTime: number): number {
  if (spans.length === 0) return -1;
  for (let i = spans.length - 1; i >= 0; i -= 1) {
    if (currentTime >= spans[i]!.startS) return i;
  }
  return 0;
}
