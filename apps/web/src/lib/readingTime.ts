import type { Lesson } from "../types/course";

/** Average adult prose reading speed; the Field Guide's time estimates ride on it. */
const WORDS_PER_MINUTE = 220;

/** Estimate how many minutes the lesson takes to read: the word count of its four phases plus
 *  the expects/self-check bookends at 220 wpm, rounded up and never below one minute. Markdown
 *  syntax counts as words — the error is small and uniform, and the figure is an estimate. */
export function estimateReadingMinutes(lesson: Lesson): number {
  const { activate, demonstrate, apply, integrate } = lesson.segments;
  const text = [
    activate.prose,
    demonstrate.prose,
    apply.prose,
    integrate.prose,
    ...(lesson.expects ?? []),
    ...(lesson.selfCheck ?? []),
  ].join(" ");
  const words = text.split(/\s+/).filter(Boolean).length;
  return Math.max(1, Math.ceil(words / WORDS_PER_MINUTE));
}
