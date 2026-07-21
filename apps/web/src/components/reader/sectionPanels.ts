import type { Root } from "mdast";

/** A worked example / attribution is a concrete instance, and reads better set apart from the general
 *  explanation. This remark transform — run AFTER the section labels (R1) and their body lifts (R3/R4)
 *  — gathers a section whose eyebrow is WORKED EXAMPLE / WORKED ATTRIBUTION and wraps the label plus
 *  its following blocks (up to the next section) in a bordered panel (`sectionpanel`). Presentation-
 *  only. Bare "Example:" is left to the callout system (it never becomes a section label), so this
 *  only ever fires on the multi-word worked-* labels. */

interface Node {
  type: string;
  children?: Node[];
  data?: { hName?: string; hProperties?: Record<string, unknown> };
}

const PANEL_HEADING = /\b(?:WORKED|ATTRIBUTION|EXAMPLE)\b/i;

function isSectionLabel(node: Node): boolean {
  return node.data?.hName === "seclabel";
}

function headingOf(node: Node): string {
  return String(node.data?.hProperties?.heading ?? "");
}

function buildPanel(blocks: Node[]): Node {
  return { type: "blockquote", data: { hName: "sectionpanel" }, children: blocks };
}

function remarkSectionPanels() {
  return (tree: Root): void => {
    const children = tree.children as unknown as Node[];
    const result: Node[] = [];

    let i = 0;
    while (i < children.length) {
      const node = children[i]!;
      if (isSectionLabel(node) && PANEL_HEADING.test(headingOf(node))) {
        let j = i + 1;
        while (j < children.length && !isSectionLabel(children[j]!)) j += 1;
        result.push(buildPanel(children.slice(i, j)));
        i = j;
      } else {
        result.push(node);
        i += 1;
      }
    }

    tree.children = result as unknown as Root["children"];
  };
}

export { remarkSectionPanels };
