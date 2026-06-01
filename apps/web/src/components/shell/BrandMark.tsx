import { useId } from "react";

interface BrandMarkProps {
  /** Rendered size in px (square). Defaults to the sidebar brand size. */
  size?: number;
}

/** The Lunaris brand mark: an amber rounded-square tile with a dark crescent-moon motif (the
 *  "lunar" in Lunaris). A fixed brand asset — its colours are intentionally literal, not themed,
 *  so the mark renders identically on light and dark. Decorative: the adjacent "Lunaris" wordmark
 *  carries the accessible name, so this is aria-hidden. */
export function BrandMark({ size = 22 }: BrandMarkProps) {
  // Mask ids are document-global; derive a unique one so two marks on a page don't collide (the
  // second would otherwise steal the crescent). Strip useId's colons — invalid in a url(#…) ref.
  const maskId = `lunaris-moon-${useId().replace(/:/g, "")}`;
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 64 64"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
      focusable="false"
    >
      <rect width="64" height="64" rx="14" fill="#e8a33d" />
      <g transform="translate(9,9) scale(0.72)" fill="#1a1206">
        <mask id={maskId}>
          <rect width="64" height="64" fill="#fff" />
          <circle cx="32" cy="20" r="23" fill="#000" />
        </mask>
        <circle cx="32" cy="36" r="24" mask={`url(#${maskId})`} />
        <path d="M27,31 C22,33 22,41 28,42 C34,43 39,41 38,35 C37,31 32,29 27,31 Z" />
        <circle cx="29" cy="25.5" r="4.6" />
        <path
          d="M18,32.5 L25,35.5 L30,32.5"
          fill="none"
          stroke="#1a1206"
          strokeWidth="3"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </g>
    </svg>
  );
}
