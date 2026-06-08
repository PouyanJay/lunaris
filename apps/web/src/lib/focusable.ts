/** CSS selector matching the natively-focusable interactive elements inside a container — the one
 *  source of truth for every focus trap (modals, drawers). Extend it here and all traps stay in
 *  sync. Disabled controls and `tabindex="-1"` are excluded. */
export const FOCUSABLE_SELECTOR =
  'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), ' +
  'textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

/** The selector plus `iframe` — for traps that contain embedded frames (e.g. the video lightbox). */
export const FOCUSABLE_SELECTOR_WITH_IFRAME = `iframe, ${FOCUSABLE_SELECTOR}`;
