import { useState } from "react";
import type { Components } from "react-markdown";

import { ArrayViz } from "./ArrayViz";
import { HtmlPreview } from "./HtmlPreview";
import styles from "./CodeBlock.module.css";

/** Minimal hast shape for reading the fenced code's language + raw text off the lowered node. */
interface HastNode {
  type?: string;
  tagName?: string;
  value?: string;
  properties?: { className?: unknown };
  children?: HastNode[];
}

/** The `language-xxx` token on the fenced code element (rehype-highlight also adds `hljs`). */
function languageOf(pre?: HastNode): string | null {
  const code = pre?.children?.find((child) => child.tagName === "code");
  const className = code?.properties?.className;
  const tokens = Array.isArray(className) ? className.map(String) : [];
  const language = tokens.find((token) => token.startsWith("language-"));
  return language ? language.slice("language-".length) : null;
}

/** Flatten the text content of a hast subtree (the code's source, pre-highlight spans). */
function textOf(node?: HastNode): string {
  if (!node) return "";
  if (node.type === "text") return node.value ?? "";
  return (node.children ?? []).map(textOf).join("");
}

async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard?.writeText(text);
    return true;
  } catch {
    return false;
  }
}

/** Renders a fenced code block. A `html-preview` fence is rendered into a sandboxed iframe so the
 *  lesson can show a live snippet safely; any other fence renders as a titled, syntax-highlighted
 *  panel with a copy button. Used as react-markdown's `pre` override, so `children` is the already
 *  highlighted `<code>` subtree and `node` carries the language + raw source. */
export const CodeBlock: NonNullable<Components["pre"]> = ({ node, children }) => {
  const hast = node as HastNode | undefined;
  const language = languageOf(hast);
  const source = textOf(hast).replace(/\n$/, "");
  const [copied, setCopied] = useState(false);

  if (language === "html-preview") {
    return <HtmlPreview html={source} />;
  }

  // An ```array fence renders as the indexed array visual (the values, on one or more lines).
  if (language === "array") {
    return <ArrayViz values={source.replace(/\n/g, " ")} />;
  }

  const onCopy = async () => {
    if (await copyText(source)) {
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    }
  };

  return (
    <figure className={styles.block}>
      <figcaption className={styles.bar}>
        <span className={styles.lang}>{language ?? "text"}</span>
        <button type="button" className={styles.copy} onClick={onCopy} aria-live="polite">
          {copied ? "Copied" : "Copy"}
        </button>
      </figcaption>
      <pre className={styles.pre}>{children}</pre>
    </figure>
  );
};
