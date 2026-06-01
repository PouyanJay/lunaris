/**
 * Format an elapsed build-phase span for the timeline: sub-minute → seconds with one decimal
 * ("1.5s"), minute-plus → whole minutes + seconds ("2m 5s"). Rounds on the whole-second total so
 * 119.5s carries to "2m 0s" rather than emitting "1m 60s". A negative span (clock skew between
 * client-stamped stage arrivals) clamps to zero instead of surfacing a confusing "−1.2s".
 */
export function formatDuration(elapsedMs: number): string {
  const totalSeconds = Math.max(0, elapsedMs) / 1000;
  if (totalSeconds < 60) return `${totalSeconds.toFixed(1)}s`;
  const whole = Math.round(totalSeconds);
  return `${Math.floor(whole / 60)}m ${whole % 60}s`;
}
