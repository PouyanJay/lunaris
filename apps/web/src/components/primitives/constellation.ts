/* Deterministic constellation geometry for CourseCover — pure math, no rendering, so the
   "same seed, same art" contract is testable without an SVG in the way. */

export const CANVAS_W = 400;
export const CANVAS_H = 230;
/** Stars keep this inset from the canvas edge so none is clipped by the cover crop. */
export const CANVAS_MARGIN_X = 26;
export const CANVAS_MARGIN_Y = 22;

/** Star hues echo the dark-theme difficulty ramp (fixed brand art, not themed). */
const STAR_HUES = ["#6b8fc4", "#6fa3b8", "#79b39c", "#c89a5a", "#d08a65"];
const HALO_COUNT = 3;

/* Spreads consecutive small seeds (course ids 1, 2, 3…) across the PRNG's state space so
   neighbouring courses don't get near-identical skies. */
const SEED_STRIDE = 97;
const SEED_OFFSET = 13;

/* The crescent sits in the canvas's upper-right quadrant; jitter keeps each cover's moon
   subtly different. The "bite" circle offset/size carve the crescent shape. */
const MOON_RADIUS_MIN = 42;
const MOON_RADIUS_JITTER = 12;
const MOON_RIGHT_INSET = 64;
const MOON_X_JITTER = 30;
const MOON_TOP_INSET = 56;
const MOON_Y_JITTER = 24;
const MOON_BITE_OFFSET_X = 0.55;
const MOON_BITE_OFFSET_Y = -0.3;
const MOON_BITE_SCALE = 0.92;

/** Deterministic PRNG (mulberry32) so a seed always draws the same constellation. */
function mulberry32(seed: number): () => number {
  let t = seed >>> 0;
  return () => {
    t = (t + 0x6d2b79f5) >>> 0;
    let r = Math.imul(t ^ (t >>> 15), 1 | t);
    r = (r + Math.imul(r ^ (r >>> 7), 61 | r)) >>> 0;
    return ((r ^ (r >>> 14)) >>> 0) / 4294967296;
  };
}

export interface Star {
  x: number;
  y: number;
  r: number;
  hue: string;
  isLit: boolean;
}

export interface Constellation {
  stars: Star[];
  /** Each star links back to an earlier one — a connected, acyclic constellation. */
  edges: { from: Star; to: Star }[];
  /** The few lit stars that get a soft glow behind them. */
  halos: Star[];
  moon: { x: number; y: number; r: number; biteX: number; biteY: number; biteR: number };
}

/** The seeded geometry behind a course cover: same seed, same sky. */
export function buildConstellation(seed: number, starCount: number): Constellation {
  const rnd = mulberry32(seed * SEED_STRIDE + SEED_OFFSET);

  const stars: Star[] = Array.from({ length: starCount }, () => ({
    x: CANVAS_MARGIN_X + rnd() * (CANVAS_W - CANVAS_MARGIN_X * 2),
    y: CANVAS_MARGIN_Y + rnd() * (CANVAS_H - CANVAS_MARGIN_Y * 2),
    r: 1.3 + rnd() * 2.3,
    hue: STAR_HUES[Math.floor(rnd() * STAR_HUES.length)] ?? "#ffffff",
    isLit: rnd() > 0.5,
  }));
  const edges = stars
    .slice(1)
    .map((star, i) => ({ from: star, to: stars[Math.floor(rnd() * (i + 1))]! }));
  const halos = stars.filter((s) => s.isLit).slice(0, HALO_COUNT);

  const r = MOON_RADIUS_MIN + rnd() * MOON_RADIUS_JITTER;
  const x = CANVAS_W - MOON_RIGHT_INSET - rnd() * MOON_X_JITTER;
  const y = MOON_TOP_INSET + rnd() * MOON_Y_JITTER;
  const moon = {
    x,
    y,
    r,
    biteX: x + r * MOON_BITE_OFFSET_X,
    biteY: y + r * MOON_BITE_OFFSET_Y,
    biteR: r * MOON_BITE_SCALE,
  };

  return { stars, edges, halos, moon };
}
