/** Deterministic 32-bit seed from a course id (FNV-1a), so a course keeps the same constellation
 *  cover across sessions and surfaces. */
export function coverSeed(courseId: string): number {
  let hash = 0x811c9dc5;
  for (let index = 0; index < courseId.length; index++) {
    hash ^= courseId.charCodeAt(index);
    hash = Math.imul(hash, 0x01000193);
  }
  return hash >>> 0;
}
