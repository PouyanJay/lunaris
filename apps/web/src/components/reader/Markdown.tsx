import ReactMarkdown, { type Components } from "react-markdown";
import rehypeSanitize from "rehype-sanitize";
import remarkGfm from "remark-gfm";

import styles from "./Markdown.module.css";

/** The lesson prose is authored as Markdown; render it safely with GitHub-flavoured features
 *  (lists, tables, task lists, strikethrough, autolinks) and a sanitiser so no raw/executable HTML
 *  can survive. Element styling is layered on in `markdownComponents` (T1) — this module owns the
 *  safe-by-default pipeline and the one cross-cutting rule that every link opens in a new tab. */

const remarkPlugins = [remarkGfm];
const rehypePlugins = [rehypeSanitize];

const baseComponents: Components = {
  a({ href, children, ...props }) {
    return (
      <a href={href} target="_blank" rel="noopener noreferrer" {...props}>
        {children}
      </a>
    );
  },
};

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
