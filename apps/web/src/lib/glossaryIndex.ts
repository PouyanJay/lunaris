import type { Course } from "../types/course";

/** Case-insensitive term → definition, for the reader's glossary auto-marking. */
export type GlossaryIndex = ReadonlyMap<string, string>;

/** An authored inline glossary directive in prose: `:term[word]{title="…"}` / `:def[word]{def="…"}`. */
const DIRECTIVE_PATTERN = /:(?:term|def)\[([^\]]+)\]\{([^}]*)\}/g;
const DEFINITION_ATTR = /(?:title|def)="([^"]*)"/;

/** Build the course's glossary from data the pipeline already ships: every knowledge component's
 *  label + definition from the prerequisite graph, overridden by any `:term` definitions authored
 *  inline in lesson prose (the author's wording wins over the graph's). Definitions are never
 *  invented — a term without one is simply absent. */
export function buildGlossaryIndex(course: Course): GlossaryIndex {
  const index = new Map<string, string>();
  for (const node of course.graph?.nodes ?? []) {
    const term = node.label.trim().toLowerCase();
    const definition = node.definition?.trim();
    if (term && definition) index.set(term, definition);
  }
  for (const module of course.modules) {
    for (const lesson of module.lessons) {
      const { activate, demonstrate, apply, integrate } = lesson.segments;
      for (const prose of [activate.prose, demonstrate.prose, apply.prose, integrate.prose]) {
        for (const match of prose.matchAll(DIRECTIVE_PATTERN)) {
          const term = match[1]?.trim().toLowerCase();
          const definition = DEFINITION_ATTR.exec(match[2] ?? "")?.[1]?.trim();
          if (term && definition) index.set(term, definition);
        }
      }
    }
  }
  return index;
}
