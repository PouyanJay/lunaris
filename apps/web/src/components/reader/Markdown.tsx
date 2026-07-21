import "katex/dist/katex.min.css";

import ReactMarkdown, { type Components } from "react-markdown";
import type { PluggableList } from "unified";

import { ArrayViz } from "./ArrayViz";
import { Callout } from "./Callout";
import { ChainFlow, ChainNode } from "./ChainFlow";
import { CodeBlock } from "./CodeBlock";
import { ExamplePanel } from "./ExamplePanel";
import { GlossaryTerm } from "./GlossaryTerm";
import { GoDeeper } from "./GoDeeper";
import { KeywordBadge } from "./KeywordBadge";
import { rehypePlugins, remarkPlugins } from "./markdownPipeline";
import { remarkAutoGlossary } from "./remarkAutoGlossary";
import { SectionLabel } from "./SectionLabel";
import { StepItem } from "./StepItem";
import { Stepper } from "./Stepper";
import { WorkedExampleBlock } from "./WorkedExampleBlock";
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
  godeeper: GoDeeper,
  steps: Stepper,
  step: StepItem,
  arrayviz: ArrayViz,
  keyword: KeywordBadge,
  examplepanel: ExamplePanel,
  workedexample: WorkedExampleBlock,
  seclabel: SectionLabel,
  chainflow: ChainFlow,
  chainnode: ChainNode,
} as Components;

interface MarkdownProps {
  children: string;
  /** Element overrides merged over the safe defaults (e.g. the cross-highlight block tagging). */
  components?: Components;
  /** Course glossary (term → definition): indexed terms in plain prose become hoverable glossary
   *  tooltips (first occurrence per render). Absent → prose renders untouched. */
  glossary?: ReadonlyMap<string, string> | undefined;
  /** Extra class on the wrapper (e.g. to scope nothing — defaults to the tokened prose styling). */
  className?: string;
}

export function Markdown({ children, components, glossary, className }: MarkdownProps) {
  const plugins: PluggableList =
    glossary && glossary.size > 0
      ? [...remarkPlugins, [remarkAutoGlossary, { index: glossary }]]
      : remarkPlugins;
  return (
    <div className={`${styles.markdown} ${className ?? ""}`}>
      <ReactMarkdown
        remarkPlugins={plugins}
        rehypePlugins={rehypePlugins}
        components={{ ...baseComponents, ...components }}
      >
        {children}
      </ReactMarkdown>
    </div>
  );
}
