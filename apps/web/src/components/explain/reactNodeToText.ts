import { isValidElement, type ReactNode } from "react";

/** Flatten rendered markdown children to the plain prose the model should explain. Element props
 *  other than children (hrefs, classNames) are presentation, not content, and are dropped. */
export function reactNodeToText(node: ReactNode): string {
  if (node === null || node === undefined || typeof node === "boolean") return "";
  if (typeof node === "string" || typeof node === "number") return String(node);
  if (Array.isArray(node)) return node.map(reactNodeToText).join("");
  if (isValidElement<{ children?: ReactNode }>(node)) return reactNodeToText(node.props.children);
  return "";
}
