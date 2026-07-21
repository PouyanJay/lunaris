import rehypeHighlight from "rehype-highlight";
import rehypeKatex from "rehype-katex";
import rehypeSanitize, { defaultSchema } from "rehype-sanitize";
import type { Schema } from "hast-util-sanitize";
import remarkDirective from "remark-directive";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import type { PluggableList } from "unified";
import type { Root } from "mdast";
import { visit } from "unist-util-visit";

import { remarkHighlight } from "./remarkHighlight";
import { remarkKeywordBadges } from "./keywordBadges";
import { remarkProseStructure } from "./proseStructure";
import { remarkSectionLabels } from "./sectionLabels";

/** The lesson prose is authored as Markdown and may now carry rich blocks: admonition callouts
 *  (`:::note` … or a "Note:" lead-in), `:::details` collapsibles, `:term[word]{title="…"}` glossary
 *  tooltips, fenced code (syntax-highlighted, with a copy button via the `pre` component override),
 *  `html-preview` fences (rendered into a sandboxed iframe), and `$…$` / `$$…$$` math.
 *
 *  This module owns the unified pipeline that makes all of that *safe*: directives are lowered to a
 *  small set of custom elements, math/highlight markup is generated from text (never passed through),
 *  and `rehype-sanitize` runs as the gate. Sanitisation runs BEFORE KaTeX/highlight so their trusted,
 *  generated output is inserted after the gate — the schema only has to permit the handful of class
 *  names the math lowering needs as input, plus our directive elements. */

/** Paragraph lead-ins ("Note: …") that become callouts, mapped to a callout variant. */
const LEAD_IN_VARIANTS: Record<string, string> = {
  note: "note",
  tip: "tip",
  insight: "insight",
  warning: "warning",
  example: "example",
  "key takeaway": "key-takeaway",
};

const CALLOUT_DIRECTIVES = new Set([
  "note",
  "tip",
  "insight",
  "warning",
  "example",
  "key-takeaway",
]);

const GLOSSARY_DIRECTIVES = new Set(["term", "def"]);

const LEAD_IN_PATTERN = /^(note|tip|insight|warning|example|key takeaway):\s+/i;

interface DirectiveChild {
  type: string;
  value?: string;
  children?: DirectiveChild[];
  data?: Record<string, unknown>;
}

interface DirectiveNode {
  type: string;
  name?: string;
  attributes?: Record<string, string | null | undefined> | null;
  children?: DirectiveChild[];
  data?: Record<string, unknown>;
}

/** The plain text of a directive child tree (a `:::deeper[label]`'s label paragraph). */
function directiveText(child: DirectiveChild): string {
  if (typeof child.value === "string") return child.value;
  return (child.children ?? []).map(directiveText).join("");
}

/** Lower a directive node onto a hast element name + properties so react-markdown can map it to a
 *  React component, then `rehype-sanitize` can vet it against the extended schema. */
function lowerDirective(node: DirectiveNode): void {
  const data = (node.data ??= {});

  if (node.type === "containerDirective" && node.name === "details") {
    data.hName = "details";
    const label = node.children?.find((child) => child.data?.directiveLabel);
    if (label) {
      label.data = { ...label.data, hName: "summary" };
    }
    return;
  }

  if (node.type === "containerDirective" && node.name && CALLOUT_DIRECTIVES.has(node.name)) {
    data.hName = "callout";
    data.hProperties = { variant: node.name };
    return;
  }

  // Depth fold (Field Guide): `:::deeper[label]` collapses rigor off the main reading path. The
  // label paragraph becomes an attribute (the GoDeeper component owns the summary), not body text.
  if (node.type === "containerDirective" && node.name === "deeper") {
    data.hName = "godeeper";
    const label = node.children?.find((child) => child.data?.directiveLabel);
    data.hProperties = label ? { label: directiveText(label) } : {};
    if (label && node.children) {
      node.children = node.children.filter((child) => child !== label);
    }
    return;
  }

  if (
    (node.type === "textDirective" || node.type === "leafDirective") &&
    node.name &&
    GLOSSARY_DIRECTIVES.has(node.name)
  ) {
    const attrs = node.attributes ?? {};
    data.hName = "glossary";
    data.hProperties = { definition: attrs.title ?? attrs.def ?? "" };
  }
}

/** Turn a "Note:/Tip:/…" lead-in paragraph into a callout, trimming the recognised label. */
function liftLeadIn(node: DirectiveNode): void {
  const first = node.children?.[0];
  if (!first || first.type !== "text" || typeof first.value !== "string") return;
  const match = first.value.match(LEAD_IN_PATTERN);
  const label = match?.[1]?.toLowerCase();
  if (!match || !label) return;
  const variant = LEAD_IN_VARIANTS[label];
  if (!variant) return;
  first.value = first.value.slice(match[0].length);
  const data = (node.data ??= {});
  data.hName = "callout";
  data.hProperties = { variant };
}

/** Remark transform: lower directives and lift "Note:" lead-ins into callouts. */
function remarkRichDirectives() {
  return (tree: Root): void => {
    visit(tree, (node) => {
      const directive = node as unknown as DirectiveNode;
      if (
        directive.type === "containerDirective" ||
        directive.type === "leafDirective" ||
        directive.type === "textDirective"
      ) {
        lowerDirective(directive);
      } else if (node.type === "paragraph") {
        liftLeadIn(node as unknown as DirectiveNode);
      }
    });
  };
}

/** `rehype-sanitize` schema: the default safe set plus the custom directive elements and the class
 *  names KaTeX reads off the lowered math nodes. Sanitisation runs first, so KaTeX/highlight output
 *  (generated downstream from text) never needs to be allow-listed here. */
const schema: Schema = {
  ...defaultSchema,
  tagNames: [
    ...(defaultSchema.tagNames ?? []),
    "callout",
    "glossary",
    "godeeper",
    "steps",
    "step",
    "arrayviz",
    "keyword",
    "mark",
    "examplepanel",
    "workedexample",
    "seclabel",
  ],
  attributes: {
    ...defaultSchema.attributes,
    callout: ["variant"],
    glossary: ["definition"],
    godeeper: ["label"],
    step: ["number", "heading"],
    arrayviz: ["values"],
    keyword: ["category"],
    workedexample: ["literallabel", "literal", "improvedlabel", "improved", "note"],
    seclabel: ["heading", "qual"],
    code: [["className", /^language-./, "math-inline", "math-display"]],
    // Alpha enumerations lifted from prose render as <ol type="a">.
    ol: ["type", "start"],
  },
};

export const remarkPlugins: PluggableList = [
  remarkGfm,
  remarkMath,
  remarkDirective,
  remarkProseStructure,
  remarkSectionLabels,
  remarkRichDirectives,
  remarkKeywordBadges,
  remarkHighlight,
];

export const rehypePlugins: PluggableList = [
  [rehypeSanitize, schema],
  rehypeKatex,
  rehypeHighlight,
];
