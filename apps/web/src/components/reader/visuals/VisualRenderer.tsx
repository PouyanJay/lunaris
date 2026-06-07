import type { ReactNode } from "react";

import type { Visual } from "../../../types/course";
import { BeforeAfter } from "./BeforeAfter";
import { ComparisonTable } from "./ComparisonTable";
import { FlowDiagram } from "./FlowDiagram";
import { MermaidFallback } from "./MermaidFallback";
import { StepsDiagram } from "./StepsDiagram";
import { TimelineDiagram } from "./TimelineDiagram";
import { WorkedExample } from "./WorkedExample";
import styles from "./visuals.module.css";

/** Pick the renderer for a visual: a typed `spec` draws with the branded components; otherwise the
 *  Mermaid `source` is the fallback. Unknown future spec types fall through to the same fallback. */
function selectVisualBody(visual: Visual): ReactNode {
  const { spec } = visual;
  switch (spec?.type) {
    case "flow":
    case "tree":
      return <FlowDiagram spec={spec} />;
    case "steps":
      return <StepsDiagram spec={spec} />;
    case "comparison":
      return <ComparisonTable spec={spec} />;
    case "timeline":
      return <TimelineDiagram spec={spec} />;
    case "before-after":
      return <BeforeAfter spec={spec} />;
    case "worked-example":
      return (
        <WorkedExample
          literal={{ label: spec.literal.label, text: spec.literal.content }}
          improved={{ label: spec.improved.label, text: spec.improved.content }}
          note={spec.note}
        />
      );
    default:
      return visual.source ? <MermaidFallback source={visual.source} /> : null;
  }
}

interface VisualRendererProps {
  visual: Visual;
}

/** Render one segment visual inside a captioned figure card. Renders nothing when there is neither
 *  a spec nor a source to show. */
export function VisualRenderer({ visual }: VisualRendererProps) {
  const body = selectVisualBody(visual);
  if (!body) return null;

  const title = visual.spec?.title ?? null;
  return (
    <figure className={styles.card}>
      {title && <figcaption className={styles.cardTitle}>{title}</figcaption>}
      {body}
    </figure>
  );
}
