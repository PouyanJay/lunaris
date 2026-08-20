import { useState } from "react";

import { SIDEBAR_RAIL_WIDTH, useSidebarLayout } from "./useSidebarLayout";

export interface TeachingRail {
  collapsed: boolean;
  toggleCollapsed: () => void;
  /** The rail's width in px, for the shell to publish as its `--sidebar-width`. */
  width: number;
}

/** How wide Live's rail is, given whether a session is being taught.
 *
 *  A session is a focus surface: a full-width nav beside it competes with the teaching, so the rail
 *  starts as the mini icon column there whatever the stored preference says, and expands on a
 *  click. Kept as its own state rather than by writing the shared preference, because collapsing
 *  the rail to teach somebody must not quietly collapse it in Studio tomorrow.
 *
 *  `session` identifies the session being taught, so a *different* one starts folded again. Its own
 *  hook because it is a small state machine with a reset rule, and the shell should be a rendering
 *  concern (review finding) — the same reason `useSidebarLayout` and `useLiveGraph` are hooks. */
export function useTeachingRail(session: string | null): TeachingRail {
  const layout = useSidebarLayout();
  const [openedInSession, setOpenedInSession] = useState(false);
  const [current, setCurrent] = useState(session);
  if (current !== session) {
    // Adjusting state during render rather than in an effect: React re-runs this component
    // immediately with the new value, so the rail never paints one frame in the old session's
    // state. The documented pattern for exactly this.
    setCurrent(session);
    setOpenedInSession(false);
  }

  const teaching = session !== null;
  const collapsed = teaching ? !openedInSession : layout.collapsed;
  return {
    collapsed,
    toggleCollapsed: teaching ? () => setOpenedInSession((open) => !open) : layout.toggleCollapsed,
    width: collapsed ? SIDEBAR_RAIL_WIDTH : layout.width,
  };
}
