import { useId } from "react";

import { buildConstellation, CANVAS_H, CANVAS_W } from "./constellation";

/* The cover is brand art on a fixed night-sky canvas — like the BrandMark, its colours are
   intentionally literal (not themed) so a cover renders identically on light and dark. The star
   hues echo the dark-theme difficulty ramp; the crescent echoes the amber brand mark. */
const NIGHT_SKY = "#0a0c10";
const MOON_AMBER = "#e0a23c";
const EDGE_STROKE = "rgba(224, 162, 60, 0.12)";
const UNLIT_STAR = "rgba(255, 255, 255, 0.16)";

const fmt = (n: number) => Number(n.toFixed(2));

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
  const { stars, edges, halos, moon } = buildConstellation(seed, nodes);

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
          <circle cx={fmt(moon.x)} cy={fmt(moon.y)} r={fmt(moon.r)} fill="white" />
          <circle cx={fmt(moon.biteX)} cy={fmt(moon.biteY)} r={fmt(moon.biteR)} fill="black" />
        </mask>
      </defs>
      <rect width={CANVAS_W} height={CANVAS_H} fill={NIGHT_SKY} />
      <circle
        cx={fmt(moon.x)}
        cy={fmt(moon.y)}
        r={fmt(moon.r)}
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
          fill={s.isLit ? s.hue : UNLIT_STAR}
        />
      ))}
    </svg>
  );
}
