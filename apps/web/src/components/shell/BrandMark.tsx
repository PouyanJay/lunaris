import { useId } from "react";

interface BrandMarkProps {
  /** Rendered size in px (square). Defaults to the sidebar brand size. */
  size?: number;
}

/** The Lunaris brand mark: an amber crescent moon cradling a filled dot (the "lunar" in Lunaris),
 *  drawn on a transparent background. A fixed brand asset — its colour is intentionally literal,
 *  not themed, so the mark renders identically on light and dark. Decorative: the adjacent "Lunaris"
 *  wordmark carries the accessible name, so this is aria-hidden. */
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
      fill="#e8a33d"
      aria-hidden="true"
      focusable="false"
    >
      <mask id={maskId}>
        <rect width="64" height="64" fill="#fff" />
        <circle cx="32" cy="22" r="21" fill="#000" />
      </mask>
      <circle cx="32" cy="34" r="22" mask={`url(#${maskId})`} />
      <circle cx="32" cy="26" r="8" />
    </svg>
  );
}
