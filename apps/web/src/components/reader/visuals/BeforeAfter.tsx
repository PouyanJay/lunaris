import { useState } from "react";

import { Tabs } from "../../primitives/Tabs";
import type { BeforeAfterSpec, TransformSide } from "../../../types/course";
import styles from "./BeforeAfter.module.css";

interface BeforeAfterProps {
  spec: BeforeAfterSpec;
}

/** The visible body of one transformation side: its content as prose. */
function SideBody({ side }: { side: TransformSide }) {
  return (
    <div className={styles.side}>
      <p className={styles.prose}>{side.content}</p>
    </div>
  );
}

/** An interactive Before/After transformation: two labelled states the reader toggles between with a
 *  tab (e.g. a naive approach → its optimised form). Reuses the accessible `Tabs` primitive (roving
 *  tabindex, arrow keys, WAI-ARIA tabs); only the active state is in the accessibility tree, so the
 *  change is read by toggling rather than by scanning two blocks. The spec's title is rendered by the
 *  surrounding `VisualRenderer` figure, so this owns only the toggle and the two sides. */
export function BeforeAfter({ spec }: BeforeAfterProps) {
  const [activeId, setActiveId] = useState<"before" | "after">("before");
  const tabs = [
    { id: "before", label: spec.before.label },
    { id: "after", label: spec.after.label },
  ];
  const side = activeId === "after" ? spec.after : spec.before;

  return (
    <div className={styles.beforeAfter}>
      <Tabs
        tabs={tabs}
        activeId={activeId}
        onChange={(id) => setActiveId(id === "after" ? "after" : "before")}
        label={spec.title ?? `${spec.before.label} and ${spec.after.label}`}
        panelClassName={styles.panel}
      >
        <SideBody side={side} />
      </Tabs>
    </div>
  );
}
