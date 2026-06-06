import "katex/dist/katex.min.css";

import ReactMarkdown, { type Components } from "react-markdown";

import { Callout } from "./Callout";
import { CodeBlock } from "./CodeBlock";
import { GlossaryTerm } from "./GlossaryTerm";
import { rehypePlugins, remarkPlugins } from "./markdownPipeline";
import { StepItem } from "./StepItem";
import { Stepper } from "./Stepper";
import styles from "./Markdown.module.css";

/** The lesson prose is authored as Markdown; render it safely with GitHub-flavoured features and a
 *  rich-block layer — admonition callouts, `:::details` collapsibles, glossary tooltips, fenced code
 *  (highlighted, copyable), sandboxed `html-preview`, and KaTeX math. The unified pipeline +
 *  sanitiser live in `markdownPipeline`; this module owns the element→component bindings and the one
 *  cross-cutting rule that every link opens in a new tab. */

// `callout`/`glossary` are custom element names emitted by the remark pipeline, so the component map
// is widened past react-markdown's intrinsic-element keys.
const baseComponents = {
  a({ href, children, ...props }) {
    return (
      <a href={href} target="_blank" rel="noopener noreferrer" {...props}>
        {children}
      </a>
    );
  },
  // Block code is wrapped in <pre>; overriding `pre` lets one component own the copy bar / preview
  // routing while inline `code` keeps the default chip styling.
  pre: CodeBlock,
  // Custom elements lowered from directives / prose structure by the remark pipeline.
  callout: Callout,
  glossary: GlossaryTerm,
  steps: Stepper,
  step: StepItem,
} as Components;

interface MarkdownProps {
  children: string;
  /** Element overrides merged over the safe defaults (e.g. the cross-highlight block tagging). */
  components?: Components;
  /** Extra class on the wrapper (e.g. to scope nothing — defaults to the tokened prose styling). */
  className?: string;
}

export function Markdown({ children, components, className }: MarkdownProps) {
  return (
    <div className={`${styles.markdown} ${className ?? ""}`}>
      <ReactMarkdown
        remarkPlugins={remarkPlugins}
        rehypePlugins={rehypePlugins}
        components={{ ...baseComponents, ...components }}
      >
        {children}
      </ReactMarkdown>
    </div>
  );
}
