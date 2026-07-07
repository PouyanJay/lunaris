import { useId } from "react";

/* The cover is brand art on a fixed night-sky canvas — like the BrandMark, its colours are
   intentionally literal (not themed) so a cover renders identically on light and dark. The star
   hues echo the dark-theme difficulty ramp; the crescent echoes the amber brand mark. */
const CANVAS_W = 400;
const CANVAS_H = 230;
const STAR_HUES = ["#6b8fc4", "#6fa3b8", "#79b39c", "#c89a5a", "#d08a65"];
const NIGHT_SKY = "#0a0c10";
const MOON_AMBER = "#e0a23c";
const EDGE_STROKE = "rgba(224, 162, 60, 0.12)";
const UNLIT_STAR = "rgba(255, 255, 255, 0.16)";
const CANVAS_MARGIN_X = 26;
const CANVAS_MARGIN_Y = 22;

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

interface Star {
  x: number;
  y: number;
  r: number;
  hue: string;
  lit: boolean;
}

interface CourseCoverProps {
  /** Stable per-course seed (e.g. a hash of the course id) — same seed, same constellation. */
  seed: number;
  /** Star count; more stars reads as a denser course. */
  nodes?: number;
}

/** A course's generated cover: a seeded constellation — tier-hued stars joined by faint amber
 *  edges under a crescent moon — on a fixed night-sky canvas. Deterministic per seed so a course
 *  keeps its cover across sessions. Decorative: the adjacent course title carries the name. */
export function CourseCover({ seed, nodes = 11 }: CourseCoverProps) {
  const maskId = `lunaris-cover-${useId().replace(/:/g, "")}`;
  const rnd = mulberry32(seed * 97 + 13);

  const stars: Star[] = Array.from({ length: nodes }, () => ({
    x: CANVAS_MARGIN_X + rnd() * (CANVAS_W - CANVAS_MARGIN_X * 2),
    y: CANVAS_MARGIN_Y + rnd() * (CANVAS_H - CANVAS_MARGIN_Y * 2),
    r: 1.3 + rnd() * 2.3,
    hue: STAR_HUES[Math.floor(rnd() * STAR_HUES.length)] ?? UNLIT_STAR,
    lit: rnd() > 0.5,
  }));
  // Each star links back to an earlier one — a connected, acyclic constellation.
  const edges = stars
    .slice(1)
    .map((star, i) => ({ from: star, to: stars[Math.floor(rnd() * (i + 1))]! }));
  const halos = stars.filter((s) => s.lit).slice(0, 3);

  const moonR = 42 + rnd() * 12;
  const moonX = CANVAS_W - 64 - rnd() * 30;
  const moonY = 56 + rnd() * 24;

  const fmt = (n: number) => Number(n.toFixed(2));

  return (
    <svg
      viewBox={`0 0 ${CANVAS_W} ${CANVAS_H}`}
      preserveAspectRatio="xMidYMid slice"
      style={{ width: "100%", height: "100%", display: "block" }}
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
      focusable="false"
    >
      <defs>
        <mask id={maskId}>
          <circle cx={fmt(moonX)} cy={fmt(moonY)} r={fmt(moonR)} fill="white" />
          <circle
            cx={fmt(moonX + moonR * 0.55)}
            cy={fmt(moonY - moonR * 0.3)}
            r={fmt(moonR * 0.92)}
            fill="black"
          />
        </mask>
      </defs>
      <rect width={CANVAS_W} height={CANVAS_H} fill={NIGHT_SKY} />
      <circle
        cx={fmt(moonX)}
        cy={fmt(moonY)}
        r={fmt(moonR)}
        fill={MOON_AMBER}
        opacity={0.15}
        mask={`url(#${maskId})`}
      />
      {halos.map((s, i) => (
        <circle
          key={`h${i}`}
          cx={fmt(s.x)}
          cy={fmt(s.y)}
          r={fmt(s.r * 3)}
          fill={s.hue}
          opacity={0.11}
        />
      ))}
      {edges.map((e, i) => (
        <line
          key={`e${i}`}
          x1={fmt(e.from.x)}
          y1={fmt(e.from.y)}
          x2={fmt(e.to.x)}
          y2={fmt(e.to.y)}
          stroke={EDGE_STROKE}
          strokeWidth={1}
        />
      ))}
      {stars.map((s, i) => (
        <circle
          key={`s${i}`}
          cx={fmt(s.x)}
          cy={fmt(s.y)}
          r={fmt(s.r)}
          fill={s.lit ? s.hue : UNLIT_STAR}
        />
      ))}
    </svg>
  );
}
