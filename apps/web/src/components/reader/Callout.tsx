import type { ReactNode } from "react";

import { ExplainAction, reactNodeToText } from "../explain/ExplainAction";
import {
  CALLOUT_META,
  Callout as CalloutPanel,
  resolveCalloutVariant,
} from "../primitives/Callout";

interface CalloutProps {
  variant?: string;
  children?: ReactNode;
}

/** The reader's admonition: the design-system Callout panel plus the inline Explain affordance,
 *  wired with the callout's flattened prose and its variant as the model's context. */
export function Callout({ variant, children }: CalloutProps) {
  const { label } = CALLOUT_META[resolveCalloutVariant(variant)];
  return (
    <CalloutPanel
      variant={variant}
      action={<ExplainAction content={reactNodeToText(children)} context={`${label} callout`} />}
    >
      {children}
    </CalloutPanel>
  );
}
